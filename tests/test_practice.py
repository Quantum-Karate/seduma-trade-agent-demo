from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from seduma_demo.practice import run_practice

ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path, decisions: object, prices: str, **kwargs: object) -> dict:
    decision_file = tmp_path / "decisions.json"
    price_file = tmp_path / "prices.csv"
    decision_file.write_text(json.dumps(decisions), encoding="utf-8")
    price_file.write_text(prices, encoding="utf-8")
    options = {
        "agent": "generic",
        "decision_file": decision_file,
        "prices_file": price_file,
        "out_dir": tmp_path / "out",
        "practice_auto": True,
        "slippage_bps": Decimal("10"),
        "fee_bps": Decimal("10"),
        "cash": Decimal("10000"),
        "sizing_portfolio": Decimal("10000"),
    }
    options.update(kwargs)
    summary = run_practice(**options)  # type: ignore[arg-type]
    _assert_identity(summary)
    return summary


def _assert_identity(summary: dict) -> None:
    total = Decimal(summary["total_pnl"])
    assert Decimal(summary["ending_equity"]) - Decimal(summary["starting_cash"]) == total
    assert Decimal(summary["realized_pnl"]) + Decimal(summary["unrealized_pnl"]) == total


def test_round_trip_slippage_and_fees(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-01-02,AAPL,100\n2024-01-03,AAPL,110\n"
    decisions = {
        "decisions": [
            {
                "symbol": "AAPL",
                "side": "BUY",
                "size": 10,
                "rationale": "Fixture buy.",
                "date": "2024-01-02",
            },
            {
                "symbol": "AAPL",
                "side": "SELL",
                "size": 10,
                "rationale": "Fixture sell.",
                "date": "2024-01-03",
            },
        ]
    }
    summary = _run(tmp_path, decisions, prices)
    assert summary["trade_count"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 0
    assert summary["realized_pnl"] == "95.8001"
    assert summary["total_pnl"] == "95.8001"
    assert summary["ending_cash"] == "10095.8001"
    assert summary["small_sample_warning"] is True
    assert summary["warning"] == (
        "WARNING: fewer than 30 simulated trades (2 in this run). "
        "A sample this small is not something to read as a result."
    )
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "fills.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["fill_price"] == "100.1"
    assert rows[0]["reference_close"] == "100"
    assert Decimal(rows[0]["fill_price"]) > Decimal(rows[0]["reference_close"])
    assert rows[1]["fill_price"] == "109.89"
    assert Decimal(rows[1]["fill_price"]) < Decimal(rows[1]["reference_close"])
    assert all(row["simulated"] is True and row["label"] == "SIMULATED" for row in rows)
    header = (tmp_path / "out" / "fills.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("label,simulated,status")


def test_entry_price_on_the_decision_is_not_the_fill(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-06-03,AAPL,190\n"
    decisions = {
        "ticker": "AAPL",
        "date": "2024-06-03",
        "trader_proposal": {
            "action": "Buy",
            "reasoning": "The entry_price below is context only.",
            "entry_price": 1,
            "position_sizing": "2 shares",
        },
    }
    summary = _run(
        tmp_path,
        decisions,
        prices,
        agent="tradingagents",
        slippage_bps=Decimal("0"),
        fee_bps=Decimal("0"),
    )
    row = json.loads((tmp_path / "out" / "fills.jsonl").read_text(encoding="utf-8"))
    assert row["fill_price"] == "190"
    assert summary["trade_count"] == 1


def test_no_lookahead_and_missing_price(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-06-01,AAPL,10\n2024-06-10,AAPL,50\n"
    decisions = {
        "decisions": [
            {
                "symbol": "AAPL",
                "side": "BUY",
                "size": 1,
                "rationale": "Uses the close on or before the date.",
                "date": "2024-06-05",
            },
            {
                "symbol": "AAPL",
                "side": "BUY",
                "size": 1,
                "rationale": "No close exists yet.",
                "date": "2024-05-01",
            },
            {
                "symbol": "MSFT",
                "side": "BUY",
                "size": 1,
                "rationale": "Symbol is absent from the sheet.",
                "date": "2024-06-10",
            },
        ]
    }
    summary = _run(tmp_path, decisions, prices, slippage_bps=Decimal("0"), fee_bps=Decimal("0"))
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "fills.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["price_date"] == "2024-06-01"
    assert rows[0]["reference_close"] == "10"
    assert rows[1]["status"] == "skipped"
    assert rows[1]["reason"] == "no price"
    assert rows[2]["status"] == "skipped"
    assert summary["trade_count"] == 1


def test_undated_decision_uses_latest_close(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-06-01,AAPL,10\n2024-06-10,AAPL,50\n"
    decisions = {
        "decisions": [
            {"symbol": "AAPL", "side": "BUY", "size": 1, "rationale": "No date on purpose."}
        ]
    }
    _run(tmp_path, decisions, prices, slippage_bps=Decimal("0"), fee_bps=Decimal("0"))
    row = json.loads((tmp_path / "out" / "fills.jsonl").read_text(encoding="utf-8"))
    assert row["price_date"] == "2024-06-10"
    assert row["reference_close"] == "50"


def test_cash_shortfall_position_clip_and_hold(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-01-02,AAPL,100\n"
    decisions = {
        "decisions": [
            {"symbol": "AAPL", "side": "BUY", "size": 1, "rationale": "Fits.", "date": "2024-01-02"},
            {"symbol": "AAPL", "side": "BUY", "size": 5, "rationale": "Does not fit.", "date": "2024-01-02"},
            {"symbol": "AAPL", "side": "SELL", "size": 9, "rationale": "Clip to the open share.", "date": "2024-01-02"},
            {"symbol": "AAPL", "side": "HOLD", "size": 0, "rationale": "Nothing to do.", "date": "2024-01-02"},
            {"symbol": "AAPL", "side": "SELL", "size": 1, "rationale": "Already flat.", "date": "2024-01-02"},
        ]
    }
    summary = _run(
        tmp_path,
        decisions,
        prices,
        cash=Decimal("150"),
        slippage_bps=Decimal("0"),
        fee_bps=Decimal("0"),
    )
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "fills.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[1]["status"] == "skipped"
    assert rows[1]["reason"] == "insufficient cash"
    assert rows[2]["status"] == "filled"
    assert rows[2]["filled_size"] == "1"
    assert "clipped" in rows[2]["notes"]
    assert rows[3]["status"] == "acknowledged"
    assert rows[3]["filled_size"] == "0"
    assert rows[4]["reason"] == "no open shares"
    assert summary["trade_count"] == 2
    assert summary["acknowledged_holds"] == 1


def test_decline_skips_the_fill(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-01-02,AAPL,100\n"
    decisions = {
        "decisions": [
            {"symbol": "AAPL", "side": "BUY", "size": 1, "rationale": "Ask first.", "date": "2024-01-02"}
        ]
    }
    answers = iter(["n"])
    summary = _run(
        tmp_path,
        decisions,
        prices,
        practice_auto=False,
        input_fn=lambda _prompt: next(answers),
        slippage_bps=Decimal("0"),
        fee_bps=Decimal("0"),
    )
    assert summary["trade_count"] == 0
    assert summary["declined"] == 1
    assert summary["ending_cash"] == "10000"


def test_confirm_rejects_junk_then_accepts(tmp_path: Path, capsys) -> None:
    prices = "date,symbol,close\n2024-01-02,AAPL,100\n"
    decisions = {
        "decisions": [
            {"symbol": "AAPL", "side": "HOLD", "size": 0, "rationale": "Ask twice.", "date": "2024-01-02"}
        ]
    }
    prompts: list[str] = []
    answers = iter(["maybe", "y"])

    def answer(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    summary = _run(tmp_path, decisions, prices, practice_auto=False, input_fn=answer)
    assert prompts == [
        "SIMULATED acknowledge HOLD AAPL (no order)? [y/n] ",
        "SIMULATED acknowledge HOLD AAPL (no order)? [y/n] ",
    ]
    assert summary["acknowledged_holds"] == 1
    assert "Please answer y or n." in capsys.readouterr().out


def test_percent_size_uses_matched_close(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-06-05,NVDA,119.5\n2024-06-07,NVDA,123\n"
    decisions = {
        "ticker": "NVDA",
        "date": "2024-06-05",
        "trader_proposal": {
            "action": "Buy",
            "reasoning": "One percent fixture.",
            "position_sizing": "1% of portfolio",
        },
    }
    summary = _run(
        tmp_path,
        decisions,
        prices,
        agent="tradingagents",
        cash=Decimal("100000"),
        sizing_portfolio=Decimal("100000"),
        slippage_bps=Decimal("5"),
        fee_bps=Decimal("1"),
    )
    row = json.loads((tmp_path / "out" / "fills.jsonl").read_text(encoding="utf-8"))
    assert row["requested_size"] == "8.368201"
    assert row["price_date"] == "2024-06-05"
    assert summary["open_positions"][0]["mark_date"] == "2024-06-07"


def test_thirty_trades_do_not_warn(tmp_path: Path) -> None:
    prices = "date,symbol,close\n2024-01-02,AAPL,1\n"
    decisions = {
        "decisions": [
            {
                "symbol": "AAPL",
                "side": "BUY",
                "size": 1,
                "rationale": f"Fixture buy {index}.",
                "date": "2024-01-02",
            }
            for index in range(30)
        ]
    }
    summary = _run(
        tmp_path,
        decisions,
        prices,
        cash=Decimal("100"),
        slippage_bps=Decimal("0"),
        fee_bps=Decimal("0"),
    )
    assert summary["trade_count"] == 30
    assert summary["small_sample_warning"] is False
    assert summary["warning"] is None
    assert summary["win_rate"] is None


def test_bundled_tradingagents_quickstart(tmp_path: Path) -> None:
    summary = run_practice(
        agent="tradingagents",
        decision_file=ROOT / "examples" / "tradingagents_decisions.json",
        prices_file=ROOT / "data" / "prices.csv",
        out_dir=tmp_path / "out",
        practice_auto=True,
        slippage_bps=Decimal("5"),
        fee_bps=Decimal("1"),
        cash=Decimal("100000"),
        sizing_portfolio=Decimal("100000"),
    )
    _assert_identity(summary)
    assert summary["trade_count"] == 5
    assert summary["closed_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["acknowledged_holds"] == 1
    assert summary["small_sample_warning"] is True
    assert summary["broker_connection"] is False
    assert summary["live_trading"] is False
    assert summary["open_positions"][0]["symbol"] == "NVDA"
    assert summary["open_positions"][0]["shares"] == "8.368201"
    rows = [
        json.loads(line)
        for line in (tmp_path / "out" / "fills.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    money_keys = ("fee", "fill_price", "realized_pnl", "cash_after")
    for row in rows:
        for key in money_keys:
            _assert_at_most_eight_places(row[key])
    for key in ("realized_pnl", "unrealized_pnl", "total_pnl", "ending_cash", "ending_equity"):
        _assert_at_most_eight_places(summary[key])


def _assert_at_most_eight_places(value: object) -> None:
    if not isinstance(value, str) or "." not in value:
        return
    assert len(value.split(".")[1]) <= 8


def test_bundled_hedge_fund_skips_short(tmp_path: Path) -> None:
    summary = run_practice(
        agent="ai-hedge-fund",
        decision_file=ROOT / "examples" / "ai_hedge_fund_decisions.json",
        prices_file=ROOT / "data" / "prices.csv",
        out_dir=tmp_path / "out",
        practice_auto=True,
        slippage_bps=Decimal("5"),
        fee_bps=Decimal("1"),
        cash=Decimal("100000"),
        sizing_portfolio=Decimal("100000"),
    )
    _assert_identity(summary)
    assert summary["trade_count"] == 2
    assert summary["unsupported"] == 1
    assert summary["acknowledged_holds"] == 1


def test_price_comments_and_bad_sheet(tmp_path: Path) -> None:
    from seduma_demo.errors import PriceError
    from seduma_demo.prices import load_prices

    sheet = tmp_path / "prices.csv"
    sheet.write_text(
        "# comment\ndate,symbol,close\n2024-01-02,AAPL,10\n2024-01-02,AAPL,11\n",
        encoding="utf-8",
    )
    book = load_prices(sheet)
    assert book.resolve("AAPL", "2024-01-02").close == Decimal("11")
    sheet.write_text("date,symbol\n2024-01-02,AAPL\n", encoding="utf-8")
    try:
        load_prices(sheet)
    except PriceError as exc:
        assert "date, symbol, close" in str(exc)
    else:
        raise AssertionError("expected a price error")
