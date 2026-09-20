#!/usr/bin/env python3
"""Read-only audit for a project Harness contract and its local authorities."""

from __future__ import annotations

import argparse
import json
import sys
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
    contract_adopted = contract_path.exists() or contract_path.is_symlink()
    if not contract_adopted:
        observations.append("project contract not adopted; only root AGENTS.md is checked")
    else:
        try:
            contract = load_contract(contract_path)
        except (ContractError, UnicodeError) as exc:
            errors.append(str(exc))
        else:
            contract_errors = validate_contract(contract, root, check_paths=True)
            errors.extend(contract_errors)
            if not contract_errors:
                verification = contract["verification"]["default"]
                if contract["governance_mode"] == "standard" and not verification:
                    warnings.append("Standard contract has no default verification commands")

    agents_path = root / "AGENTS.md"
    if not agents_path.exists() and not agents_path.is_symlink():
        if contract_adopted:
            warnings.append("missing root AGENTS.md")
        else:
            observations.append("no root AGENTS.md to check")
    else:
        try:
            line_count = len(agents_path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read root AGENTS.md: {exc}")
        else:
            observations.append(f"root AGENTS.md lines: {line_count}")
            if line_count > 150:
                warnings.append("root AGENTS.md exceeds 150 lines; review context weight")

    status = "issues" if errors else "healthy" if contract_adopted else "not-adopted"
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
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
