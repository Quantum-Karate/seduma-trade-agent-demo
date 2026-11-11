from __future__ import annotations

from seduma_demo.errors import AdapterError
from seduma_demo.models import OrderIntent, ParseResult, RejectedDecision
from seduma_demo.parseutil import (
    clean_text,
    explicit_shares,
    normalize_symbol,
    parse_date,
)

_SUPPORTED = {"buy": "BUY", "sell": "SELL", "hold": "HOLD"}
_UNSUPPORTED = {"short", "cover"}


def parse_ai_hedge_fund(payload: object, source: str = "ai-hedge-fund") -> ParseResult:
    """Read an ai-hedge-fund-style ``{ticker: {action, quantity, reasoning}}`` map.

    The upstream project is not imported. Short and cover are logged and skipped.
    """
    decisions, as_of = _split(payload)
    result = ParseResult()
    for ticker, decision in decisions.items():
        label = str(ticker)
        if not isinstance(decision, dict):
            raise AdapterError(f"{label} must be a JSON object")
        symbol = normalize_symbol(label, label)
        action = decision.get("action")
        if not isinstance(action, str) or not action.strip():
            raise AdapterError(f"{label} is missing an action")
        key = action.strip().lower()
        rationale = clean_text(decision.get("reasoning", decision.get("rationale")), label)
        row_date = parse_date(decision.get("date", decision.get("as_of")), label) or as_of
        if key in _UNSUPPORTED:
            result.rejected.append(
                RejectedDecision(
                    symbol=symbol,
                    source=source,
                    source_action=action.strip(),
                    rationale=rationale,
                    reason="short and cover are not simulated",
                )
            )
            continue
        if key not in _SUPPORTED:
            raise AdapterError(
                f"{label} action {action!r} is not buy, sell, hold, short, or cover"
            )
        side = _SUPPORTED[key]
        shares = explicit_shares(decision)
        if side == "HOLD":
            shares = None
        elif shares is None:
            raise AdapterError(f"{label} {side} needs a quantity")
        elif shares <= 0:
            raise AdapterError(f"{label} {side} quantity must be greater than zero")
        result.intents.append(
            OrderIntent(
                symbol=symbol,
                side=side,  # type: ignore[arg-type]
                rationale=rationale,
                source=source,
                share_size=shares,
                as_of=row_date,
                source_action=action.strip(),
            )
        )
    return result


def _split(payload: object) -> tuple[dict, str | None]:
    if not isinstance(payload, dict):
        raise AdapterError("ai-hedge-fund input must be a JSON object")
    nested = payload.get("decisions")
    if isinstance(nested, dict):
        as_of = parse_date(payload.get("date", payload.get("as_of")), "file")
        return nested, as_of
    if payload and all(isinstance(value, dict) and "action" in value for value in payload.values()):
        return payload, None
    raise AdapterError(
        "ai-hedge-fund input must be {decisions: {TICKER: {action, quantity, reasoning}}} "
        "or a ticker map of those objects"
    )
