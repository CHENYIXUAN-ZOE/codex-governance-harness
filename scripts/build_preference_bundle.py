#!/usr/bin/env python3
"""Build a shareable preference-only archive from an explicit source allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.0"
NAME = f"codex-preference-learning-{VERSION}"
DOCS = ("README.md", "INSTALL_FOR_CODEX.md", "GLOBAL-INSTRUCTIONS.md", "verify_bundle.py")
SKILL_FILES = ("SKILL.md", "agents/openai.yaml", "scripts/preferences.py")


def build(output: Path) -> Path:
    files = {}
    for relative in DOCS:
        files[relative] = (ROOT / "share/preference-learning" / relative).read_bytes()
    for relative in SKILL_FILES:
        files[f"skills/learn-user-preferences/{relative}"] = (
            ROOT / "plugin/skills/learn-user-preferences" / relative
        ).read_bytes()
    for relative, data in files.items():
        if b"/Users/" in data or b"/home/chenyi" in data:
            raise ValueError(f"Machine-specific path in {relative}")
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files["SHA256SUMS.json"] = (json.dumps(checksums, indent=2) + "\n").encode()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{NAME}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, data in sorted(files.items()):
            entry = zipfile.ZipInfo(f"{NAME}/{relative}", date_time=(2026, 9, 20, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    path = build(args.output)
    print(json.dumps({"archive": str(path), "bytes": path.stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
