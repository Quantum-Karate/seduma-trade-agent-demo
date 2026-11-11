"""Local close prices. Nothing here is downloaded."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from seduma_demo.errors import AdapterError, PriceError
from seduma_demo.parseutil import is_symbol, parse_date, to_decimal


@dataclass(frozen=True)
class PricePoint:
    date: str
    symbol: str
    close: Decimal


class PriceBook:
    def __init__(self, points: list[PricePoint]) -> None:
        grouped: dict[str, dict[str, PricePoint]] = {}
        for point in points:
            grouped.setdefault(point.symbol, {})[point.date] = point
        self._by_symbol = {
            symbol: [dates[day] for day in sorted(dates)]
            for symbol, dates in grouped.items()
        }

    def resolve(self, symbol: str, as_of: str | None) -> PricePoint | None:
        series = self._by_symbol.get(symbol)
        if not series:
            return None
        if as_of is None:
            return series[-1]
        eligible = [point for point in series if point.date <= as_of]
        if not eligible:
            return None
        return eligible[-1]

    def latest(self, symbol: str) -> PricePoint | None:
        series = self._by_symbol.get(symbol)
        if not series:
            return None
        return series[-1]


def load_prices(path: Path) -> PriceBook:
    if not path.is_file():
        raise PriceError(f"price file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise PriceError(f"{path} is not UTF-8") from exc
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        raise PriceError(f"{path} has no price rows")
    reader = csv.DictReader(lines)
    fieldnames = set(reader.fieldnames or [])
    required = {"date", "symbol", "close"}
    if not required <= fieldnames:
        raise PriceError(f"{path} must include columns: date, symbol, close")
    points: list[PricePoint] = []
    for index, row in enumerate(reader, start=1):
        label = f"{path} price row {index}"
        symbol_raw = (row.get("symbol") or "").strip()
        if not is_symbol(symbol_raw):
            raise PriceError(f"{label} has unsupported symbol {symbol_raw!r}")
        try:
            as_of = parse_date((row.get("date") or "").strip(), label)
            close = to_decimal((row.get("close") or "").strip(), f"{label} close")
        except AdapterError as exc:
            raise PriceError(str(exc)) from exc
        if as_of is None:
            raise PriceError(f"{label} is missing a date")
        if close <= 0:
            raise PriceError(f"{label} close must be positive")
        points.append(PricePoint(date=as_of, symbol=symbol_raw.strip().upper(), close=close))
    if not points:
        raise PriceError(f"{path} has no price rows")
    return PriceBook(points)
