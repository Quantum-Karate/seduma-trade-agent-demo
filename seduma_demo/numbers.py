"""Display helpers for simulated numbers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# Currency, fees, and P&L are shown to this quantum. Share counts are already
# coarser, so the same rounding does not change them.
DISPLAY_QUANTUM = Decimal("0.00000001")


def format_number(value: Decimal) -> str:
    """Render a Decimal without exponent notation or trailing zeros."""
    quantized = value.quantize(DISPLAY_QUANTUM, rounding=ROUND_HALF_UP)
    if quantized == 0:
        return "0"
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
