"""Practice loop: adapt decisions, ask for y/n, simulate fills, write logs."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import TextIO

from seduma_demo.adapters import get_adapter
from seduma_demo.constants import DISCLAIMER, SMALL_SAMPLE_WARNING
from seduma_demo.errors import AdapterError, PracticeError
from seduma_demo.models import LOG_FIELDS, LogRow, OrderIntent, RejectedDecision
from seduma_demo.numbers import format_number
from seduma_demo.prices import PriceBook, PricePoint, load_prices
from seduma_demo.simulate import Account, resolve_shares, apply_fill
from seduma_demo.summary import build_summary

InputFn = Callable[[str], str]
Writer = TextIO


def run_practice(
    *,
    agent: str,
    decision_file: Path,
    prices_file: Path,
    out_dir: Path,
    practice_auto: bool,
    slippage_bps: Decimal,
    fee_bps: Decimal,
    cash: Decimal,
    sizing_portfolio: Decimal,
    input_fn: InputFn | None = None,
    stdout: Writer | None = None,
) -> dict[str, object]:
    import sys

    output = stdout if stdout is not None else sys.stdout
    reader = input_fn if input_fn is not None else input
    payload = _load_json(decision_file)
    try:
        parsed = get_adapter(agent).parse(payload)
    except AdapterError as exc:
        raise AdapterError(f"{decision_file}: {exc}") from exc
    if not parsed.intents and not parsed.rejected:
        raise AdapterError(f"{decision_file}: no decisions in file")
    prices = load_prices(prices_file)
    account = Account(cash=cash)
    rows: list[LogRow] = []
    mode = "practice-auto" if practice_auto else "practice-confirm"
    _header(
        output,
        agent=agent,
        decision_file=decision_file,
        prices_file=prices_file,
        mode=mode,
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
        cash=cash,
        sizing_portfolio=sizing_portfolio,
    )
    for rejected in parsed.rejected:
        row = _rejected_row(rejected, account, slippage_bps, fee_bps)
        rows.append(row)
        _say(output, f"Unsupported {rejected.symbol} {rejected.source_action}: {rejected.reason}")
    for index, intent in enumerate(parsed.intents, start=1):
        rows.append(
            _one_intent(
                index,
                intent,
                prices,
                account,
                practice_auto=practice_auto,
                slippage_bps=slippage_bps,
                fee_bps=fee_bps,
                sizing_portfolio=sizing_portfolio,
                reader=reader,
                output=output,
            )
        )
    summary = build_summary(
        rows,
        account,
        prices,
        starting_cash=cash,
        mode=mode,
        decision_file=str(decision_file),
        prices_file=str(prices_file),
        agent=agent,
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
    )
    _write(out_dir, rows, summary)
    _print_summary(output, summary, out_dir)
    return summary


def _one_intent(
    index: int,
    intent: OrderIntent,
    prices: PriceBook,
    account: Account,
    *,
    practice_auto: bool,
    slippage_bps: Decimal,
    fee_bps: Decimal,
    sizing_portfolio: Decimal,
    reader: InputFn,
    output: Writer,
) -> LogRow:
    point = prices.resolve(intent.symbol, intent.as_of)
    _say(output, f"{index}. {intent.side} {intent.symbol}{_when(intent)}")
    _say(output, f"   rationale: {_one_line(intent.rationale)}")
    if intent.notes:
        _say(output, f"   note: {'; '.join(intent.notes)}")
    if intent.side != "HOLD" and point is None:
        _say(output, "   skipped: no close on or before the decision date")
        return _row(
            intent,
            status="skipped",
            reason="no price",
            account=account,
            slippage_bps=slippage_bps,
            fee_bps=fee_bps,
            requested=_requested(intent),
        )
    if point is not None:
        _say(
            output,
            f"   reference close {_num(point.close)} on {point.date}",
        )
    shares = Decimal("0")
    if intent.side != "HOLD":
        assert point is not None
        shares = resolve_shares(intent, point.close, sizing_portfolio)
        if shares <= 0:
            _say(output, "   skipped: size rounds to zero")
            return _row(
                intent,
                status="skipped",
                reason="size rounds to zero",
                account=account,
                point=point,
                slippage_bps=slippage_bps,
                fee_bps=fee_bps,
                requested=shares,
            )
        _say(output, f"   size {_num(shares)} shares")
    approved = _approve(intent, shares, point, practice_auto, reader, output)
    if not approved:
        _say(output, "   declined")
        return _row(
            intent,
            status="declined",
            reason="declined",
            account=account,
            point=point,
            slippage_bps=slippage_bps,
            fee_bps=fee_bps,
            requested=shares if intent.side != "HOLD" else Decimal("0"),
            approved=False,
        )
    if intent.side == "HOLD":
        _say(output, "   acknowledged HOLD, no fill")
        return _row(
            intent,
            status="acknowledged",
            account=account,
            point=point,
            slippage_bps=slippage_bps,
            fee_bps=fee_bps,
            requested=Decimal("0"),
            filled=Decimal("0"),
            approved=True,
        )
    assert point is not None
    result = apply_fill(
        account,
        symbol=intent.symbol,
        side=intent.side,
        shares=shares,
        close=point.close,
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
    )
    notes = tuple(intent.notes) + result.notes
    if result.status == "filled":
        _say(
            output,
            "   SIMULATED fill "
            f"{_num(result.filled)} @ {_num(result.fill_price)} "
            f"fee {_num(result.fee)}",
        )
        if result.realized_pnl is not None:
            _say(output, f"   realized P&L {_num(result.realized_pnl)}")
        if result.notes:
            _say(output, f"   note: {'; '.join(result.notes)}")
    else:
        _say(output, f"   not filled: {result.reason}")
    return _row(
        intent,
        status=result.status,
        reason=result.reason,
        account=account,
        point=point,
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
        requested=shares,
        filled=result.filled,
        fill_price=result.fill_price,
        fee=result.fee,
        realized=result.realized_pnl,
        approved=True,
        notes="; ".join(notes),
    )


def _approve(
    intent: OrderIntent,
    shares: Decimal,
    point: PricePoint | None,
    practice_auto: bool,
    reader: InputFn,
    output: Writer,
) -> bool:
    if practice_auto:
        _say(output, "   approved (--practice-auto)")
        return True
    if intent.side == "HOLD":
        prompt = f"SIMULATED acknowledge HOLD {intent.symbol} (no order)? [y/n] "
    else:
        assert point is not None
        prompt = (
            f"SIMULATED approve {intent.side} {_num(shares)} {intent.symbol} "
            f"at reference close {_num(point.close)} on {point.date}? [y/n] "
        )
    while True:
        try:
            answer = reader(prompt)
        except EOFError as exc:
            raise PracticeError(
                "confirmation stopped at end of input. "
                "Re-run with --practice-auto for an unattended simulated run."
            ) from exc
        cleaned = answer.strip().lower()
        if cleaned in {"y", "yes"}:
            _break_after_prompt(output)
            return True
        if cleaned in {"n", "no"}:
            _break_after_prompt(output)
            return False
        _break_after_prompt(output)
        _say(output, "Please answer y or n.")


def _rejected_row(
    rejected: RejectedDecision,
    account: Account,
    slippage_bps: Decimal,
    fee_bps: Decimal,
) -> LogRow:
    return LogRow(
        status="unsupported",
        source=rejected.source,
        symbol=rejected.symbol,
        side=rejected.source_action.upper(),
        source_action=rejected.source_action,
        reason=rejected.reason,
        rationale=rejected.rationale,
        cash_after=account.cash,
        position_after=_shares_of(account, rejected.symbol),
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
        approved=None,
    )


def _row(
    intent: OrderIntent,
    *,
    status: str,
    account: Account,
    slippage_bps: Decimal,
    fee_bps: Decimal,
    reason: str = "",
    point: PricePoint | None = None,
    requested: Decimal | None = None,
    filled: Decimal | None = None,
    fill_price: Decimal | None = None,
    fee: Decimal | None = None,
    realized: Decimal | None = None,
    approved: bool | None = None,
    notes: str = "",
) -> LogRow:
    if not notes and intent.notes:
        notes = "; ".join(intent.notes)
    position = _shares_of(account, intent.symbol)
    return LogRow(
        status=status,
        source=intent.source,
        symbol=intent.symbol,
        side=intent.side,
        source_action=intent.source_action,
        reason=reason,
        requested_size=requested,
        filled_size=filled,
        as_of=intent.as_of or "",
        price_date=point.date if point else "",
        reference_close=point.close if point else None,
        fill_price=fill_price,
        fee=fee,
        slippage_bps=slippage_bps,
        fee_bps=fee_bps,
        realized_pnl=realized,
        cash_after=account.cash,
        position_after=position,
        rationale=intent.rationale,
        approved=approved,
        notes=notes,
    )


def _shares_of(account: Account, symbol: str) -> Decimal:
    position = account.positions.get(symbol)
    if position is None:
        return Decimal("0")
    return position.shares


def _requested(intent: OrderIntent) -> Decimal | None:
    return intent.share_size


def _header(output: Writer, **parts: object) -> None:
    _say(output, "Seduma Trade practice demo")
    _say(output, "SIMULATED FILLS ONLY. No broker connection. No live trading.")
    _say(output, "")
    _say(output, f"Agent: {parts['agent']}")
    _say(output, f"Decisions: {parts['decision_file']}")
    _say(output, f"Prices: {parts['prices_file']}")
    _say(output, f"Mode: {parts['mode']}")
    _say(output, f"Slippage: {_num(parts['slippage_bps'])} bps adverse")
    _say(output, f"Fees: {_num(parts['fee_bps'])} bps")
    _say(output, f"Starting cash: {_num(parts['cash'])}")
    _say(output, f"Sizing portfolio: {_num(parts['sizing_portfolio'])}")
    _say(output, "")


def _print_summary(output: Writer, summary: dict[str, object], out_dir: Path) -> None:
    _say(output, "")
    _say(output, "SIMULATED PRACTICE SUMMARY")
    _say(output, f"Trades: {summary['trade_count']}")
    _say(output, f"Closed trades: {summary['closed_trades']}")
    _say(output, f"Wins: {summary['wins']}")
    _say(output, f"Losses: {summary['losses']}")
    _say(output, f"Flats: {summary['flats']}")
    _say(output, f"Win rate: {_win_rate(summary)}")
    _say(output, f"Realized P&L: {summary['realized_pnl']}")
    _say(output, f"Unrealized P&L: {summary['unrealized_pnl']}")
    _say(output, f"Total P&L: {summary['total_pnl']}")
    _say(output, "Unrealized P&L uses the last supplied close and does not charge an exit fee.")
    _say(output, f"Ending cash: {summary['ending_cash']}")
    _say(output, f"Ending equity: {summary['ending_equity']}")
    positions = summary["open_positions"]
    if isinstance(positions, list) and positions:
        rendered = ", ".join(
            f"{item['shares']} {item['symbol']} @ {item['mark_close']} ({item['mark_date']})"
            for item in positions
        )
        _say(output, f"Open positions: {rendered}")
    else:
        _say(output, "Open positions: none")
    warning = summary["warning"]
    if isinstance(warning, str):
        _say(output, warning)
    _say(output, "")
    _say(output, f"Wrote {out_dir / 'fills.csv'}")
    _say(output, f"Wrote {out_dir / 'fills.jsonl'}")
    _say(output, f"Wrote {out_dir / 'summary.json'}")
    _say(output, "")
    _say(output, DISCLAIMER)


def _win_rate(summary: dict[str, object]) -> str:
    rate = summary["win_rate"]
    closed = summary["closed_trades"]
    if rate is None or closed == 0:
        return "n/a (no closing sells)"
    percent = (Decimal(str(rate)) * Decimal("100")).quantize(Decimal("0.01"))
    return f"{format(percent, 'f')}% of {closed} closing sells"


def _write(out_dir: Path, rows: list[LogRow], summary: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "fills.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv(value) for key, value in row.as_dict().items()})
    with (out_dir / "fills.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.as_dict(), ensure_ascii=False) + "\n")
    with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")


def _load_json(path: Path) -> object:
    if not path.is_file():
        raise PracticeError(f"decision file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        raise PracticeError(f"{path} is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise PracticeError(f"{path} is not valid JSON: {exc.msg}") from exc


def _break_after_prompt(output: Writer) -> None:
    """A piped answer is not echoed, so move to the next line ourselves."""
    import sys

    if not sys.stdin.isatty():
        print(file=output)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _when(intent: OrderIntent) -> str:
    if intent.as_of:
        return f" as of {intent.as_of}"
    return ""


def _say(output: Writer, text: str) -> None:
    print(text, file=output)


def _num(value: object) -> str:
    if isinstance(value, Decimal):
        return format_number(value)
    return str(value)


def _csv(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
