from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".csv", ".txt"}
SKIP_DIRS = {".git", ".pytest_cache", ".venv", "venv", "results", "__pycache__", "build", "dist"}
SKIP_FILES = {"test_public_copy.py"}

def _banned() -> tuple[re.Pattern[str], ...]:
    # Pieces stay split so the guard does not write the blocked phrases.
    return (
        re.compile("Seduma Trade " + "Do" + "jo"),
        re.compile("Do" + "jo"),
        re.compile("Th" + "oth"),
        re.compile("Ph" + "isher"),
        re.compile("Neural " + "Agency"),
        re.compile(r"\b" + "N" + "AE" + r"\b"),
        re.compile("Al" + "paca", re.IGNORECASE),
        re.compile(r"passive[- ]income", re.IGNORECASE),
        re.compile(r"\bprofit\b", re.IGNORECASE),
    )


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.name == "LICENSE" or path.suffix in TEXT_SUFFIXES:
            yield path


def test_public_copy_avoids_forbidden_language() -> None:
    failures: list[str] = []
    for path in _files():
        text = path.read_text(encoding="utf-8")
        for pattern in _banned():
            if pattern.search(text):
                failures.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")
    assert failures == []


def test_runtime_modules_do_not_import_network_clients() -> None:
    pattern = re.compile(
        r"^\s*(?:import|from)\s+(urllib|requests|httpx|socket|aiohttp|http)\b",
        re.MULTILINE,
    )
    failures = []
    for path in (ROOT / "seduma_demo").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            failures.append(str(path.relative_to(ROOT)))
        lowered = text.lower()
        assert "api_key" not in lowered
        assert "apikey" not in lowered
    assert failures == []


def test_readme_has_required_sections_and_links() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Seduma Trade" in readme
    assert "Not a broker or investment adviser." in readme
    assert "does not pick or recommend trades" in readme
    assert "not a prediction of live performance" in readme
    assert "Not investment advice." in readme
    assert "https://payhip.com/b/K7UaW" in readme
    assert "https://quantum-karate.github.io/website/" in readme
    assert "https://github.com/TauricResearch/TradingAgents" in readme
    assert "https://github.com/virattt/ai-hedge-fund" in readme
    assert "python -m seduma_demo run" in readme
    assert "--practice-auto" in readme
    assert "```mermaid" in readme
    lowered = readme.lower()
    for heading in ("60-second quickstart", "how it works", "limits"):
        assert heading in lowered
    assert "## Seduma Trade" in readme
