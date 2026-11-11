from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from seduma_demo.numbers import format_number

Side = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True)
class OrderIntent:
    """One normalized practice intent. It is not an order at a broker."""

    symbol: str
    side: Side
    rationale: str
    source: str
    share_size: Decimal | None = None
    portfolio_percent: Decimal | None = None
    as_of: str | None = None
    source_action: str = ""
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RejectedDecision:
    """An action this practice loop will not simulate, such as a short."""

    symbol: str
    source: str
    source_action: str
    rationale: str
    reason: str


@dataclass
class ParseResult:
    intents: list[OrderIntent] = field(default_factory=list)
    rejected: list[RejectedDecision] = field(default_factory=list)


@dataclass
class LogRow:
    """One line in the results log. `simulated` is always true."""

    status: str
    source: str
    symbol: str
    side: str
    source_action: str = ""
    reason: str = ""
    requested_size: Decimal | None = None
    filled_size: Decimal | None = None
    as_of: str = ""
    price_date: str = ""
    reference_close: Decimal | None = None
    fill_price: Decimal | None = None
    fee: Decimal | None = None
    slippage_bps: Decimal | None = None
    fee_bps: Decimal | None = None
    realized_pnl: Decimal | None = None
    cash_after: Decimal | None = None
    position_after: Decimal | None = None
    rationale: str = ""
    approved: bool | None = None
    notes: str = ""
    simulated: bool = True
    label: str = "SIMULATED"

    def as_dict(self) -> dict[str, object]:
        return {
            "label": "SIMULATED",
            "simulated": True,
            "status": self.status,
            "source": self.source,
            "symbol": self.symbol,
            "side": self.side,
            "source_action": self.source_action,
            "requested_size": _num(self.requested_size),
            "filled_size": _num(self.filled_size),
            "as_of": self.as_of,
            "price_date": self.price_date,
            "reference_close": _num(self.reference_close),
            "fill_price": _num(self.fill_price),
            "fee": _num(self.fee),
            "slippage_bps": _num(self.slippage_bps),
            "fee_bps": _num(self.fee_bps),
            "realized_pnl": _num(self.realized_pnl),
            "cash_after": _num(self.cash_after),
            "position_after": _num(self.position_after),
            "approved": self.approved,
            "reason": self.reason,
            "notes": self.notes,
            "rationale": self.rationale,
        }


def _num(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format_number(value)


LOG_FIELDS = list(LogRow("", "", "", "").as_dict().keys())
