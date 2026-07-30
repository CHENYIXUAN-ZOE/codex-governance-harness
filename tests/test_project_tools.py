from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
INITIALIZER = (
    REPO_ROOT
    / "plugin"
    / "skills"
    / "initialize-project-harness"
    / "scripts"
    / "initialize_project.py"
)
AUDITOR = (
    REPO_ROOT / "plugin" / "skills" / "audit-governance-harness" / "scripts" / "audit_project.py"
)
SOURCE_CHECK = REPO_ROOT / "scripts" / "check_source.py"


def load_initializer_module():
    spec = importlib.util.spec_from_file_location("initialize_project", INITIALIZER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load initializer module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProjectToolTests(unittest.TestCase):
    def run_initializer(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(INITIALIZER), str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def run_auditor(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(AUDITOR), str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_lite_mode_creates_no_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_initializer(root, "--mode", "lite", "--apply")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "no-persistent-artifacts")
            self.assertFalse((root / ".harness").exists())
            self.assertFalse((root / "AGENTS.md").exists())

    def test_standard_initialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = (
                "--mode",
                "standard",
                "--domain",
                "software",
                "--project-summary",
                "Build a reliable example service.",
                "--verification",
                "python -m unittest",
                "--apply",
            )
            first = self.run_initializer(root, *arguments)
            self.assertEqual(first.returncode, 0, first.stderr)
            contract_path = root / ".harness/project.json"
            first_contract = contract_path.read_text(encoding="utf-8")
            first_agents = (root / "AGENTS.md").read_text(encoding="utf-8")

            second = self.run_initializer(root, *arguments)
            self.assertEqual(second.returncode, 0, second.stderr)
            second_report = json.loads(second.stdout)
            self.assertEqual(second_report["status"], "unchanged")
            self.assertEqual(second_report["writes"], {})
            self.assertEqual(
                contract_path.read_text(encoding="utf-8"),
                first_contract,
            )
            self.assertEqual(
                (root / "AGENTS.md").read_text(encoding="utf-8"),
                first_agents,
            )

    def test_existing_project_files_are_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Existing\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("keep this exact file\n", encoding="utf-8")

            result = self.run_initializer(
                root,
                "--mode",
                "standard",
                "--domain",
                "documents",
                "--apply",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads((root / ".harness/project.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["authority"]["project"], "README.md")
            self.assertEqual(
                (root / "AGENTS.md").read_text(encoding="utf-8"),
                "keep this exact file\n",
            )

    def test_assured_mode_refuses_missing_controls_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_initializer(
                root,
                "--mode",
                "assured",
                "--project-summary",
                "Handle a high-impact workflow.",
                "--apply",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "PROJECT.md").exists())
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / ".harness").exists())

    def test_assured_mode_accepts_explicit_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Assured\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs/risk.md").write_text("# Risks\n", encoding="utf-8")

            result = self.run_initializer(
                root,
                "--mode",
                "assured",
                "--domain",
                "sensitive",
                "--risk-authority",
                "docs/risk.md",
                "--verification",
                "python -m unittest",
                "--apply",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads((root / ".harness/project.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["authority"]["risks"], "docs/risk.md")
            self.assertEqual(contract["governance_mode"], "assured")

    def test_existing_different_contract_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.run_initializer(
                root,
                "--project-summary",
                "Initial project.",
                "--apply",
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            contract_path = root / ".harness/project.json"
            original = contract_path.read_text(encoding="utf-8")
            (root / "RISK.md").write_text("# Risks\n", encoding="utf-8")

            conflicting = self.run_initializer(
                root,
                "--mode",
                "assured",
                "--risk-authority",
                "RISK.md",
                "--verification",
                "python -m unittest",
                "--apply",
            )
            self.assertNotEqual(conflicting.returncode, 0)
            self.assertEqual(contract_path.read_text(encoding="utf-8"), original)

    def test_authority_cannot_escape_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            outside = Path(directory) / "outside.md"
            outside.write_text("outside\n", encoding="utf-8")
            result = self.run_initializer(
                root,
                "--project-authority",
                "../outside.md",
                "--apply",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / ".harness").exists())

    def test_windows_absolute_authority_is_rejected_on_all_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_initializer(
                root,
                "--project-authority",
                r"C:\external\PROJECT.md",
                "--apply",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / ".harness").exists())

    def test_atomic_apply_rolls_back_partial_commit(self) -> None:
        initializer = load_initializer_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / ".harness" / "first.txt"
            second = root / "second.txt"
            real_replace = initializer.os.replace
            call_count = 0

            def flaky_replace(source, target):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("injected failure")
                return real_replace(source, target)

            with mock.patch.object(initializer.os, "replace", side_effect=flaky_replace):
                with self.assertRaises(OSError):
                    initializer.atomic_create_many(
                        {
                            first: "first\n",
                            second: "second\n",
                        }
                    )

            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertFalse((root / ".harness").exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_audit_detects_missing_authority_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialized = self.run_initializer(
                root,
                "--project-summary",
                "Audited project.",
                "--apply",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            before = sorted(path.relative_to(root) for path in root.rglob("*"))

            healthy = self.run_auditor(root, "--json")
            self.assertEqual(healthy.returncode, 0, healthy.stderr)
            (root / "PROJECT.md").unlink()
            broken = self.run_auditor(root, "--json")
            self.assertEqual(broken.returncode, 1)
            report = json.loads(broken.stdout)
            self.assertTrue(
                any("authority.project does not exist" in item for item in report["errors"])
            )
            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(len(after), len(before) - 1)

    def test_audit_requires_a_project_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialized = self.run_initializer(
                root,
                "--project-summary",
                "Audited project.",
                "--apply",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            contract_path = root / ".harness/project.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            del contract["authority"]["project"]
            contract_path.write_text(json.dumps(contract), encoding="utf-8")

            result = self.run_auditor(root, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertIn("contracts require authority.project", report["errors"])

    def test_source_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SOURCE_CHECK)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
