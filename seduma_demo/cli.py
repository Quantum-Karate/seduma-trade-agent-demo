"""Command line for the practice demo. There is no live-trading command."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from seduma_demo.constants import DISCLAIMER
from seduma_demo.errors import PracticeError
from seduma_demo.practice import run_practice

SCHEMA_PATH = Path(__file__).with_name("generic_decision.schema.json")
_BPS_LIMIT = Decimal("10000")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "schema":
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return 0
    try:
        slippage = _bps("slippage-bps", args.slippage_bps)
        fee = _bps("fee-bps", args.fee_bps)
        cash = _cash(args.cash)
        sizing = cash if args.sizing_portfolio is None else _positive(
            "sizing-portfolio", args.sizing_portfolio
        )
        run_practice(
            agent=args.agent,
            decision_file=args.file,
            prices_file=args.prices,
            out_dir=args.out,
            practice_auto=args.practice_auto,
            slippage_bps=slippage,
            fee_bps=fee,
            cash=cash,
            sizing_portfolio=sizing,
        )
    except PracticeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m seduma_demo",
        description=(
            "Seduma Trade practice demo. Simulated fills only. "
            "No broker connection and no live trading."
        ),
        epilog=DISCLAIMER,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run",
        help="Turn a decision file into simulated practice fills",
    )
    run.add_argument(
        "--agent",
        required=True,
        choices=["tradingagents", "ai-hedge-fund", "generic"],
        help="Which decision shape to read",
    )
    run.add_argument("--file", required=True, type=Path, help="Decision JSON file")
    run.add_argument(
        "--prices",
        type=Path,
        default=Path("data/prices.csv"),
        help="Local CSV of date,symbol,close (default: data/prices.csv)",
    )
    run.add_argument(
        "--practice-auto",
        action="store_true",
        help="Approve every intent without a prompt. Fills stay simulated.",
    )
    run.add_argument("--slippage-bps", default="5", help="Adverse slippage in basis points (default: 5)")
    run.add_argument("--fee-bps", default="1", help="Fee in basis points of fill notional (default: 1)")
    run.add_argument("--cash", default="100000", help="Starting simulated cash (default: 100000)")
    run.add_argument(
        "--sizing-portfolio",
        default=None,
        help="Value used only to turn 'N%% of portfolio' into shares. Defaults to --cash.",
    )
    run.add_argument(
        "--out",
        type=Path,
        default=Path("results"),
        help="Directory for fills.csv, fills.jsonl, and summary.json",
    )
    commands.add_parser("schema", help="Print the generic decision JSON schema")
    return parser


def _decimal(flag: str, value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise PracticeError(f"--{flag} must be a number") from exc
    if not parsed.is_finite():
        raise PracticeError(f"--{flag} must be a finite number")
    return parsed


def _bps(flag: str, value: str) -> Decimal:
    parsed = _decimal(flag, value)
    if parsed < 0 or parsed > _BPS_LIMIT:
        raise PracticeError(f"--{flag} must be from 0 to 10000")
    return parsed


def _cash(value: str) -> Decimal:
    parsed = _decimal("cash", value)
    if parsed < 0:
        raise PracticeError("--cash cannot be negative")
    return parsed


def _positive(flag: str, value: str) -> Decimal:
    parsed = _decimal(flag, value)
    if parsed <= 0:
        raise PracticeError(f"--{flag} must be positive")
    return parsed
