#!/usr/bin/env python3
"""Read-only audit for a project Harness contract and its local authorities."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN_ROOT))

from lib.harness_contract import ContractError, load_contract, validate_contract


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit a project Harness without changes.")
    parser.add_argument("project", help="Project root directory")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args(argv)


def audit_project(project_root: Path) -> Dict[str, Any]:
    root = project_root.resolve()
    errors: List[str] = []
    warnings: List[str] = []
    observations: List[str] = []

    if not root.is_dir():
        errors.append(f"project root is not a directory: {root}")
        return {
            "project": str(root),
            "status": "issues",
            "errors": errors,
            "warnings": warnings,
            "observations": observations,
        }

    contract_path = root / ".harness/project.json"
    if not contract_path.exists():
        errors.append("missing .harness/project.json")
        return {
            "project": str(root),
            "status": "issues",
            "errors": errors,
            "warnings": warnings,
            "observations": observations,
        }

    try:
        contract = load_contract(contract_path)
    except ContractError as exc:
        errors.append(str(exc))
        contract = {}

    if contract:
        errors.extend(validate_contract(contract, root, check_paths=True))
        authority = contract.get("authority", {})
        if isinstance(authority, dict):
            by_target: Dict[str, List[str]] = defaultdict(list)
            for key, value in authority.items():
                if isinstance(value, str):
                    by_target[value].append(key)
            for target, keys in sorted(by_target.items()):
                if len(keys) > 1:
                    warnings.append(f"authority target is reused by {', '.join(keys)}: {target}")

        verification = contract.get("verification", {}).get("default", [])
        if contract.get("governance_mode") == "standard" and not verification:
            warnings.append("Standard contract has no default verification commands")

    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        warnings.append("missing root AGENTS.md")
    else:
        line_count = len(agents_path.read_text(encoding="utf-8").splitlines())
        observations.append(f"root AGENTS.md lines: {line_count}")
        if line_count > 150:
            warnings.append("root AGENTS.md exceeds 150 lines; review context weight")

    status = "healthy" if not errors else "issues"
    return {
        "project": str(root),
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "observations": observations,
    }


def render_human(report: Dict[str, Any]) -> str:
    lines = [f"Project Harness audit: {report['status']}", f"Project: {report['project']}"]
    for label in ("errors", "warnings", "observations"):
        values = report[label]
        lines.append(f"{label.capitalize()}: {len(values)}")
        lines.extend(f"- {value}" for value in values)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    report = audit_project(Path(args.project))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report))
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
