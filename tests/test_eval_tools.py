from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts/run_evals.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("run_evals", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load eval runner module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvalToolTests(unittest.TestCase):
    def test_static_suite_and_context_budget_pass(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", str(RUNNER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        suite = json.loads((REPO_ROOT / "evals/routing-cases.json").read_text())
        self.assertEqual(report["case_count"], len(suite["cases"]))
        self.assertTrue(report["context_weight"]["within_limits"])
        self.assertEqual(report["context_weight"]["on_demand_skill_count"], 5)

    def test_summary_compares_exact_fields(self) -> None:
        runner = load_runner_module()
        baseline = {
            "case_id": "example",
            "variant": "baseline",
            "status": "mismatch",
            "field_matches": {
                "mode": False,
                "skill": False,
                "persistent_governance_artifacts": True,
                "must_pause_before_execution": True,
            },
            "usage": {"input_tokens": 100, "output_tokens": 10},
        }
        treatment = {
            "case_id": "example",
            "variant": "treatment",
            "status": "passed",
            "field_matches": {
                "mode": True,
                "skill": True,
                "persistent_governance_artifacts": True,
                "must_pause_before_execution": True,
            },
            "usage": {"input_tokens": 120, "output_tokens": 8},
        }
        summary = runner.summarize([baseline, treatment])
        self.assertEqual(summary["baseline"]["field_accuracy"], 0.5)
        self.assertEqual(summary["treatment"]["field_accuracy"], 1.0)
        self.assertEqual(summary["comparison"]["field_accuracy_delta"], 0.5)
        self.assertEqual(summary["comparison"]["average_input_tokens_delta"], 20)
        self.assertEqual(summary["comparison"]["average_input_tokens_delta_ratio"], 0.2)

        passing_gate = runner.quality_gate({"summary": summary}, 25)
        self.assertEqual(passing_gate["status"], "passed")
        failing_gate = runner.quality_gate({"summary": summary}, 10)
        self.assertEqual(failing_gate["status"], "failed")


if __name__ == "__main__":
    unittest.main()
