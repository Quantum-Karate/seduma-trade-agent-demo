from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "seduma_demo", *args],
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def test_module_quickstart(tmp_path: Path) -> None:
    out = tmp_path / "out"
    completed = _run(
        [
            "run",
            "--agent",
            "tradingagents",
            "--file",
            "examples/tradingagents_decisions.json",
            "--prices",
            "data/prices.csv",
            "--practice-auto",
            "--out",
            str(out),
        ]
    )
    assert completed.returncode == 0, completed.stderr
    assert "SIMULATED FILLS ONLY" in completed.stdout
    assert "SIMULATED PRACTICE SUMMARY" in completed.stdout
    assert "approved (--practice-auto)" in completed.stdout
    assert "[y/n]" not in completed.stdout
    assert "WARNING: fewer than 30 simulated trades" in completed.stdout
    assert "Not a broker or investment adviser." in completed.stdout
    assert "No broker connection" in completed.stdout
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["simulated"] is True
    assert summary["trade_count"] == 5
    assert summary["broker_connection"] is False


def test_confirm_gate_from_the_cli(tmp_path: Path) -> None:
    out = tmp_path / "out"
    completed = _run(
        [
            "run",
            "--agent",
            "generic",
            "--file",
            "examples/generic_decisions.json",
            "--prices",
            "data/prices.csv",
            "--out",
            str(out),
        ],
        stdin="y\nn\ny\nn\n",
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count("[y/n]") == 4
    assert "SIMULATED approve BUY 4 AAPL" in completed.stdout
    assert "declined" in completed.stdout
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "practice-confirm"
    assert summary["trade_count"] == 2
    assert summary["declined"] == 2
    assert summary["live_trading"] is False


def test_eof_without_practice_auto_is_an_error() -> None:
    completed = _run(
        [
            "run",
            "--agent",
            "generic",
            "--file",
            "examples/generic_decisions.json",
            "--out",
            "results-should-not-matter",
        ],
        stdin="",
    )
    assert completed.returncode == 2
    assert "practice-auto" in completed.stderr


def test_bad_hedge_fund_file_is_a_parse_error(tmp_path: Path) -> None:
    decision_file = tmp_path / "not-decisions.json"
    decision_file.write_text('{"hello": "world"}\n', encoding="utf-8")
    completed = _run(
        [
            "run",
            "--agent",
            "ai-hedge-fund",
            "--file",
            str(decision_file),
            "--practice-auto",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert completed.returncode == 2
    assert "ticker map" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "Traceback" not in completed.stdout


def test_missing_file_and_schema() -> None:
    missing = _run(["run", "--agent", "generic", "--file", "examples/missing.json"])
    assert missing.returncode == 2
    assert "not found" in missing.stderr
    schema = _run(["schema"])
    assert schema.returncode == 0
    assert '"decisions"' in schema.stdout
    assert "BUY" in schema.stdout


def test_help_mentions_simulation() -> None:
    completed = _run(["--help"])
    assert completed.returncode == 0
    assert "Simulated fills only" in completed.stdout
    assert "Not a broker or investment adviser." in completed.stdout
