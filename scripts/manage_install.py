#!/usr/bin/env python3
"""Plan, install, diagnose, and remove the Governance Harness safely."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugin"
GLOBAL_SOURCE = REPO_ROOT / "global/AGENTS.md"
MARKETPLACE_SOURCE = REPO_ROOT / ".agents/plugins/marketplace.json"
STATE_VERSION = 1
STATE_DIRECTORY = "governance-harness"
ACTIVE_STATE = "active-install.json"
START_RE = re.compile(r"<!-- codex-governance-harness:start version=([0-9A-Za-z.-]+) -->")
END_MARKER = "<!-- codex-governance-harness:end -->"
ALLOWED_PACKAGE_ENTRIES = {
    ".codex-plugin",
    "VERSION",
    "lib",
    "schemas",
    "skills",
    "templates",
}
FORBIDDEN_PACKAGE_PARTS = {
    ".git",
    ".ruff_cache",
    "__pycache__",
    "docs",
    "tests",
}


class InstallError(RuntimeError):
    """Raised when installation state cannot be changed safely."""


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Manage the Codex Governance Harness. Install and removal commands are "
            "dry-run by default; pass --apply to mutate the selected Codex home."
        )
    )
    parser.add_argument(
        "command",
        choices=("install", "status", "doctor", "rollback", "uninstall"),
    )
    default_codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    parser.add_argument(
        "--codex-home",
        default=str(default_codex_home),
        help="Codex state root; must already exist",
    )
    parser.add_argument(
        "--user-home",
        default=str(Path.home()),
        help="HOME passed to Codex CLI; use an isolated path for tests",
    )
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply install, rollback, or uninstall after preflight succeeds",
    )
    return parser.parse_args(argv)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def dump_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError(f"expected a JSON object: {path}")
    return data


def validate_target(codex_home: Path, user_home: Path) -> Tuple[Path, Path]:
    resolved_codex = codex_home.expanduser().resolve()
    resolved_user = user_home.expanduser().resolve()
    if not resolved_codex.is_dir():
        raise InstallError(f"CODEX_HOME must already be a directory: {resolved_codex}")
    if not resolved_user.is_dir():
        raise InstallError(f"user home must already be a directory: {resolved_user}")
    if resolved_codex == Path(resolved_codex.anchor):
        raise InstallError("refusing to use a filesystem root as CODEX_HOME")
    if resolved_codex == resolved_user:
        raise InstallError("refusing to use the user home itself as CODEX_HOME")
    if resolved_codex == REPO_ROOT.resolve():
        raise InstallError("refusing to use the source repository as CODEX_HOME")
    return resolved_codex, resolved_user


def managed_region(content: str) -> Optional[Dict[str, Any]]:
    starts = list(START_RE.finditer(content))
    end_count = content.count(END_MARKER)
    if not starts and end_count == 0:
        return None
    if len(starts) != 1 or end_count != 1:
        raise InstallError("global AGENTS.md has partial or duplicate Harness markers")
    start_match = starts[0]
    end_start = content.find(END_MARKER)
    end = end_start + len(END_MARKER)
    if end_start < start_match.start():
        raise InstallError("global AGENTS.md Harness markers are out of order")
    if content[end : end + 1] == "\n":
        end += 1
    return {
        "start": start_match.start(),
        "end": end,
        "version": start_match.group(1),
        "block": content[start_match.start() : end],
    }


def source_info() -> Dict[str, Any]:
    manifest = load_json(PLUGIN_ROOT / ".codex-plugin/plugin.json")
    marketplace = load_json(MARKETPLACE_SOURCE)
    version = (PLUGIN_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if manifest.get("version") != version:
        raise InstallError("plugin manifest version does not match plugin/VERSION")
    plugin_name = manifest.get("name")
    if not isinstance(plugin_name, str) or not plugin_name:
        raise InstallError("plugin manifest name is missing")

    entries = marketplace.get("plugins")
    if not isinstance(entries, list):
        raise InstallError("marketplace plugins must be an array")
    matches = [
        item for item in entries if isinstance(item, dict) and item.get("name") == plugin_name
    ]
    if len(matches) != 1:
        raise InstallError("marketplace must contain the plugin exactly once")
    source_path = matches[0].get("source", {}).get("path")
    if source_path != "./plugin":
        raise InstallError("marketplace plugin source must be ./plugin")

    marketplace_name = marketplace.get("name")
    if not isinstance(marketplace_name, str) or not marketplace_name:
        raise InstallError("marketplace name is missing")

    actual_entries = {path.name for path in PLUGIN_ROOT.iterdir()}
    if actual_entries != ALLOWED_PACKAGE_ENTRIES:
        unexpected = sorted(actual_entries - ALLOWED_PACKAGE_ENTRIES)
        missing = sorted(ALLOWED_PACKAGE_ENTRIES - actual_entries)
        raise InstallError(
            f"plugin package entries differ; unexpected={unexpected}, missing={missing}"
        )
    for path in PLUGIN_ROOT.rglob("*"):
        relative = path.relative_to(PLUGIN_ROOT)
        if FORBIDDEN_PACKAGE_PARTS.intersection(relative.parts):
            raise InstallError(f"forbidden package content: {relative}")

    global_text = GLOBAL_SOURCE.read_text(encoding="utf-8")
    region = managed_region(global_text)
    if region is None or region["start"] != 0:
        raise InstallError("global source must begin with one managed Harness block")
    if global_text[region["end"] :].strip():
        raise InstallError("global source must contain only the managed Harness block")
    if region["version"] != version:
        raise InstallError("global AGENTS block version does not match plugin version")

    return {
        "plugin_name": plugin_name,
        "version": version,
        "marketplace_name": marketplace_name,
        "marketplace_root": str(REPO_ROOT.resolve()),
        "plugin_root": str(PLUGIN_ROOT.resolve()),
        "global_text": global_text,
        "global_block": region["block"],
    }


def codex_environment(codex_home: Path, user_home: Path) -> Dict[str, str]:
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(codex_home)
    environment["HOME"] = str(user_home)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def run_codex(
    codex_bin: str,
    codex_home: Path,
    user_home: Path,
    arguments: Sequence[str],
) -> Dict[str, Any]:
    executable = shutil.which(codex_bin)
    if executable is None:
        raise InstallError(f"Codex CLI not found: {codex_bin}")
    result = subprocess.run(
        [executable, *arguments],
        cwd=codex_home,
        env=codex_environment(codex_home, user_home),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise InstallError(f"Codex CLI failed ({' '.join(arguments)}): {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InstallError(
            f"Codex CLI returned invalid JSON ({' '.join(arguments)}): {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise InstallError("Codex CLI JSON output must be an object")
    return payload


def inspect_cli(
    source: Mapping[str, Any],
    codex_bin: str,
    codex_home: Path,
    user_home: Path,
) -> Dict[str, Any]:
    marketplace_payload = run_codex(
        codex_bin,
        codex_home,
        user_home,
        ("plugin", "marketplace", "list", "--json"),
    )
    plugin_payload = run_codex(
        codex_bin,
        codex_home,
        user_home,
        ("plugin", "list", "--json"),
    )
    marketplaces = marketplace_payload.get("marketplaces", [])
    installed = plugin_payload.get("installed", [])
    marketplace = next(
        (
            item
            for item in marketplaces
            if isinstance(item, dict) and item.get("name") == source["marketplace_name"]
        ),
        None,
    )
    plugin = next(
        (
            item
            for item in installed
            if isinstance(item, dict)
            and item.get("name") == source["plugin_name"]
            and item.get("marketplaceName") == source["marketplace_name"]
        ),
        None,
    )
    return {"marketplace": marketplace, "plugin": plugin}


def agents_install_plan(
    existing: str,
    source_block: str,
) -> Dict[str, Any]:
    region = managed_region(existing)
    if region is None:
        if not existing or existing.endswith("\n\n"):
            separator = ""
        elif existing.endswith("\n"):
            separator = "\n"
        else:
            separator = "\n\n"
        result = existing + separator + source_block
        previous_block = None
    else:
        separator = ""
        previous_block = region["block"]
        result = existing[: region["start"]] + source_block + existing[region["end"] :]
    return {
        "result": result,
        "changed": result != existing,
        "previous_block": previous_block,
        "inserted_separator": separator,
    }


def unified_diff(before: str, after: str, path: Path) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{path}:before",
            tofile=f"{path}:after",
        )
    )


def active_state_path(codex_home: Path) -> Path:
    return codex_home / STATE_DIRECTORY / ACTIVE_STATE


def plan_install(
    source: Mapping[str, Any],
    cli_state: Mapping[str, Any],
    codex_home: Path,
) -> Dict[str, Any]:
    agents_path = codex_home / "AGENTS.md"
    agents_existed = agents_path.exists()
    try:
        existing_agents = agents_path.read_text(encoding="utf-8") if agents_existed else ""
    except UnicodeDecodeError as exc:
        raise InstallError(f"global AGENTS.md is not valid UTF-8: {agents_path}") from exc
    agents = agents_install_plan(existing_agents, source["global_block"])

    marketplace = cli_state.get("marketplace")
    if marketplace is None:
        marketplace_action = "add"
    else:
        marketplace_source = marketplace.get("marketplaceSource", {})
        configured_root = marketplace_source.get("source")
        if Path(str(configured_root)).resolve() != REPO_ROOT.resolve():
            raise InstallError("a marketplace with the managed name points to a different source")
        marketplace_action = "unchanged"

    plugin = cli_state.get("plugin")
    warnings: List[str] = []
    if plugin is None:
        plugin_action = "add"
    else:
        if plugin.get("version") != source["version"]:
            raise InstallError(
                "an installed managed plugin has a different version; upgrades require "
                "an explicit migration"
            )
        plugin_action = "unchanged"
        if plugin.get("enabled") is not True:
            warnings.append("the installed plugin is disabled; preserving the user's choice")

    active_path = active_state_path(codex_home)
    active_exists = active_path.exists()
    changed = agents["changed"] or marketplace_action == "add" or plugin_action == "add"
    if active_exists and changed:
        raise InstallError(
            "an active managed installation exists but has drifted; run doctor and "
            "rollback before reinstalling"
        )

    status = "planned" if changed else "unchanged"
    if not changed and not active_exists:
        status = "already-present-unmanaged"
        warnings.append(
            "all components already exist but no manager state owns them; nothing will be adopted"
        )
    return {
        "status": status,
        "target": {
            "codex_home": str(codex_home),
            "agents": str(agents_path),
            "active_state": str(active_path),
        },
        "source": {
            "version": source["version"],
            "plugin": source["plugin_name"],
            "marketplace": source["marketplace_name"],
            "repository": source["marketplace_root"],
        },
        "actions": {
            "agents": "update"
            if agents["changed"] and agents_existed
            else ("create" if agents["changed"] else "unchanged"),
            "marketplace": marketplace_action,
            "plugin": plugin_action,
        },
        "agents_diff": unified_diff(existing_agents, agents["result"], agents_path),
        "warnings": warnings,
        "_agents_before": existing_agents,
        "_agents_existed": agents_existed,
        "_agents_plan": agents,
        "_active_exists": active_exists,
    }


def public_report(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in data.items() if not key.startswith("_")}


def transaction_paths(codex_home: Path) -> Tuple[str, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transaction_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    directory = codex_home / STATE_DIRECTORY / "transactions" / transaction_id
    return transaction_id, directory, directory / "record.json"


def apply_install(
    plan: Dict[str, Any],
    source: Mapping[str, Any],
    codex_bin: str,
    codex_home: Path,
    user_home: Path,
) -> Dict[str, Any]:
    if plan["status"] in {"unchanged", "already-present-unmanaged"}:
        return public_report(plan)

    transaction_id, transaction_dir, record_path = transaction_paths(codex_home)
    agents_path = codex_home / "AGENTS.md"
    config_path = codex_home / "config.toml"
    agents_changed = plan["_agents_plan"]["changed"]
    config_existed = config_path.exists()
    config_before = config_path.read_text(encoding="utf-8") if config_existed else ""
    marketplace_added = False
    plugin_added = False
    transaction_dir.mkdir(parents=True, exist_ok=False)
    if plan["_agents_existed"]:
        atomic_write(transaction_dir / "AGENTS.before", plan["_agents_before"])
    if config_existed:
        atomic_write(transaction_dir / "config.before.toml", config_before)

    record: Dict[str, Any] = {
        "state_version": STATE_VERSION,
        "status": "pending",
        "transaction_id": transaction_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": source["version"],
        "codex_home": str(codex_home),
        "user_home": str(user_home),
        "repository": source["marketplace_root"],
        "agents": {
            "path": str(agents_path),
            "changed": agents_changed,
            "existed": plan["_agents_existed"],
            "previous_block": plan["_agents_plan"]["previous_block"],
            "inserted_separator": plan["_agents_plan"]["inserted_separator"],
            "installed_block_sha256": sha256_text(source["global_block"]),
            "backup": "AGENTS.before" if plan["_agents_existed"] else None,
        },
        "config": {
            "path": str(config_path),
            "existed": config_existed,
            "backup": "config.before.toml" if config_existed else None,
            "before_sha256": sha256_text(config_before) if config_existed else None,
        },
        "marketplace": {
            "name": source["marketplace_name"],
            "added": False,
        },
        "plugin": {
            "name": source["plugin_name"],
            "added": False,
        },
    }
    atomic_write(record_path, dump_json(record))

    rollback_errors: List[str] = []
    try:
        if agents_changed:
            atomic_write(agents_path, plan["_agents_plan"]["result"])
        if plan["actions"]["marketplace"] == "add":
            run_codex(
                codex_bin,
                codex_home,
                user_home,
                (
                    "plugin",
                    "marketplace",
                    "add",
                    source["marketplace_root"],
                    "--json",
                ),
            )
            marketplace_added = True
            record["marketplace"]["added"] = True
        if plan["actions"]["plugin"] == "add":
            run_codex(
                codex_bin,
                codex_home,
                user_home,
                (
                    "plugin",
                    "add",
                    source["plugin_name"],
                    "--marketplace",
                    source["marketplace_name"],
                    "--json",
                ),
            )
            plugin_added = True
            record["plugin"]["added"] = True
        record["status"] = "installed"
        atomic_write(record_path, dump_json(record))
        atomic_write(active_state_path(codex_home), dump_json(record))
    except Exception as exc:
        if plugin_added:
            try:
                run_codex(
                    codex_bin,
                    codex_home,
                    user_home,
                    (
                        "plugin",
                        "remove",
                        source["plugin_name"],
                        "--marketplace",
                        source["marketplace_name"],
                        "--json",
                    ),
                )
            except InstallError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if marketplace_added:
            try:
                run_codex(
                    codex_bin,
                    codex_home,
                    user_home,
                    (
                        "plugin",
                        "marketplace",
                        "remove",
                        source["marketplace_name"],
                        "--json",
                    ),
                )
            except InstallError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if agents_changed:
            try:
                if plan["_agents_existed"]:
                    atomic_write(agents_path, plan["_agents_before"])
                else:
                    with contextlib.suppress(FileNotFoundError):
                        agents_path.unlink()
            except OSError as rollback_exc:
                rollback_errors.append(f"cannot restore AGENTS.md: {rollback_exc}")
        try:
            if config_existed:
                if not config_path.is_file():
                    rollback_errors.append("config.toml disappeared during rollback")
                elif sha256_text(config_path.read_text(encoding="utf-8")) != sha256_text(
                    config_before
                ):
                    rollback_errors.append("config.toml differs after rollback")
            elif config_path.exists() and config_path.read_text(encoding="utf-8").strip():
                rollback_errors.append("config.toml retained managed state after rollback")
        except (OSError, UnicodeDecodeError) as rollback_exc:
            rollback_errors.append(f"cannot verify config.toml rollback: {rollback_exc}")
        record["status"] = "failed-rolled-back" if not rollback_errors else "failed-residual"
        record["error"] = str(exc)
        record["rollback_errors"] = rollback_errors
        with contextlib.suppress(OSError):
            atomic_write(record_path, dump_json(record))
        if rollback_errors:
            raise InstallError(
                f"installation failed: {exc}; rollback also failed: {'; '.join(rollback_errors)}"
            ) from exc
        raise InstallError(f"installation failed and was rolled back: {exc}") from exc

    result = public_report(plan)
    result["status"] = "installed"
    result["transaction_id"] = transaction_id
    result["state"] = str(active_state_path(codex_home))
    return result


def inspect_status(
    source: Mapping[str, Any],
    cli_state: Mapping[str, Any],
    codex_home: Path,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    agents_path = codex_home / "AGENTS.md"
    region: Optional[Dict[str, Any]] = None
    if agents_path.exists():
        try:
            region = managed_region(agents_path.read_text(encoding="utf-8"))
        except (InstallError, UnicodeDecodeError) as exc:
            errors.append(str(exc))
    if region is None:
        errors.append("managed global AGENTS block is missing")
    elif sha256_text(region["block"]) != sha256_text(source["global_block"]):
        errors.append("managed global AGENTS block differs from this source version")

    marketplace = cli_state.get("marketplace")
    if marketplace is None:
        errors.append("managed marketplace is missing")
    plugin = cli_state.get("plugin")
    if plugin is None:
        errors.append("managed plugin is not installed")
    else:
        if plugin.get("version") != source["version"]:
            errors.append("installed plugin version differs from source")
        if plugin.get("enabled") is not True:
            warnings.append("managed plugin is installed but disabled")

    active_path = active_state_path(codex_home)
    active = None
    if active_path.exists():
        try:
            active = load_json(active_path)
        except InstallError as exc:
            errors.append(str(exc))
    else:
        warnings.append("installation manager has no active state")

    if errors:
        status = "degraded"
    elif active is None:
        status = "present-unmanaged"
    else:
        status = "installed"
    return {
        "status": status,
        "version": source["version"],
        "codex_home": str(codex_home),
        "components": {
            "agents": region is not None,
            "marketplace": marketplace is not None,
            "plugin": plugin is not None,
            "active_state": active is not None,
        },
        "errors": errors,
        "warnings": warnings,
        "_active": active,
    }


def removal_plan(
    source: Mapping[str, Any],
    cli_state: Mapping[str, Any],
    codex_home: Path,
) -> Dict[str, Any]:
    active_path = active_state_path(codex_home)
    if not active_path.exists():
        raise InstallError("no active managed installation to remove")
    active = load_json(active_path)
    if active.get("state_version") != STATE_VERSION:
        raise InstallError("unsupported installation state version")
    if Path(str(active.get("codex_home"))).resolve() != codex_home:
        raise InstallError("installation state belongs to a different CODEX_HOME")
    if active.get("version") != source["version"]:
        raise InstallError(
            "installation state version differs from source; use its matching source"
        )

    agents_state = active.get("agents")
    if not isinstance(agents_state, dict):
        raise InstallError("installation state has no agents record")
    agents_path = codex_home / "AGENTS.md"
    if not agents_path.is_file():
        raise InstallError("managed global AGENTS.md is missing; refusing removal")
    current = agents_path.read_text(encoding="utf-8")
    region = managed_region(current)
    if region is None:
        raise InstallError("managed global AGENTS block is missing; refusing removal")
    if sha256_text(region["block"]) != agents_state.get("installed_block_sha256"):
        raise InstallError("managed global AGENTS block changed; refusing removal")

    previous_block = agents_state.get("previous_block")
    separator = agents_state.get("inserted_separator", "")
    if previous_block is not None:
        restored = current[: region["start"]] + str(previous_block) + current[region["end"] :]
    else:
        removal_start = region["start"]
        if separator:
            separator_start = removal_start - len(separator)
            if separator_start < 0 or current[separator_start:removal_start] != separator:
                raise InstallError("managed AGENTS insertion boundary changed; refusing removal")
            removal_start = separator_start
        restored = current[:removal_start] + current[region["end"] :]

    delete_agents = not agents_state.get("existed") and not restored
    plugin_added = bool(active.get("plugin", {}).get("added"))
    marketplace_added = bool(active.get("marketplace", {}).get("added"))
    plugin_present = cli_state.get("plugin") is not None
    marketplace_present = cli_state.get("marketplace") is not None
    warnings: List[str] = []
    if plugin_added and not plugin_present:
        warnings.append("managed plugin was already absent")
    if marketplace_added and not marketplace_present:
        warnings.append("managed marketplace was already absent")

    return {
        "status": "planned",
        "target": {"codex_home": str(codex_home), "active_state": str(active_path)},
        "actions": {
            "agents": "delete"
            if delete_agents
            else ("update" if restored != current else "unchanged"),
            "plugin": "remove" if plugin_added and plugin_present else "preserve",
            "marketplace": ("remove" if marketplace_added and marketplace_present else "preserve"),
        },
        "agents_diff": unified_diff(current, restored, agents_path),
        "warnings": warnings,
        "_active": active,
        "_agents_current": current,
        "_agents_restored": restored,
        "_delete_agents": delete_agents,
    }


def apply_removal(
    plan: Dict[str, Any],
    source: Mapping[str, Any],
    codex_bin: str,
    codex_home: Path,
    user_home: Path,
    reason: str,
) -> Dict[str, Any]:
    agents_path = codex_home / "AGENTS.md"
    removed_plugin = False
    removed_marketplace = False
    agents_changed = plan["actions"]["agents"] != "unchanged"
    rollback_errors: List[str] = []
    try:
        if agents_changed:
            if plan["_delete_agents"]:
                agents_path.unlink()
            else:
                atomic_write(agents_path, plan["_agents_restored"])
        if plan["actions"]["plugin"] == "remove":
            run_codex(
                codex_bin,
                codex_home,
                user_home,
                (
                    "plugin",
                    "remove",
                    source["plugin_name"],
                    "--marketplace",
                    source["marketplace_name"],
                    "--json",
                ),
            )
            removed_plugin = True
        if plan["actions"]["marketplace"] == "remove":
            run_codex(
                codex_bin,
                codex_home,
                user_home,
                (
                    "plugin",
                    "marketplace",
                    "remove",
                    source["marketplace_name"],
                    "--json",
                ),
            )
            removed_marketplace = True

        active = plan["_active"]
        active["status"] = reason
        active["removed_at"] = datetime.now(timezone.utc).isoformat()
        transaction_id = active.get("transaction_id")
        if transaction_id:
            record_path = (
                codex_home / STATE_DIRECTORY / "transactions" / str(transaction_id) / "record.json"
            )
            atomic_write(record_path, dump_json(active))
        active_state_path(codex_home).unlink()
    except Exception as exc:
        if removed_marketplace:
            try:
                run_codex(
                    codex_bin,
                    codex_home,
                    user_home,
                    (
                        "plugin",
                        "marketplace",
                        "add",
                        source["marketplace_root"],
                        "--json",
                    ),
                )
            except InstallError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if removed_plugin:
            try:
                run_codex(
                    codex_bin,
                    codex_home,
                    user_home,
                    (
                        "plugin",
                        "add",
                        source["plugin_name"],
                        "--marketplace",
                        source["marketplace_name"],
                        "--json",
                    ),
                )
            except InstallError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if agents_changed:
            try:
                atomic_write(agents_path, plan["_agents_current"])
            except OSError as rollback_exc:
                rollback_errors.append(f"cannot restore AGENTS.md: {rollback_exc}")
        if rollback_errors:
            raise InstallError(
                f"removal failed: {exc}; rollback also failed: {'; '.join(rollback_errors)}"
            ) from exc
        raise InstallError(f"removal failed and was rolled back: {exc}") from exc

    result = public_report(plan)
    result["status"] = reason
    return result


def doctor_report(
    source: Mapping[str, Any],
    status: Dict[str, Any],
    cli_state: Mapping[str, Any],
) -> Dict[str, Any]:
    errors = list(status["errors"])
    warnings = list(status["warnings"])
    plugin = cli_state.get("plugin")
    installed_path: Optional[Path] = None
    if plugin is not None and plugin.get("installedPath"):
        installed_path = Path(str(plugin["installedPath"]))
    elif plugin is not None:
        expected = (
            Path(status["codex_home"])
            / "plugins"
            / "cache"
            / source["marketplace_name"]
            / source["plugin_name"]
            / source["version"]
        )
        if expected.exists():
            installed_path = expected

    if installed_path is not None:
        manifest_path = installed_path / ".codex-plugin/plugin.json"
        if not manifest_path.is_file():
            errors.append("installed plugin manifest is missing")
        else:
            try:
                installed_manifest = load_json(manifest_path)
                if installed_manifest.get("version") != source["version"]:
                    errors.append("installed plugin manifest version differs from source")
            except InstallError as exc:
                errors.append(str(exc))
        for path in installed_path.rglob("*"):
            if FORBIDDEN_PACKAGE_PARTS.intersection(path.relative_to(installed_path).parts):
                errors.append(f"installed package contains forbidden path: {path}")
                break

    return {
        "status": "healthy" if not errors else "unhealthy",
        "installation_status": status["status"],
        "version": source["version"],
        "checks": {
            "source_package": "passed",
            "global_agents": "passed" if status["components"]["agents"] else "failed",
            "marketplace": "passed" if status["components"]["marketplace"] else "failed",
            "plugin": "passed" if status["components"]["plugin"] else "failed",
            "active_state": "passed" if status["components"]["active_state"] else "warning",
        },
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        codex_home, user_home = validate_target(
            Path(args.codex_home),
            Path(args.user_home),
        )
        source = source_info()
        cli_state = inspect_cli(source, args.codex_bin, codex_home, user_home)

        if args.command == "install":
            plan = plan_install(source, cli_state, codex_home)
            report = (
                apply_install(
                    plan,
                    source,
                    args.codex_bin,
                    codex_home,
                    user_home,
                )
                if args.apply
                else public_report(plan)
            )
            print(dump_json(report), end="")
            return 0

        if args.command == "status":
            report = inspect_status(source, cli_state, codex_home)
            print(dump_json(public_report(report)), end="")
            return 0 if report["status"] in {"installed", "present-unmanaged"} else 1

        if args.command == "doctor":
            status = inspect_status(source, cli_state, codex_home)
            report = doctor_report(source, status, cli_state)
            print(dump_json(report), end="")
            return 0 if report["status"] == "healthy" else 1

        plan = removal_plan(source, cli_state, codex_home)
        reason = "rolled-back" if args.command == "rollback" else "uninstalled"
        report = (
            apply_removal(
                plan,
                source,
                args.codex_bin,
                codex_home,
                user_home,
                reason,
            )
            if args.apply
            else public_report(plan)
        )
        print(dump_json(report), end="")
        return 0
    except (InstallError, OSError) as exc:
        print(dump_json({"status": "refused", "error": str(exc)}), end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
