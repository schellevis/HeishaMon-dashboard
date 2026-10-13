"""Lint-level packaging checks (no Docker run): Dockerfile, .dockerignore, build pin."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "backend" / "heishamon_dashboard"


def _dockerfile_lines() -> list[str]:
    # Join backslash continuations so multi-line instructions parse as one.
    text = (ROOT / "Dockerfile").read_text().replace("\\\n", " ")
    return text.splitlines()


def _runtime_copies() -> list[tuple[str, str]]:
    """(sources, destination) of COPY lines in the runtime stage, without --from."""
    copies = []
    in_runtime = False
    for line in _dockerfile_lines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            in_runtime = bool(re.search(r"\bAS\s+runtime\b", stripped, re.I))
        elif in_runtime and stripped.upper().startswith("COPY ") and "--from" not in stripped:
            parts = [p for p in stripped.split()[1:] if not p.startswith("--")]
            copies.append((" ".join(parts[:-1]), parts[-1]))
    return copies


def test_runtime_copies_whole_package_directory():
    copies = _runtime_copies()
    dir_copies = [c for c in copies if c[0] == "backend/heishamon_dashboard/"]
    assert dir_copies, copies
    assert dir_copies[0][1].endswith("/"), dir_copies
    # A directory COPY covers every file under the tree, including later subpackages.
    assert not any("*" in src for src, _ in copies), copies
    assert list(PACKAGE.rglob("*.py")) and list(PACKAGE.rglob("*.json"))


def test_dockerignore_excludes_sensitive_paths():
    entries = {
        line.strip().rstrip("/")
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for needed in (".env", ".git", ".paseo-autopilot", "data", "**/node_modules", ".venv"):
        assert needed in entries or f"{needed}*" in entries, needed
    assert "!.env.example" in entries


def test_every_from_is_pinned_or_marked():
    lines = _dockerfile_lines()
    refs = [i for i, line in enumerate(lines) if re.match(r"\s*(FROM|COPY\s+--from=\S*/\S+)", line)]
    assert refs
    for i in refs:
        block = " ".join(lines[max(0, i - 1) : i + 1])
        assert "@sha256:" in lines[i] or "TODO(release): pin digest" in block, lines[i]


def test_healthcheck_present():
    assert any(line.strip().startswith("HEALTHCHECK") for line in _dockerfile_lines())


def test_hatchling_pinned_exactly():
    requires = tomllib.loads((ROOT / "pyproject.toml").read_text())["build-system"]["requires"]
    assert any(re.fullmatch(r"hatchling==\d+(\.\d+)*", r) for r in requires), requires


def test_frontend_stage_copies_rules_next_to_catalog():
    """The `$catalog` and `$rules` Vite aliases resolve to files under backend/heishamon_dashboard/."""
    copied = []
    in_frontend = False
    for line in _dockerfile_lines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            in_frontend = bool(re.search(r"\bAS\s+frontend\b", stripped, re.I))
        elif in_frontend and stripped.upper().startswith("COPY "):
            parts = [p for p in stripped.split()[1:] if not p.startswith("--")]
            copied.extend((src, parts[-1]) for src in parts[:-1])
    for name in ("catalog.json", "rules.json"):
        assert (f"backend/heishamon_dashboard/{name}", f"/src/backend/heishamon_dashboard/{name}") in copied, copied
