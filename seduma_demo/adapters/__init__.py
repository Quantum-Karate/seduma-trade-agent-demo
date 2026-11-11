"""Decision adapters.

The TradingAgents and ai-hedge-fund parsers accept small fixtures that mimic
those projects' published decision shapes. This package does not depend on
either project.
"""

from __future__ import annotations

from collections.abc import Callable

from seduma_demo.adapters.ai_hedge_fund import parse_ai_hedge_fund
from seduma_demo.adapters.generic import parse_generic
from seduma_demo.adapters.tradingagents import parse_tradingagents
from seduma_demo.errors import AdapterError
from seduma_demo.models import ParseResult

Parser = Callable[[object, str], ParseResult]

_PARSERS: dict[str, Parser] = {
    "tradingagents": parse_tradingagents,
    "ai-hedge-fund": parse_ai_hedge_fund,
    "generic": parse_generic,
}


class Adapter:
    def __init__(self, name: str, parser: Parser) -> None:
        self.name = name
        self._parser = parser

    def parse(self, payload: object) -> ParseResult:
        return self._parser(payload, self.name)


def get_adapter(name: str) -> Adapter:
    parser = _PARSERS.get(name)
    if parser is None:
        known = ", ".join(sorted(_PARSERS))
        raise AdapterError(f"unknown agent {name!r}. Choose one of: {known}")
    return Adapter(name, parser)
