#!/usr/bin/env python3
"""Dependency-free structural checks for the Governance Harness source tree."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugin"
REQUIRED = (
    ".agents/plugins/marketplace.json",
    "evals/routing-cases.json",
    "evals/routing-response.schema.json",
    "evals/results/0.1.0-summary.json",
    "global/AGENTS.md",
    "docs/deployment/INSTALLATION-0.1.0.md",
    "plugin/.codex-plugin/plugin.json",
    "plugin/VERSION",
    "plugin/schemas/project-harness.schema.json",
    "plugin/templates/project/AGENTS.md.tmpl",
    "plugin/templates/project/PROJECT.md.tmpl",
    "scripts/manage_install.py",
    "scripts/run_evals.py",
)
FORBIDDEN_MARKERS = ("[TODO", "TODO:", "PLACEHOLDER", "TBD")
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


def check() -> List[str]:
    errors: List[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    try:
        manifest = json.loads((ROOT / "plugin/.codex-plugin/plugin.json").read_text())
        marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        schema = json.loads((ROOT / "plugin/schemas/project-harness.schema.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [*errors, f"JSON parse failure: {exc}"]

    version = (ROOT / "plugin/VERSION").read_text(encoding="utf-8").strip()
    try:
        eval_summary = json.loads((ROOT / f"evals/results/{version}-summary.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [*errors, f"current evaluation summary cannot be read: {exc}"]
    if manifest.get("version") != version:
        errors.append("VERSION does not match plugin manifest version")
    marketplace_plugins = marketplace.get("plugins", [])
    matching_plugins = [
        item
        for item in marketplace_plugins
        if isinstance(item, dict) and item.get("name") == manifest.get("name")
    ]
    if len(matching_plugins) != 1:
        errors.append("local marketplace must contain the plugin exactly once")
    elif matching_plugins[0].get("source", {}).get("path") != "./plugin":
        errors.append("local marketplace plugin source must point to ./plugin")
    if schema.get("properties", {}).get("schema_version", {}).get("const") != 1:
        errors.append("project contract schema_version const must be 1")
    if eval_summary.get("harness_version") != version:
        errors.append("evaluation summary version does not match plugin version")
    if eval_summary.get("gates", {}).get("status") != "passed":
        errors.append("evaluation summary gate is not passed")

    package_entries = {path.name for path in PLUGIN_ROOT.iterdir() if path.name != ".DS_Store"}
    if package_entries != ALLOWED_PACKAGE_ENTRIES:
        errors.append("installable plugin contains missing or unexpected top-level entries")
    for path in PLUGIN_ROOT.rglob("*"):
        if FORBIDDEN_PACKAGE_PARTS.intersection(path.relative_to(PLUGIN_ROOT).parts):
            errors.append(f"forbidden installable package content: {path.relative_to(ROOT)}")

    global_agents = (ROOT / "global/AGENTS.md").read_text(encoding="utf-8")
    if global_agents.count("codex-governance-harness:start") != 1:
        errors.append("global AGENTS start marker must appear exactly once")
    if global_agents.count("codex-governance-harness:end") != 1:
        errors.append("global AGENTS end marker must appear exactly once")

    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in FORBIDDEN_MARKERS:
            if marker in content:
                errors.append(f"forbidden marker {marker!r} in {path.relative_to(ROOT)}")

    for skill_path in sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md")):
        content = skill_path.read_text(encoding="utf-8")
        match = re.match(
            r"^---\nname:\s*([a-z0-9-]+)\ndescription:\s*(.+?)\n---\n",
            content,
            re.DOTALL,
        )
        if not match:
            errors.append(f"invalid Skill frontmatter: {skill_path.relative_to(ROOT)}")
            continue
        name = match.group(1)
        if name != skill_path.parent.name:
            errors.append(f"Skill name does not match folder: {name}")
        openai_yaml = skill_path.parent / "agents/openai.yaml"
        if not openai_yaml.is_file():
            errors.append(f"missing agents/openai.yaml for {name}")
        elif f"${name}" not in openai_yaml.read_text(encoding="utf-8"):
            errors.append(f"openai.yaml default prompt does not mention ${name}")
        for reference in re.findall(r"references/([A-Za-z0-9._/-]+\.md)", content):
            if not (skill_path.parent / "references" / reference).is_file():
                errors.append(f"missing Skill reference for {name}: {reference}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Source check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Source check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
