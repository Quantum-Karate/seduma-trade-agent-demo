from __future__ import annotations

from seduma_demo.errors import AdapterError
from seduma_demo.models import OrderIntent, ParseResult
from seduma_demo.parseutil import (
    clean_text,
    explicit_shares,
    normalize_symbol,
    parse_date,
)

_FIELDS = {"symbol", "side", "size", "rationale", "date"}
_SIDES = {"BUY", "SELL", "HOLD"}


def parse_generic(payload: object, source: str = "generic") -> ParseResult:
    """Read the generic decision schema, a bare array, or one decision object."""
    result = ParseResult()
    for index, item in enumerate(_rows(payload)):
        label = f"decisions[{index}]"
        if not isinstance(item, dict):
            raise AdapterError(f"{label} must be a JSON object")
        extra = set(item) - _FIELDS
        if extra:
            names = ", ".join(sorted(str(name) for name in extra))
            raise AdapterError(f"{label} has unknown fields: {names}")
        symbol = normalize_symbol(item.get("symbol"), label)
        side = _side(item.get("side"), label)
        as_of = parse_date(item.get("date"), label)
        rationale = clean_text(item.get("rationale"), label)
        shares = explicit_shares(item)
        if "size" not in item:
            raise AdapterError(f"{label} is missing size")
        if side == "HOLD":
            if shares != 0:
                raise AdapterError(f"{label} HOLD size must be 0")
            shares = None
        elif shares is None or shares <= 0:
            raise AdapterError(f"{label} {side} size must be greater than zero")
        result.intents.append(
            OrderIntent(
                symbol=symbol,
                side=side,  # type: ignore[arg-type]
                rationale=rationale,
                source=source,
                share_size=shares,
                as_of=as_of,
                source_action=side,
            )
        )
    return result


def _rows(payload: object) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "decisions" in payload:
        extra = set(payload) - {"decisions"}
        if extra:
            names = ", ".join(sorted(str(name) for name in extra))
            raise AdapterError(f"unknown fields: {names}")
        rows = payload["decisions"]
        if not isinstance(rows, list):
            raise AdapterError("decisions must be an array")
        return rows
    if isinstance(payload, dict):
        return [payload]
    raise AdapterError(
        "generic input must be {decisions: [...]}, an array, or one decision object"
    )


def _side(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AdapterError(f"{label} side must be BUY, SELL, or HOLD")
    side = value.strip().upper()
    if side not in _SIDES:
        raise AdapterError(f"{label} side must be BUY, SELL, or HOLD")
    return side
