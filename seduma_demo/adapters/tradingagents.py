from __future__ import annotations

import re
from decimal import Decimal

from seduma_demo.errors import AdapterError
from seduma_demo.models import OrderIntent, ParseResult
from seduma_demo.parseutil import (
    clean_text,
    map_rating,
    normalize_symbol,
    parse_date,
    sizing_from,
)

_PROPOSAL = re.compile(
    r"FINAL TRANSACTION PROPOSAL:\s*\*\*(BUY|SELL|HOLD)\*\*",
    re.IGNORECASE,
)
_LABELED = re.compile(
    r"\*\*(Rating|Recommendation|Action)\*\*:\s*"
    r"(Buy|Overweight|Hold|Underweight|Sell)\b",
    re.IGNORECASE,
)
_POSITION = re.compile(r"\*\*Position Sizing\*\*:\s*(.+)", re.IGNORECASE)
_REASON = re.compile(
    r"\*\*(Reasoning|Rationale|Executive Summary|Investment Thesis)\*\*:\s*"
    r"(.*?)(?=\n\*\*|\nFINAL TRANSACTION|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def parse_tradingagents(payload: object, source: str = "tradingagents") -> ParseResult:
    """Read TradingAgents-style trader, portfolio, or rendered decision text.

    The upstream project is not imported. See the fixtures in ``examples/``.
    """
    result = ParseResult()
    for label, symbol_hint, item in _iter_items(payload):
        result.intents.append(_parse_item(item, symbol_hint, label, source))
    return result


def _iter_items(payload: object) -> list[tuple[str, str | None, dict]]:
    if isinstance(payload, list):
        return [
            (f"[{index}]", None, _object(item, f"[{index}]"))
            for index, item in enumerate(payload)
        ]
    if not isinstance(payload, dict):
        raise AdapterError("TradingAgents input must be a JSON object or array")
    for key in ("runs", "decisions"):
        if key in payload:
            rows = payload[key]
            if not isinstance(rows, list):
                raise AdapterError(f"{key} must be an array")
            return [
                (f"{key}[{index}]", None, _object(item, f"{key}[{index}]"))
                for index, item in enumerate(rows)
            ]
    if _ticker_map(payload):
        return [
            (str(ticker), str(ticker), _object(item, str(ticker)))
            for ticker, item in payload.items()
        ]
    return [("[0]", None, payload)]


def _ticker_map(payload: dict) -> bool:
    if not payload:
        return False
    reserved = {
        "action",
        "ticker",
        "symbol",
        "trader_proposal",
        "trader",
        "portfolio_decision",
        "portfolio_manager",
        "research_plan",
        "research_manager",
        "final_trade_decision",
        "rating",
        "recommendation",
        "date",
        "runs",
        "decisions",
        "position_sizing",
        "reasoning",
    }
    if reserved.intersection(payload):
        return False
    from seduma_demo.parseutil import is_symbol

    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict) or not is_symbol(key):
            return False
    return True


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise AdapterError(f"{label} must be a JSON object")
    return value


def _parse_item(item: dict, symbol_hint: str | None, label: str, source: str) -> OrderIntent:
    symbol = normalize_symbol(item.get("ticker", item.get("symbol", symbol_hint)), label)
    as_of = parse_date(item.get("date", item.get("trade_date", item.get("as_of"))), label)
    nested, raw_action, rationale, rendered_sizing = _action_fields(item, label)
    side, source_action = map_rating(raw_action, label)
    notes: list[str] = []
    if source_action.lower() in {"overweight", "underweight"}:
        notes.append(f"source rating {source_action} mapped to {side}")
    if side == "HOLD":
        share_size: Decimal | None = None
        percent: Decimal | None = None
    else:
        share_size, percent = sizing_from(item, nested, rendered_sizing, label)
        if share_size is None and percent is None:
            raise AdapterError(
                f"{label} {side} {symbol} needs a size. Add size, quantity, shares, "
                "or position_sizing as '10 shares' or '5% of portfolio'."
            )
        if share_size is not None and share_size <= 0:
            raise AdapterError(f"{label} {side} size must be greater than zero")
        if percent is not None and percent <= 0:
            raise AdapterError(f"{label} {side} percent must be greater than zero")
    return OrderIntent(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        rationale=clean_text(rationale, label),
        source=source,
        share_size=share_size,
        portfolio_percent=percent,
        as_of=as_of,
        source_action=source_action,
        notes=tuple(notes),
    )


def _action_fields(
    item: dict, label: str
) -> tuple[dict | None, object, object, str | None]:
    proposal = item.get("trader_proposal", item.get("trader"))
    portfolio = item.get("portfolio_decision", item.get("portfolio_manager"))
    research = item.get("research_plan", item.get("research_manager"))
    rendered = item.get("final_trade_decision")
    if isinstance(proposal, dict):
        return proposal, proposal.get("action"), proposal.get("reasoning"), None
    if isinstance(portfolio, dict):
        return (
            portfolio,
            portfolio.get("rating"),
            _join(portfolio.get("executive_summary"), portfolio.get("investment_thesis")),
            None,
        )
    if isinstance(research, dict):
        return (
            research,
            research.get("recommendation"),
            _join(research.get("rationale"), research.get("strategic_actions")),
            None,
        )
    if isinstance(rendered, str):
        raw_action, rationale, sizing = _parse_rendered(rendered, label)
        return None, raw_action, rationale, sizing
    if any(key in item for key in ("action", "rating", "recommendation")):
        raw = item.get("action", item.get("rating", item.get("recommendation")))
        rationale = item.get("reasoning")
        if rationale is None:
            rationale = item.get("rationale")
        if rationale is None:
            rationale = _join(item.get("executive_summary"), item.get("investment_thesis"))
        return None, raw, rationale, None
    raise AdapterError(f"{label} has no action, rating, or rendered decision")


def _join(left: object, right: object) -> str:
    parts = [part.strip() for part in (left, right) if isinstance(part, str) and part.strip()]
    return "\n\n".join(parts)


def _parse_rendered(text: str, label: str) -> tuple[str, str, str | None]:
    proposal = _PROPOSAL.search(text)
    labeled = _LABELED.search(text)
    if proposal and labeled:
        proposal_side, _ = map_rating(proposal.group(1), label)
        labeled_side, _ = map_rating(labeled.group(2), label)
        if proposal_side != labeled_side:
            raise AdapterError(f"{label} rendered action and rating disagree")
    if proposal:
        raw_action = proposal.group(1)
    elif labeled:
        raw_action = labeled.group(2)
    else:
        raise AdapterError(
            f"{label} text has no FINAL TRANSACTION PROPOSAL or rating line"
        )
    reasons = [match.group(2).strip() for match in _REASON.finditer(text) if match.group(2).strip()]
    rationale = "\n\n".join(reasons) if reasons else text.strip()
    sizing = _POSITION.search(text)
    return raw_action, rationale, sizing.group(1).strip() if sizing else None
