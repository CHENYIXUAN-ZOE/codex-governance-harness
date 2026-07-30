#!/usr/bin/env python3
"""Plan or apply a minimal project Harness without overwriting existing files."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PLUGIN_ROOT))

from lib.harness_contract import (
    DOMAIN_MODULES,
    ContractError,
    dump_contract,
    first_existing,
    is_external_reference,
    load_contract,
    resolve_local_reference,
    validate_contract,
)


class InitializationError(RuntimeError):
    """Raised when initialization cannot proceed without unsafe behavior."""


AUTHORITY_CANDIDATES = {
    "architecture": (
        "ARCHITECTURE.md",
        "docs/architecture.md",
        "docs/architecture/README.md",
    ),
    "current_state": (
        "docs/status/NOW.md",
        "STATUS.md",
        "NOW.md",
    ),
    "decisions": (
        "docs/decisions",
        "docs/adr",
        "ADR",
    ),
    "risks": (
        "docs/governance/RISK-REGISTER.md",
        "docs/risk-register.md",
        "RISK.md",
    ),
    "plans": (
        "docs/plans",
        "docs/exec-plans",
        "PLANS.md",
    ),
}

PROJECT_AUTHORITY_CANDIDATES = (
    "PROJECT.md",
    "README.md",
    "README",
    "docs/project.md",
    "docs/product.md",
)

VERIFICATION_CANDIDATES = (
    "scripts/check",
    "scripts/check.sh",
    "scripts/harness_check.sh",
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan a minimal project Harness. The command is dry-run by default; "
            "pass --apply to create missing files."
        )
    )
    parser.add_argument("project", help="Project root directory")
    parser.add_argument(
        "--mode",
        choices=("lite", "standard", "assured"),
        default="standard",
        help="Governance intensity",
    )
    parser.add_argument("--project-name", help="Project display name")
    parser.add_argument(
        "--domain",
        action="append",
        choices=sorted(DOMAIN_MODULES),
        default=[],
        help="Composable project domain module; repeat as needed",
    )
    parser.add_argument(
        "--project-authority",
        help="Existing relative path or URI for the project's purpose and scope",
    )
    parser.add_argument(
        "--project-summary",
        help="Create PROJECT.md with this purpose when no project authority exists",
    )
    parser.add_argument(
        "--risk-authority",
        help="Existing relative path or URI for risks; required for Assured mode",
    )
    parser.add_argument(
        "--verification",
        action="append",
        default=[],
        help="Verification command; repeat as needed",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create planned files after all preflight checks pass",
    )
    return parser.parse_args(argv)


def render_template(path: Path, values: Mapping[str, str]) -> str:
    content = path.read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace("${" + key + "}", value)
    if "${" in content:
        raise InitializationError(f"unresolved template placeholder in {path}")
    return content


def ensure_reference_exists(project_root: Path, value: str, field: str) -> None:
    if is_external_reference(value):
        return
    try:
        resolved = resolve_local_reference(project_root, value)
    except ContractError as exc:
        raise InitializationError(str(exc)) from exc
    if resolved is None or not resolved.exists():
        raise InitializationError(f"{field} does not exist: {value}")


def detect_verification(project_root: Path) -> List[str]:
    found = first_existing(project_root, VERIFICATION_CANDIDATES)
    return [found] if found else []


def build_contract_and_files(
    project_root: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    root = project_root.resolve()
    if not root.is_dir():
        raise InitializationError(f"project root is not a directory: {root}")

    if args.mode == "lite":
        return {
            "mode": "lite",
            "status": "no-persistent-artifacts",
            "project": str(root),
            "writes": {},
            "reused": [],
        }

    project_name = (args.project_name or root.name).strip()
    if not project_name:
        raise InitializationError("project name must not be empty")

    proposed: Dict[Path, str] = {}
    reused: List[str] = []

    project_authority = args.project_authority or first_existing(root, PROJECT_AUTHORITY_CANDIDATES)
    if project_authority:
        ensure_reference_exists(root, project_authority, "project authority")
    elif args.project_summary:
        project_authority = "PROJECT.md"
        proposed[root / project_authority] = render_template(
            PLUGIN_ROOT / "templates/project/PROJECT.md.tmpl",
            {
                "PROJECT_NAME": project_name,
                "PROJECT_SUMMARY": args.project_summary.strip(),
            },
        )
    else:
        raise InitializationError(
            "no project authority found; pass --project-authority or --project-summary"
        )

    authority: Dict[str, str] = {"project": project_authority}
    for key, candidates in AUTHORITY_CANDIDATES.items():
        detected = first_existing(root, candidates)
        if detected:
            authority[key] = detected

    if args.risk_authority:
        ensure_reference_exists(root, args.risk_authority, "risk authority")
        authority["risks"] = args.risk_authority

    verification = list(dict.fromkeys(args.verification or detect_verification(root)))
    if args.mode == "assured":
        if "risks" not in authority:
            raise InitializationError(
                "Assured mode requires --risk-authority or an existing risk authority"
            )
        if not verification:
            raise InitializationError("Assured mode requires at least one --verification command")

    harness_version = (PLUGIN_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    contract = {
        "schema_version": 1,
        "harness_version": harness_version,
        "project_name": project_name,
        "governance_mode": args.mode,
        "domain_modules": list(dict.fromkeys(args.domain)),
        "authority": authority,
        "verification": {"default": verification},
    }
    contract_errors = validate_contract(contract, root, check_paths=False)
    if contract_errors:
        raise InitializationError("; ".join(contract_errors))

    contract_path = root / ".harness/project.json"
    if contract_path.exists():
        existing_contract = load_contract(contract_path)
        if existing_contract != contract:
            raise InitializationError(
                "existing .harness/project.json differs; refusing to overwrite it"
            )
        reused.append(".harness/project.json")
    else:
        proposed[contract_path] = dump_contract(contract)

    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        reused.append("AGENTS.md")
    else:
        proposed[agents_path] = render_template(
            PLUGIN_ROOT / "templates/project/AGENTS.md.tmpl",
            {
                "PROJECT_NAME": project_name,
                "GOVERNANCE_MODE": args.mode,
            },
        )

    for target in proposed:
        if target.exists():
            raise InitializationError(f"refusing to overwrite existing file: {target}")

    return {
        "mode": args.mode,
        "status": "planned",
        "project": str(root),
        "contract": contract,
        "writes": {str(path.relative_to(root)): content for path, content in proposed.items()},
        "reused": sorted(reused),
        "_proposed": proposed,
    }


def atomic_create_many(files: Mapping[Path, str]) -> None:
    staged: Dict[Path, Path] = {}
    committed: List[Path] = []
    created_directories: List[Path] = []
    failed = True
    try:
        for target, content in files.items():
            missing_directories: List[Path] = []
            parent = target.parent
            while not parent.exists():
                missing_directories.append(parent)
                parent = parent.parent
            for directory in reversed(missing_directories):
                directory.mkdir()
                created_directories.append(directory)

            if target.exists():
                raise InitializationError(f"refusing to overwrite existing file: {target}")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=str(target.parent),
            )
            temporary = Path(temporary_name)
            staged[target] = temporary
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

        for target, temporary in staged.items():
            if target.exists():
                raise InitializationError(f"target appeared during apply: {target}")
            os.replace(temporary, target)
            committed.append(target)
        failed = False
    except Exception:
        for target in reversed(committed):
            with contextlib.suppress(FileNotFoundError):
                target.unlink()
        raise
    finally:
        for temporary in staged.values():
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
        if failed:
            for directory in reversed(created_directories):
                with contextlib.suppress(OSError):
                    directory.rmdir()


def public_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in plan.items() if not key.startswith("_")}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        plan = build_contract_and_files(Path(args.project), args)
        if args.apply:
            if plan.get("_proposed"):
                atomic_create_many(plan["_proposed"])
                plan["status"] = "applied"
            elif plan.get("mode") != "lite":
                plan["status"] = "unchanged"
        print(json.dumps(public_plan(plan), ensure_ascii=False, indent=2))
        return 0
    except (InitializationError, ContractError, OSError) as exc:
        print(f"initialization refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
