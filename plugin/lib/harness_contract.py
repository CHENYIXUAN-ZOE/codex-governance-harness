"""Shared project Harness contract validation with no third-party dependencies."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

SCHEMA_VERSION = 1
MODES = {"standard", "assured"}
DOMAIN_MODULES = {
    "software",
    "data",
    "research",
    "documents",
    "automation",
    "external-operations",
    "sensitive",
}
AUTHORITY_KEYS = {
    "project",
    "architecture",
    "current_state",
    "decisions",
    "risks",
    "plans",
}
TOP_LEVEL_KEYS = {
    "schema_version",
    "harness_version",
    "project_name",
    "governance_mode",
    "domain_modules",
    "authority",
    "verification",
}
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")


class ContractError(ValueError):
    """Raised when a project Harness contract cannot be loaded or validated."""


def is_external_reference(value: str) -> bool:
    if WINDOWS_ABSOLUTE_PATTERN.match(value) or value.startswith("\\"):
        return False
    parsed = urlparse(value)
    return bool(parsed.scheme and len(parsed.scheme) > 1)


def resolve_local_reference(project_root: Path, value: str) -> Optional[Path]:
    if is_external_reference(value):
        return None
    if WINDOWS_ABSOLUTE_PATTERN.match(value) or value.startswith("\\"):
        raise ContractError(f"authority reference must be relative or a URI: {value}")
    reference = Path(value)
    if reference.is_absolute():
        raise ContractError(f"authority reference must be relative or a URI: {value}")
    root = project_root.resolve()
    resolved = (root / reference).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ContractError(f"authority reference escapes the project root: {value}") from exc
    return resolved


def _require_string(value: Any, field: str, errors: List[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")


def validate_contract(
    data: Any,
    project_root: Optional[Path] = None,
    check_paths: bool = False,
) -> List[str]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["contract must be a JSON object"]

    unknown_top = sorted(set(data) - TOP_LEVEL_KEYS)
    if unknown_top:
        errors.append(f"unknown top-level fields: {', '.join(unknown_top)}")

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    harness_version = data.get("harness_version")
    _require_string(harness_version, "harness_version", errors)
    if isinstance(harness_version, str) and not SEMVER_PATTERN.fullmatch(harness_version):
        errors.append("harness_version must use semantic version syntax")

    project_name = data.get("project_name")
    _require_string(project_name, "project_name", errors)
    if isinstance(project_name, str) and len(project_name) > 200:
        errors.append("project_name must not exceed 200 characters")

    mode = data.get("governance_mode")
    if mode not in MODES:
        errors.append("governance_mode must be standard or assured")

    modules = data.get("domain_modules")
    if not isinstance(modules, list):
        errors.append("domain_modules must be an array")
    else:
        invalid_modules = [item for item in modules if item not in DOMAIN_MODULES]
        if invalid_modules:
            errors.append(f"unknown domain modules: {', '.join(map(str, invalid_modules))}")
        if len(modules) != len(set(map(str, modules))):
            errors.append("domain_modules must not contain duplicates")

    authority = data.get("authority")
    if not isinstance(authority, dict):
        errors.append("authority must be an object")
        authority = {}
    else:
        unknown_authority = sorted(set(authority) - AUTHORITY_KEYS)
        if unknown_authority:
            errors.append(f"unknown authority fields: {', '.join(unknown_authority)}")
        for key, value in authority.items():
            _require_string(value, f"authority.{key}", errors)
            if not isinstance(value, str) or not value.strip() or project_root is None:
                continue
            try:
                resolved = resolve_local_reference(project_root, value)
            except ContractError as exc:
                errors.append(str(exc))
                continue
            if check_paths and resolved is not None and not resolved.exists():
                errors.append(f"authority.{key} does not exist: {value}")
    if not isinstance(authority.get("project"), str) or not authority["project"].strip():
        errors.append("contracts require authority.project")

    verification = data.get("verification")
    commands: Any = None
    if not isinstance(verification, dict):
        errors.append("verification must be an object")
    else:
        unknown_verification = sorted(set(verification) - {"default"})
        if unknown_verification:
            errors.append(f"unknown verification fields: {', '.join(unknown_verification)}")
        commands = verification.get("default")
        if not isinstance(commands, list):
            errors.append("verification.default must be an array")
        else:
            for index, command in enumerate(commands):
                _require_string(command, f"verification.default[{index}]", errors)
            if len(commands) != len(set(map(str, commands))):
                errors.append("verification.default must not contain duplicates")

    if mode == "assured":
        if not isinstance(authority.get("risks"), str) or not authority["risks"].strip():
            errors.append("assured contracts require authority.risks")
        if not isinstance(commands, list) or not commands:
            errors.append("assured contracts require at least one verification command")

    return errors


def load_contract(path: Path) -> Dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load contract {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"contract must be a JSON object: {path}")
    return data


def dump_contract(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def first_existing(project_root: Path, candidates: Iterable[str]) -> Optional[str]:
    for candidate in candidates:
        if (project_root / candidate).exists():
            return candidate
    return None
