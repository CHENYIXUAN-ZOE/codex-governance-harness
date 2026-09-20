#!/usr/bin/env python3
"""Check a share bundle and exercise memory only in an isolated temporary home."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_FILES = ("SKILL.md", "agents/openai.yaml", "scripts/preferences.py")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", type=Path, help="Optionally test the installed skill copy")
    args = parser.parse_args()
    require(sys.version_info >= (3, 9), "Python 3.9 or later is required")
    require(sys.platform != "win32", "Use macOS/Linux or Python inside WSL")
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    for relative, expected in manifest.items():
        item = root / relative
        require(not item.is_symlink() and item.resolve().is_relative_to(root), "Unsafe bundle path")
        require(hashlib.sha256(item.read_bytes()).hexdigest() == expected, f"Changed: {relative}")
    skill = args.skill_dir or root / "skills/learn-user-preferences"
    for relative in SKILL_FILES:
        expected = manifest[f"skills/learn-user-preferences/{relative}"]
        require(
            hashlib.sha256((skill / relative).read_bytes()).hexdigest() == expected,
            f"Skill copy differs: {relative}",
        )
    script = skill.resolve() / "scripts/preferences.py"
    with tempfile.TemporaryDirectory(prefix="preference-bundle-check-") as temporary:
        home = Path(temporary) / "isolated-codex"
        home.mkdir()
        project = Path(temporary) / "project-a"
        project.mkdir()
        other = Path(temporary) / "project-b"
        other.mkdir()

        def run(*arguments: str) -> dict:
            result = subprocess.run(
                [sys.executable, "-B", str(script), "--codex-home", str(home), *arguments],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)

        require(run("list")["preferences"] == [], "Fresh store should be empty")
        require(not list(home.iterdir()), "A read must not create storage")

        def record(event: str, context: str) -> dict:
            return run(
                "record",
                "--scope",
                "project",
                "--project",
                str(project),
                "--key",
                "synthetic-check",
                "--category",
                "output",
                "--value",
                "Use a compact table for comparisons.",
                "--when",
                "When comparing options.",
                "--source-summary",
                "Synthetic isolated verifier feedback.",
                "--evidence",
                "correction",
                "--event-id",
                event,
                "--context-id",
                context,
                "--apply",
            )

        require(record("a:1", "a")["preferences"][0]["status"] == "candidate", "Candidate missing")
        require(record("a:2", "a")["preferences"][0]["status"] == "candidate", "Context inflated")
        require(record("b:1", "b")["preferences"][0]["status"] == "promoted", "Promotion missing")
        require(run("list", "--project", str(other))["preferences"] == [], "Project scope leaked")
        require(
            run("list", "--project", str(project))["preferences"][0]["status"] == "promoted",
            "Recall failed",
        )
        run("undo", "--event-id", "undo:1", "--apply")
        require(
            run("list", "--project", str(project))["preferences"][0]["status"] == "candidate",
            "Undo failed",
        )
    print(
        "PASS: file integrity, isolated persistence, independent feedback, scope, recall and undo"
    )
    print("No real user memory was read or modified. Codex skill discovery requires a fresh task.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
