#!/usr/bin/env python3
"""Validate the evaluation suite or run isolated baseline/treatment comparisons."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = REPO_ROOT / "evals/routing-cases.json"
RESPONSE_SCHEMA = REPO_ROOT / "evals/routing-response.schema.json"
INSTALL_MANAGER = REPO_ROOT / "scripts/manage_install.py"
GLOBAL_AGENTS = REPO_ROOT / "global/AGENTS.md"
PLUGIN_ROOT = REPO_ROOT / "plugin"
EXPECTED_FIELDS = (
    "mode",
    "skill",
    "persistent_governance_artifacts",
    "must_pause_before_execution",
)
VALID_SKILLS = {
    None,
    "governed-project-work",
    "initialize-project-harness",
    "audit-governance-harness",
    "evolve-governance-harness",
    "learn-user-preferences",
}


class EvalError(RuntimeError):
    """Raised when an evaluation cannot be run reliably."""


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate routing evals and report context weight. Use --live for isolated "
            "Codex baseline/treatment model calls."
        )
    )
    parser.add_argument("--live", action="store_true", help="Run Codex model evaluations")
    parser.add_argument(
        "--variant",
        choices=("baseline", "treatment", "both"),
        default="both",
    )
    parser.add_argument(
        "--auth-source",
        help="Existing Codex auth.json copied into ephemeral evaluation homes",
    )
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", help="Optional explicit model passed to codex exec")
    parser.add_argument("--case", action="append", default=[], help="Case ID; repeatable")
    parser.add_argument("--limit", type=int, help="Run only the first N selected cases")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Fail unless treatment is exact and context overhead stays within budget",
    )
    parser.add_argument(
        "--max-input-delta",
        type=float,
        default=1800,
        help="Maximum treatment minus baseline average input tokens for --gate",
    )
    parser.add_argument("--output", help="Optional path for the JSON report")
    return parser.parse_args(argv)


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError(f"cannot load JSON {path}: {exc}") from exc


def validate_suite(data: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["evaluation suite must be an object"]
    if data.get("suite_version") != 1:
        errors.append("suite_version must be 1")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        return [*errors, "cases must be a non-empty array"]
    seen = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{label} must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{label}.id must be a non-empty string")
        elif case_id in seen:
            errors.append(f"duplicate case id: {case_id}")
        else:
            seen.add(case_id)
        if not isinstance(case.get("category"), str) or not case["category"]:
            errors.append(f"{label}.category must be a non-empty string")
        if not isinstance(case.get("task"), str) or not case["task"]:
            errors.append(f"{label}.task must be a non-empty string")
        expected = case.get("expected")
        if not isinstance(expected, dict):
            errors.append(f"{label}.expected must be an object")
            continue
        if set(expected) != set(EXPECTED_FIELDS):
            errors.append(f"{label}.expected fields do not match the routing contract")
        if expected.get("mode") not in {"lite", "standard", "assured"}:
            errors.append(f"{label}.expected.mode is invalid")
        if expected.get("skill") not in VALID_SKILLS:
            errors.append(f"{label}.expected.skill is invalid")
        for field in (
            "persistent_governance_artifacts",
            "must_pause_before_execution",
        ):
            if not isinstance(expected.get(field), bool):
                errors.append(f"{label}.expected.{field} must be boolean")
    return errors


def static_report(suite: Mapping[str, Any]) -> Dict[str, Any]:
    global_text = GLOBAL_AGENTS.read_text(encoding="utf-8")
    skill_files = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
    plugin_files = [path for path in PLUGIN_ROOT.rglob("*") if path.is_file()]
    global_bytes = len(global_text.encode("utf-8"))
    global_words = len(global_text.split())
    return {
        "status": "valid",
        "suite_version": suite["suite_version"],
        "case_count": len(suite["cases"]),
        "context_weight": {
            "always_loaded_global_bytes": global_bytes,
            "always_loaded_global_words": global_words,
            "global_limit_bytes": 8192,
            "global_limit_words": 1200,
            "within_limits": global_bytes <= 8192 and global_words <= 1200,
            "on_demand_skill_count": len(skill_files),
            "on_demand_skill_bytes": sum(path.stat().st_size for path in skill_files),
            "installed_package_files": len(plugin_files),
            "installed_package_bytes": sum(path.stat().st_size for path in plugin_files),
        },
    }


def select_cases(
    suite: Mapping[str, Any],
    selected_ids: Sequence[str],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    cases = list(suite["cases"])
    if selected_ids:
        requested = set(selected_ids)
        cases = [case for case in cases if case["id"] in requested]
        missing = sorted(requested - {case["id"] for case in cases})
        if missing:
            raise EvalError(f"unknown case IDs: {', '.join(missing)}")
    if limit is not None:
        if limit < 1:
            raise EvalError("--limit must be positive")
        cases = cases[:limit]
    return cases


def evaluation_prompt(case: Mapping[str, Any]) -> str:
    return f"""This is a read-only governance routing evaluation.
Do not use tools, inspect files, or make changes.
Classify the user's task using the active Codex instructions and available governance Skills.

Rules for the response:
- `skill` is the exact governance Skill that should guide the task, or null.
- `persistent_governance_artifacts` is true only if the task should create or change
  governance artifacts, not merely because ordinary project files persist.
- `must_pause_before_execution` is true only if an additional authorization or
  high-impact control must be established before performing the requested action.
- Keep `reason` under 300 characters.

User task:
{case["task"]}
"""


def copy_auth(source: Path, codex_home: Path) -> None:
    if not source.is_file():
        raise EvalError(f"auth source does not exist: {source}")
    target = codex_home / "auth.json"
    shutil.copy2(source, target)
    os.chmod(target, 0o600)


def install_treatment(
    codex_home: Path,
    user_home: Path,
    codex_bin: str,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(INSTALL_MANAGER),
            "install",
            "--codex-home",
            str(codex_home),
            "--user-home",
            str(user_home),
            "--codex-bin",
            codex_bin,
            "--apply",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise EvalError(f"cannot install treatment Harness: {result.stdout}{result.stderr}")


def parse_usage(jsonl: str) -> Optional[Dict[str, Any]]:
    usage = None
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and isinstance(event.get("usage"), dict):
            usage = event["usage"]
        item = event.get("item") if isinstance(event, dict) else None
        if isinstance(item, dict) and isinstance(item.get("usage"), dict):
            usage = item["usage"]
    return usage


def run_case(
    case: Mapping[str, Any],
    variant: str,
    codex_home: Path,
    user_home: Path,
    work: Path,
    codex_bin: str,
    model: Optional[str],
) -> Dict[str, Any]:
    output_path = codex_home / f"eval-{variant}-{case['id']}.json"
    arguments = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--output-schema",
        str(RESPONSE_SCHEMA),
        "--output-last-message",
        str(output_path),
        "--json",
        "--cd",
        str(work),
    ]
    if model:
        arguments.extend(("--model", model))
    arguments.append(evaluation_prompt(case))
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(user_home),
            "CODEX_HOME": str(codex_home),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    result = subprocess.run(
        arguments,
        cwd=work,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if result.returncode:
        return {
            "case_id": case["id"],
            "variant": variant,
            "status": "error",
            "error": (result.stderr or result.stdout).strip(),
        }
    try:
        response = load_json(output_path)
    except EvalError as exc:
        return {
            "case_id": case["id"],
            "variant": variant,
            "status": "error",
            "error": str(exc),
        }
    expected = case["expected"]
    fields = {field: response.get(field) == expected[field] for field in EXPECTED_FIELDS}
    return {
        "case_id": case["id"],
        "variant": variant,
        "status": "passed" if all(fields.values()) else "mismatch",
        "expected": expected,
        "response": response,
        "field_matches": fields,
        "usage": parse_usage(result.stdout),
    }


def summarize(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    summaries: Dict[str, Any] = {}
    variants = sorted({str(result["variant"]) for result in results})
    for variant in variants:
        selected = [result for result in results if result["variant"] == variant]
        scored = [result for result in selected if "field_matches" in result]
        usage_samples = [
            result["usage"] for result in selected if isinstance(result.get("usage"), dict)
        ]
        correct_fields = sum(
            sum(bool(value) for value in result["field_matches"].values()) for result in scored
        )
        total_fields = len(scored) * len(EXPECTED_FIELDS)
        averages = {}
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            values = [
                usage[field]
                for usage in usage_samples
                if isinstance(usage.get(field), (int, float))
            ]
            averages[f"average_{field}"] = sum(values) / len(values) if values else None
        summaries[variant] = {
            "cases": len(selected),
            "errors": sum(result["status"] == "error" for result in selected),
            "exact_cases": sum(result["status"] == "passed" for result in selected),
            "exact_case_rate": (
                sum(result["status"] == "passed" for result in selected) / len(selected)
                if selected
                else 0
            ),
            "field_accuracy": correct_fields / total_fields if total_fields else 0,
            "usage": {
                "samples": len(usage_samples),
                **averages,
            },
        }
    if "baseline" in summaries and "treatment" in summaries:
        baseline_input = summaries["baseline"]["usage"]["average_input_tokens"]
        treatment_input = summaries["treatment"]["usage"]["average_input_tokens"]
        input_delta = (
            treatment_input - baseline_input
            if baseline_input is not None and treatment_input is not None
            else None
        )
        summaries["comparison"] = {
            "field_accuracy_delta": (
                summaries["treatment"]["field_accuracy"] - summaries["baseline"]["field_accuracy"]
            ),
            "exact_case_rate_delta": (
                summaries["treatment"]["exact_case_rate"] - summaries["baseline"]["exact_case_rate"]
            ),
            "average_input_tokens_delta": input_delta,
            "average_input_tokens_delta_ratio": (
                input_delta / baseline_input if input_delta is not None and baseline_input else None
            ),
        }
    return summaries


def run_live(
    cases: Sequence[Mapping[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    if not args.auth_source:
        raise EvalError("--live requires --auth-source")
    if shutil.which(args.codex_bin) is None:
        raise EvalError(f"Codex CLI not found: {args.codex_bin}")
    variants = ("baseline", "treatment") if args.variant == "both" else (args.variant,)
    results: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        work = root / "work"
        work.mkdir()
        for variant in variants:
            user_home = root / f"home-{variant}"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            copy_auth(Path(args.auth_source).expanduser(), codex_home)
            if variant == "treatment":
                install_treatment(codex_home, user_home, args.codex_bin)
            for case in cases:
                results.append(
                    run_case(
                        case,
                        variant,
                        codex_home,
                        user_home,
                        work,
                        args.codex_bin,
                        args.model,
                    )
                )
    version_result = subprocess.run(
        [args.codex_bin, "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "environment": {
            "codex_version": version_result.stdout.strip() or "unknown",
            "model": args.model or "default",
            "sandbox": "read-only",
            "ephemeral": True,
        },
        "results": results,
        "summary": summarize(results),
    }


def quality_gate(
    live_report: Mapping[str, Any],
    max_input_delta: float,
) -> Dict[str, Any]:
    summary = live_report.get("summary", {})
    treatment = summary.get("treatment")
    errors: List[str] = []
    if not isinstance(treatment, dict):
        errors.append("treatment results are required")
    else:
        if treatment.get("errors") != 0:
            errors.append("treatment contains evaluation errors")
        if treatment.get("exact_case_rate") != 1.0:
            errors.append("treatment exact-case rate must be 1.0")
        if treatment.get("field_accuracy") != 1.0:
            errors.append("treatment field accuracy must be 1.0")
    comparison = summary.get("comparison")
    observed_delta = None
    if isinstance(comparison, dict):
        observed_delta = comparison.get("average_input_tokens_delta")
        if not isinstance(observed_delta, (int, float)):
            errors.append("comparison input-token delta is unavailable")
        elif observed_delta > max_input_delta:
            errors.append(f"average input-token delta {observed_delta} exceeds {max_input_delta}")
    return {
        "status": "passed" if not errors else "failed",
        "max_input_tokens_delta": max_input_delta,
        "observed_input_tokens_delta": observed_delta,
        "errors": errors,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
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
        if temporary.exists():
            temporary.unlink()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        suite = load_json(CASES_PATH)
        errors = validate_suite(suite)
        if errors:
            raise EvalError("; ".join(errors))
        report: Dict[str, Any] = static_report(suite)
        if not report["context_weight"]["within_limits"]:
            raise EvalError("global context weight exceeds the evaluation budget")
        exit_code = 0
        if args.live:
            cases = select_cases(suite, args.case, args.limit)
            report["live"] = run_live(cases, args)
            if args.gate:
                report["live"]["gate"] = quality_gate(
                    report["live"],
                    args.max_input_delta,
                )
                if report["live"]["gate"]["status"] != "passed":
                    exit_code = 1
        elif args.gate:
            raise EvalError("--gate requires --live")
        if args.output:
            write_report(Path(args.output).expanduser().resolve(), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code
    except (EvalError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
