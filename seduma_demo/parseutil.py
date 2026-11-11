from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from seduma_demo.errors import AdapterError

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHARES = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:shares?)?$", re.IGNORECASE)
_PERCENT = re.compile(r"^(\d+(?:\.\d+)?)\s*%(?:\s+of\s+portfolio)?$", re.IGNORECASE)

_RATING_TO_SIDE = {
    "buy": "BUY",
    "overweight": "BUY",
    "hold": "HOLD",
    "underweight": "SELL",
    "sell": "SELL",
}


def is_symbol(value: str) -> bool:
    return bool(_SYMBOL.fullmatch(value.strip().upper()))


def normalize_symbol(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"{label} is missing a symbol")
    symbol = value.strip().upper()
    if not _SYMBOL.fullmatch(symbol):
        raise AdapterError(f"{label} has unsupported symbol {value!r}")
    return symbol


def parse_date(value: object, label: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise AdapterError(f"{label} date must be YYYY-MM-DD, got {value!r}")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise AdapterError(f"{label} date is not a calendar date: {value}") from exc
    return value


def to_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, Decimal):
        if isinstance(value, bool):
            raise AdapterError(f"{label} must be a number")
        parsed = value
    elif isinstance(value, (int, float, str)):
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise AdapterError(f"{label} must be a number") from exc
    else:
        raise AdapterError(f"{label} must be a number")
    if not parsed.is_finite():
        raise AdapterError(f"{label} must be a finite number")
    return parsed


def clean_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AdapterError(f"{label} rationale must be text")
    text = value.strip()
    if not text:
        raise AdapterError(f"{label} is missing a rationale")
    if len(text) > 2000:
        return text[:2000].rstrip() + "..."
    return text


def map_rating(raw: object, label: str) -> tuple[str, str]:
    if not isinstance(raw, str) or not raw.strip():
        raise AdapterError(f"{label} is missing an action")
    key = raw.strip().lower()
    if key not in _RATING_TO_SIDE:
        raise AdapterError(
            f"{label} action {raw!r} is not Buy, Overweight, Hold, Underweight, or Sell"
        )
    return _RATING_TO_SIDE[key], raw.strip()


def explicit_shares(source: dict) -> Decimal | None:
    for key in ("size", "quantity", "shares"):
        if key in source and source[key] is not None:
            amount = to_decimal(source[key], f"{key}")
            if amount < 0:
                raise AdapterError(f"{key} cannot be negative")
            return amount
    return None


def parse_position_sizing(value: object, label: str) -> tuple[Decimal | None, Decimal | None]:
    if isinstance(value, bool):
        raise AdapterError(f"{label} position sizing must be text or a number")
    if isinstance(value, (int, float, Decimal)):
        amount = to_decimal(value, f"{label} position sizing")
        if amount < 0:
            raise AdapterError(f"{label} position sizing cannot be negative")
        return amount, None
    if not isinstance(value, str):
        raise AdapterError(f"{label} position sizing must be text or a number")
    cleaned = " ".join(value.strip().split())
    shares = _SHARES.fullmatch(cleaned)
    if shares:
        amount = Decimal(shares.group(1))
        return amount, None
    percent = _PERCENT.fullmatch(cleaned)
    if percent:
        amount = Decimal(percent.group(1))
        return None, amount
    raise AdapterError(
        f"{label} position sizing {value!r} is not a share count or a percent. "
        "Use a number, '10 shares', or '5% of portfolio'."
    )


def sizing_from(
    item: dict,
    nested: dict | None,
    rendered_sizing: str | None,
    label: str,
) -> tuple[Decimal | None, Decimal | None]:
    for source in (item, nested):
        if isinstance(source, dict):
            shares = explicit_shares(source)
            if shares is not None:
                return shares, None
    for source in (item, nested):
        if isinstance(source, dict) and source.get("position_sizing") is not None:
            return parse_position_sizing(source["position_sizing"], label)
    if rendered_sizing is not None:
        return parse_position_sizing(rendered_sizing, label)
    return None, None
