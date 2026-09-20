from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGER = REPO_ROOT / "scripts/manage_install.py"
CODEX_AVAILABLE = shutil.which("codex") is not None


def load_manager_module():
    spec = importlib.util.spec_from_file_location("manage_install", MANAGER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load install manager module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallToolTests(unittest.TestCase):
    def run_manager(
        self,
        command: str,
        codex_home: Path,
        user_home: Path,
        *,
        apply: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
            sys.executable,
            "-B",
            str(MANAGER),
            command,
            "--codex-home",
            str(codex_home),
            "--user-home",
            str(user_home),
        ]
        if apply:
            arguments.append("--apply")
        return subprocess.run(
            arguments,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_finder_metadata_does_not_block_validation_or_get_removed(self) -> None:
        manager = load_manager_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / "plugin"
            shutil.copytree(REPO_ROOT / "plugin", plugin)
            metadata = plugin / ".DS_Store"
            nested_metadata = plugin / "skills/.DS_Store"
            metadata.write_bytes(b"finder metadata")
            nested_metadata.write_bytes(b"nested finder metadata")
            with mock.patch.object(manager, "PLUGIN_ROOT", plugin):
                source = manager.source_info()
                self.assertIn(".DS_Store", source["metadata_files"])
                self.assertIn("skills/.DS_Store", source["metadata_files"])
                self.assertEqual(metadata.read_bytes(), b"finder metadata")
                self.assertEqual(nested_metadata.read_bytes(), b"nested finder metadata")
                (plugin / "unexpected-content").write_text("unexpected", encoding="utf-8")
                with self.assertRaisesRegex(manager.InstallError, "unexpected-content"):
                    manager.source_info()

    @unittest.skipUnless(CODEX_AVAILABLE, "Codex CLI is required")
    def test_dry_run_install_has_no_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            user_home = Path(directory) / "home"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            agents = codex_home / "AGENTS.md"
            original = "# Existing\n"
            agents.write_text(original, encoding="utf-8")

            result = self.run_manager("install", codex_home, user_home)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "planned")
            self.assertEqual(agents.read_text(encoding="utf-8"), original)
            self.assertFalse((codex_home / "config.toml").exists())
            self.assertFalse((codex_home / "governance-harness").exists())

    @unittest.skipUnless(CODEX_AVAILABLE, "Codex CLI is required")
    def test_install_is_idempotent_and_uninstall_restores_agents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            user_home = Path(directory) / "home"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            agents = codex_home / "AGENTS.md"
            original = "# Existing\n\nKeep this.\n"
            agents.write_text(original, encoding="utf-8")
            config = codex_home / "config.toml"
            original_config = "# Existing user configuration\n"
            config.write_text(original_config, encoding="utf-8")

            installed = self.run_manager("install", codex_home, user_home, apply=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            installed_report = json.loads(installed.stdout)
            self.assertEqual(installed_report["status"], "installed")
            state_path = Path(installed_report["state"])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            config_backup = (
                codex_home
                / "governance-harness"
                / "transactions"
                / state["transaction_id"]
                / state["config"]["backup"]
            )
            self.assertEqual(
                config_backup.read_text(encoding="utf-8"),
                original_config,
            )
            before = {
                "agents": agents.read_bytes(),
                "config": config.read_bytes(),
                "state": state_path.read_bytes(),
            }

            doctor = self.run_manager("doctor", codex_home, user_home)
            self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
            self.assertEqual(json.loads(doctor.stdout)["status"], "healthy")

            repeated = self.run_manager("install", codex_home, user_home, apply=True)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            repeated_report = json.loads(repeated.stdout)
            self.assertEqual(repeated_report["status"], "unchanged")
            self.assertFalse(any(key.startswith("_") for key in repeated_report))
            after = {
                "agents": agents.read_bytes(),
                "config": config.read_bytes(),
                "state": state_path.read_bytes(),
            }
            self.assertEqual(after, before)

            removed = self.run_manager("uninstall", codex_home, user_home, apply=True)
            self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            self.assertEqual(agents.read_text(encoding="utf-8"), original)
            self.assertEqual(config.read_text(encoding="utf-8"), original_config)
            self.assertFalse(state_path.exists())
            status = self.run_manager("status", codex_home, user_home)
            self.assertEqual(status.returncode, 1)

    @unittest.skipUnless(CODEX_AVAILABLE, "Codex CLI is required")
    def test_user_edits_outside_managed_block_survive_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            user_home = Path(directory) / "home"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            agents = codex_home / "AGENTS.md"
            original = "# Original\n"
            agents.write_text(original, encoding="utf-8")
            installed = self.run_manager("install", codex_home, user_home, apply=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)

            installed_text = agents.read_text(encoding="utf-8")
            agents.write_text(
                "# Added before\n" + installed_text + "# Added after\n",
                encoding="utf-8",
            )
            removed = self.run_manager("uninstall", codex_home, user_home, apply=True)
            self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            self.assertEqual(
                agents.read_text(encoding="utf-8"),
                "# Added before\n" + original + "# Added after\n",
            )

    @unittest.skipUnless(CODEX_AVAILABLE, "Codex CLI is required")
    def test_removal_preserves_personal_preferences(self) -> None:
        for command in ("uninstall", "rollback"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                user_home = Path(directory) / "home"
                codex_home = user_home / ".codex"
                preference_path = codex_home / "governance-harness/preferences.json"
                preference_path.parent.mkdir(parents=True)
                preferences = b'{"preferences": [{"id": "keep-my-judgment"}]}\n'
                preference_path.write_bytes(preferences)
                installed = self.run_manager("install", codex_home, user_home, apply=True)
                self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
                removed = self.run_manager(command, codex_home, user_home, apply=True)
                self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
                self.assertEqual(preference_path.read_bytes(), preferences)

    @unittest.skipUnless(CODEX_AVAILABLE, "Codex CLI is required")
    def test_tampered_managed_block_refuses_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            user_home = Path(directory) / "home"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            agents = codex_home / "AGENTS.md"
            agents.write_text("# Original\n", encoding="utf-8")
            installed = self.run_manager("install", codex_home, user_home, apply=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            state_path = codex_home / "governance-harness/active-install.json"

            changed = agents.read_text(encoding="utf-8").replace(
                "# Personal Governance Defaults",
                "# Changed Governance Defaults",
            )
            agents.write_text(changed, encoding="utf-8")
            before_config = (codex_home / "config.toml").read_bytes()
            refused = self.run_manager("uninstall", codex_home, user_home, apply=True)
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(json.loads(refused.stdout)["status"], "refused")
            self.assertEqual(agents.read_text(encoding="utf-8"), changed)
            self.assertEqual((codex_home / "config.toml").read_bytes(), before_config)
            self.assertTrue(state_path.exists())

    def test_install_failure_rolls_back_global_agents(self) -> None:
        manager = load_manager_module()
        with tempfile.TemporaryDirectory() as directory:
            user_home = Path(directory) / "home"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            source = manager.source_info()
            plan = manager.plan_install(
                source,
                {"marketplace": None, "plugin": None},
                codex_home,
            )
            calls = []

            def failing_codex(_bin, _codex_home, _user_home, arguments):
                calls.append(tuple(arguments))
                if tuple(arguments[:2]) == ("plugin", "add"):
                    raise manager.InstallError("injected plugin install failure")
                return {}

            with mock.patch.object(manager, "run_codex", side_effect=failing_codex):
                with self.assertRaises(manager.InstallError):
                    manager.apply_install(
                        plan,
                        source,
                        "codex",
                        codex_home,
                        user_home,
                    )

            self.assertFalse((codex_home / "AGENTS.md").exists())
            self.assertFalse((codex_home / "governance-harness/active-install.json").exists())
            self.assertTrue(any(call[:3] == ("plugin", "marketplace", "remove") for call in calls))
            records = list((codex_home / "governance-harness/transactions").glob("*/record.json"))
            self.assertEqual(len(records), 1)
            self.assertEqual(
                json.loads(records[0].read_text(encoding="utf-8"))["status"],
                "failed-rolled-back",
            )

    def test_old_state_without_registration_can_be_removed_before_reinstall(self) -> None:
        manager = load_manager_module()
        with tempfile.TemporaryDirectory() as directory:
            user_home = Path(directory).resolve() / "home"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            source = manager.source_info()
            old_source = dict(source)
            old_source["version"] = "0.1.0"
            old_source["global_block"] = source["global_block"].replace(
                f"version={source['version']}", "version=0.1.0", 1
            )
            agents_path = codex_home / "AGENTS.md"
            agents_path.write_text("# Existing preferences\n", encoding="utf-8")
            config_path = codex_home / "config.toml"
            config = 'model = "user-selected-model"\n'
            config_path.write_text(config, encoding="utf-8")
            plan = manager.plan_install(
                old_source, {"marketplace": None, "plugin": None}, codex_home
            )
            with mock.patch.object(manager, "run_codex", return_value={}):
                manager.apply_install(plan, old_source, "codex", codex_home, user_home)
            agents_path.write_text(
                "# Added before\n" + agents_path.read_text(encoding="utf-8") + "# Added after\n",
                encoding="utf-8",
            )

            removal = manager.removal_plan(
                source, {"marketplace": None, "plugin": None}, codex_home
            )
            self.assertTrue(any("0.1.0" in item for item in removal["warnings"]))
            before = agents_path.read_text(encoding="utf-8")
            agents_path.write_text(
                before.replace("# Personal Governance Defaults", "# Changed rules"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(manager.InstallError, "block changed"):
                manager.removal_plan(source, {"marketplace": None, "plugin": None}, codex_home)
            agents_path.write_text(before, encoding="utf-8")
            with mock.patch.object(manager, "run_codex") as cli:
                manager.apply_removal(
                    removal, source, "codex", codex_home, user_home, "uninstalled"
                )
                cli.assert_not_called()
            self.assertEqual(
                agents_path.read_text(encoding="utf-8"),
                "# Added before\n# Existing preferences\n# Added after\n",
            )
            self.assertEqual(config_path.read_text(encoding="utf-8"), config)
            self.assertFalse(manager.active_state_path(codex_home).exists())
            new_plan = manager.plan_install(
                source, {"marketplace": None, "plugin": None}, codex_home
            )
            self.assertEqual(new_plan["status"], "planned")
            if CODEX_AVAILABLE:
                installed = self.run_manager("install", codex_home, user_home, apply=True)
                self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
                doctor = self.run_manager("doctor", codex_home, user_home)
                self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
                removed = self.run_manager("uninstall", codex_home, user_home, apply=True)
                self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
                self.assertEqual(
                    agents_path.read_text(encoding="utf-8"), removal["_agents_restored"]
                )
                self.assertEqual(config_path.read_text(encoding="utf-8"), config)

    def test_removal_refuses_registered_old_plugin_or_changed_marketplace(self) -> None:
        manager = load_manager_module()
        with tempfile.TemporaryDirectory() as directory:
            user_home = Path(directory).resolve() / "home"
            codex_home = user_home / ".codex"
            codex_home.mkdir(parents=True)
            source = manager.source_info()
            plan = manager.plan_install(source, {"marketplace": None, "plugin": None}, codex_home)
            with mock.patch.object(manager, "run_codex", return_value={}):
                manager.apply_install(plan, source, "codex", codex_home, user_home)
            new_source = dict(source, version="99.0.0")
            plugin_state = {"version": source["version"]}
            with self.assertRaisesRegex(manager.InstallError, "exact old package"):
                manager.removal_plan(
                    new_source, {"marketplace": None, "plugin": plugin_state}, codex_home
                )
            with self.assertRaisesRegex(manager.InstallError, "marketplace source has changed"):
                manager.removal_plan(
                    source,
                    {
                        "marketplace": {"marketplaceSource": {"source": directory}},
                        "plugin": None,
                    },
                    codex_home,
                )

    def test_root_codex_home_is_refused(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(MANAGER),
                "install",
                "--codex-home",
                "/",
                "--user-home",
                "/",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "refused")


if __name__ == "__main__":
    unittest.main()
