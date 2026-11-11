"""Summary of one simulated practice run."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from seduma_demo.constants import DISCLAIMER, MIN_TRADES_FOR_SILENCE, SMALL_SAMPLE_WARNING
from seduma_demo.numbers import format_number
from seduma_demo.models import LogRow
from seduma_demo.prices import PriceBook
from seduma_demo.simulate import Account


def build_summary(
    rows: list[LogRow],
    account: Account,
    prices: PriceBook,
    *,
    starting_cash: Decimal,
    mode: str,
    decision_file: str,
    prices_file: str,
    agent: str,
    slippage_bps: Decimal,
    fee_bps: Decimal,
) -> dict[str, object]:
    trades = [row for row in rows if row.status == "filled" and row.side in {"BUY", "SELL"}]
    closed = [row for row in trades if row.side == "SELL"]
    wins = _count(closed, lambda row: row.realized_pnl is not None and row.realized_pnl > 0)
    losses = _count(closed, lambda row: row.realized_pnl is not None and row.realized_pnl < 0)
    flats = _count(closed, lambda row: row.realized_pnl is not None and row.realized_pnl == 0)
    realized = sum((row.realized_pnl or Decimal("0") for row in closed), Decimal("0"))
    unrealized = Decimal("0")
    open_positions: list[dict[str, str]] = []
    market_value = Decimal("0")
    for symbol, position in sorted(account.positions.items()):
        if position.shares == 0:
            continue
        point = prices.latest(symbol)
        if point is None:
            continue
        value = point.close * position.shares
        market_value += value
        unrealized += value - position.cost
        open_positions.append(
            {
                "symbol": symbol,
                "shares": _num(position.shares),
                "cost": _num(position.cost),
                "mark_date": point.date,
                "mark_close": _num(point.close),
                "market_value": _num(value),
            }
        )
    ending_equity = account.cash + market_value
    total = ending_equity - starting_cash
    small = len(trades) < MIN_TRADES_FOR_SILENCE
    win_rate = None
    if closed:
        win_rate = str((Decimal(wins) / Decimal(len(closed))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
    return {
        "label": "SIMULATED",
        "simulated": True,
        "broker_connection": False,
        "live_trading": False,
        "agent": agent,
        "mode": mode,
        "decision_file": decision_file,
        "prices_file": prices_file,
        "slippage_bps": _num(slippage_bps),
        "fee_bps": _num(fee_bps),
        "slippage": "adverse: buys above the close, sells below the close",
        "trade_count": len(trades),
        "trade_count_basis": "simulated BUY and SELL fills",
        "closed_trades": len(closed),
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate": win_rate,
        "win_rate_basis": "closing sells with positive realized P&L after simulated fees",
        "realized_pnl": _num(realized),
        "unrealized_pnl": _num(unrealized),
        "unrealized_basis": "open shares marked at the last close in the price file, with no exit fee",
        "total_pnl": _num(total),
        "starting_cash": _num(starting_cash),
        "ending_cash": _num(account.cash),
        "ending_equity": _num(ending_equity),
        "open_positions": open_positions,
        "skipped": sum(1 for row in rows if row.status == "skipped"),
        "declined": sum(1 for row in rows if row.status == "declined"),
        "acknowledged_holds": sum(1 for row in rows if row.status == "acknowledged"),
        "unsupported": sum(1 for row in rows if row.status == "unsupported"),
        "small_sample_warning": small,
        "warning": SMALL_SAMPLE_WARNING.format(count=len(trades)) if small else None,
        "disclaimer": DISCLAIMER,
    }


def _count(rows: list[LogRow], predicate) -> int:
    return sum(1 for row in rows if predicate(row))


def _num(value: Decimal) -> str:
    return format_number(value)
