"""Simulated fills against a supplied close.

Buys fill above the close by the slippage rate. Sells fill below it.
A fee rate is then applied to the fill notional. Nothing is sent to a broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from seduma_demo.errors import PracticeError
from seduma_demo.models import OrderIntent

BPS = Decimal("10000")
SHARE_QUANTUM = Decimal("0.000001")


@dataclass
class Position:
    shares: Decimal = Decimal("0")
    cost: Decimal = Decimal("0")


@dataclass
class Account:
    cash: Decimal
    positions: dict[str, Position] = field(default_factory=dict)

    def position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position()
        return self.positions[symbol]


@dataclass(frozen=True)
class FillResult:
    status: str
    reason: str
    filled: Decimal
    fill_price: Decimal | None
    fee: Decimal
    realized_pnl: Decimal | None
    notes: tuple[str, ...] = ()


def resolve_shares(intent: OrderIntent, close: Decimal, sizing_portfolio: Decimal) -> Decimal:
    if intent.side == "HOLD":
        return Decimal("0")
    if intent.share_size is not None:
        shares = intent.share_size
    elif intent.portfolio_percent is not None:
        if sizing_portfolio <= 0:
            raise PracticeError("sizing portfolio must be positive to use a percent size")
        if close <= 0:
            raise PracticeError(f"{intent.symbol} close must be positive")
        dollars = sizing_portfolio * intent.portfolio_percent / Decimal("100")
        shares = dollars / close
    else:
        raise PracticeError(f"{intent.symbol} is missing a size")
    return shares.quantize(SHARE_QUANTUM, rounding=ROUND_HALF_UP)


def quote(close: Decimal, side: str, slippage_bps: Decimal) -> Decimal:
    slip = slippage_bps / BPS
    if side == "BUY":
        return close * (Decimal("1") + slip)
    if side == "SELL":
        return close * (Decimal("1") - slip)
    raise PracticeError("HOLD has no fill price")


def apply_fill(
    account: Account,
    *,
    symbol: str,
    side: str,
    shares: Decimal,
    close: Decimal,
    slippage_bps: Decimal,
    fee_bps: Decimal,
) -> FillResult:
    if side == "BUY":
        return _buy(account, symbol, shares, close, slippage_bps, fee_bps)
    if side == "SELL":
        return _sell(account, symbol, shares, close, slippage_bps, fee_bps)
    raise PracticeError("HOLD is not a fill")


def _fee(notional: Decimal, fee_bps: Decimal) -> Decimal:
    return abs(notional) * fee_bps / BPS


def _buy(
    account: Account,
    symbol: str,
    shares: Decimal,
    close: Decimal,
    slippage_bps: Decimal,
    fee_bps: Decimal,
) -> FillResult:
    price = quote(close, "BUY", slippage_bps)
    notional = price * shares
    fee = _fee(notional, fee_bps)
    total = notional + fee
    if total > account.cash:
        return FillResult("skipped", "insufficient cash", Decimal("0"), price, Decimal("0"), None)
    account.cash -= total
    position = account.position(symbol)
    position.shares += shares
    position.cost += total
    return FillResult("filled", "", shares, price, fee, None)


def _sell(
    account: Account,
    symbol: str,
    shares: Decimal,
    close: Decimal,
    slippage_bps: Decimal,
    fee_bps: Decimal,
) -> FillResult:
    position = account.position(symbol)
    price = quote(close, "SELL", slippage_bps)
    if position.shares <= 0:
        return FillResult("skipped", "no open shares", Decimal("0"), price, Decimal("0"), None)
    filled = shares if shares <= position.shares else position.shares
    notes: tuple[str, ...] = ()
    if filled < shares:
        notes = ("clipped to open shares",)
    notional = price * filled
    fee = _fee(notional, fee_bps)
    proceeds = notional - fee
    if proceeds < 0 and account.cash < -proceeds:
        return FillResult(
            "skipped",
            "insufficient cash for sell fee",
            Decimal("0"),
            price,
            Decimal("0"),
            None,
        )
    average = position.cost / position.shares
    realized = proceeds - average * filled
    position.cost -= average * filled
    position.shares -= filled
    if position.shares == 0:
        position.cost = Decimal("0")
    account.cash += proceeds
    return FillResult("filled", "", filled, price, fee, realized, notes)
