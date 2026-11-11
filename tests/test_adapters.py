from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from seduma_demo.adapters import get_adapter
from seduma_demo.errors import AdapterError

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_tradingagents_example_shapes() -> None:
    payload = json.loads((EXAMPLES / "tradingagents_decisions.json").read_text(encoding="utf-8"))
    parsed = get_adapter("tradingagents").parse(payload)
    assert [item.side for item in parsed.intents] == ["BUY", "BUY", "HOLD", "BUY", "SELL", "SELL"]
    assert [item.symbol for item in parsed.intents] == ["AAPL", "MSFT", "NVDA", "NVDA", "AAPL", "MSFT"]
    assert parsed.intents[0].share_size == Decimal("10")
    assert parsed.intents[0].as_of == "2024-06-03"
    assert parsed.intents[3].portfolio_percent == Decimal("1")
    assert parsed.intents[2].share_size is None
    assert "not a recommendation" in parsed.intents[5].rationale.lower()
    assert parsed.rejected == []


def test_tradingagents_rating_map_and_legacy_text() -> None:
    parsed = get_adapter("tradingagents").parse(
        {
            "AAPL": {
                "portfolio_decision": {
                    "rating": "Overweight",
                    "executive_summary": "Fixture overweight.",
                    "investment_thesis": "Mapped to a buy for practice.",
                },
                "size": 4,
            },
            "MSFT": {
                "rating": "Underweight",
                "rationale": "Fixture underweight.",
                "position_sizing": "2% of portfolio",
            },
        }
    )
    assert parsed.intents[0].side == "BUY"
    assert parsed.intents[0].share_size == Decimal("4")
    assert parsed.intents[0].notes == ("source rating Overweight mapped to BUY",)
    assert parsed.intents[1].side == "SELL"
    assert parsed.intents[1].portfolio_percent == Decimal("2")
    assert parsed.intents[1].notes == ("source rating Underweight mapped to SELL",)


def test_tradingagents_rendered_rating_and_disagreement() -> None:
    parsed = get_adapter("tradingagents").parse(
        {
            "ticker": "NVDA",
            "final_trade_decision": (
                "**Rating**: Hold\n\n"
                "**Executive Summary**: No change in this fixture.\n"
            ),
        }
    )
    assert parsed.intents[0].side == "HOLD"
    assert "No change" in parsed.intents[0].rationale

    with pytest.raises(AdapterError, match="disagree"):
        get_adapter("tradingagents").parse(
            {
                "ticker": "NVDA",
                "final_trade_decision": (
                    "**Action**: Buy\n\n"
                    "**Reasoning**: Fixture.\n\n"
                    "FINAL TRANSACTION PROPOSAL: **SELL**"
                ),
            }
        )


def test_tradingagents_buy_without_size_is_an_error() -> None:
    with pytest.raises(AdapterError, match="needs a size"):
        get_adapter("tradingagents").parse(
            {
                "ticker": "AAPL",
                "trader_proposal": {"action": "Buy", "reasoning": "Fixture with no size."},
            }
        )


def test_ai_hedge_fund_example_and_cover() -> None:
    payload = json.loads((EXAMPLES / "ai_hedge_fund_decisions.json").read_text(encoding="utf-8"))
    parsed = get_adapter("ai-hedge-fund").parse(payload)
    assert [(item.symbol, item.side, item.share_size) for item in parsed.intents] == [
        ("AAPL", "BUY", Decimal("8")),
        ("NVDA", "BUY", Decimal("2")),
        ("MSFT", "HOLD", None),
    ]
    assert parsed.intents[0].as_of == "2024-06-07"
    assert len(parsed.rejected) == 1
    assert parsed.rejected[0].symbol == "TSLA"
    assert parsed.rejected[0].reason == "short and cover are not simulated"

    cover = get_adapter("ai-hedge-fund").parse(
        {"AMD": {"action": "cover", "quantity": 1, "reasoning": "Fixture cover."}}
    )
    assert cover.intents == []
    assert cover.rejected[0].symbol == "AMD"


def test_ai_hedge_fund_bad_shape_is_an_adapter_error() -> None:
    with pytest.raises(AdapterError, match="must be a JSON object"):
        get_adapter("ai-hedge-fund").parse(["AAPL"])
    with pytest.raises(AdapterError, match="ticker map"):
        get_adapter("ai-hedge-fund").parse({})
    with pytest.raises(AdapterError, match="ticker map"):
        get_adapter("ai-hedge-fund").parse({"hello": "world"})
    with pytest.raises(AdapterError, match="ticker map"):
        get_adapter("ai-hedge-fund").parse({"decisions": [{"action": "buy"}]})


def test_ai_hedge_fund_rejects_unknown_action() -> None:
    with pytest.raises(AdapterError, match="not buy, sell, hold"):
        get_adapter("ai-hedge-fund").parse(
            {"AAPL": {"action": "liquidate", "quantity": 1, "reasoning": "Fixture."}}
        )


def test_generic_example_schema_rules() -> None:
    payload = json.loads((EXAMPLES / "generic_decisions.json").read_text(encoding="utf-8"))
    parsed = get_adapter("generic").parse(payload)
    assert [item.side for item in parsed.intents] == ["BUY", "HOLD", "SELL", "BUY"]
    assert parsed.intents[0].share_size == Decimal("4")

    with pytest.raises(AdapterError, match="unknown fields"):
        get_adapter("generic").parse(
            {
                "decisions": [
                    {
                        "symbol": "AAPL",
                        "side": "BUY",
                        "size": 1,
                        "rationale": "Fixture.",
                        "confidence": 10,
                    }
                ]
            }
        )
    with pytest.raises(AdapterError, match="HOLD size must be 0"):
        get_adapter("generic").parse(
            [{"symbol": "AAPL", "side": "hold", "size": 1, "rationale": "Fixture."}]
        )
    with pytest.raises(AdapterError, match="BUY, SELL, or HOLD"):
        get_adapter("generic").parse(
            [{"symbol": "AAPL", "side": "SHORT", "size": 1, "rationale": "Fixture."}]
        )
