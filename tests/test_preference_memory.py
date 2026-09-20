from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugin/skills/learn-user-preferences/scripts/preferences.py"
)


class PreferenceMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        self.store = self.home / "governance-harness/preferences.json"

    def call(self, *args: str, success: bool = True) -> dict:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--codex-home", str(self.home), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        return json.loads(result.stdout if success else result.stderr)

    def feedback(
        self,
        event: str = "task-one:turn-one",
        context: str = "task-one",
        evidence: str = "correction",
        command: str = "record",
        value: str = "Lead with the decision and support it with current project evidence.",
        project: Path | None = None,
        apply: bool = True,
        success: bool = True,
    ) -> dict:
        arguments = [
            command,
            "--scope",
            "project" if project else "global",
            "--key",
            "evidence-based-judgment",
            "--category",
            "workflow",
            "--value",
            value,
            "--when",
            "When evaluating a recommendation.",
            "--source-summary",
            "The user corrected an unsupported change of recommendation.",
            "--evidence",
            evidence,
            "--event-id",
            event,
            "--context-id",
            context,
        ]
        if project:
            arguments.extend(("--project", str(project)))
        if apply:
            arguments.append("--apply")
        return self.call(*arguments, success=success)

    def test_missing_read_and_preview_do_not_write(self) -> None:
        self.assertEqual(self.call("list")["preferences"], [])
        preview = self.feedback(apply=False)
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(preview["preferences"][0]["status"], "candidate")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_two_independent_corrections_promote_but_repeated_turns_do_not(self) -> None:
        first = self.feedback()
        self.assertEqual(first["preferences"][0]["status"], "candidate")
        second_turn = self.feedback(event="task-one:turn-two")
        self.assertEqual(second_turn["preferences"][0]["status"], "candidate")
        self.assertEqual(second_turn["preferences"][0]["evidence_count"], 1)
        independent = self.feedback(event="task-two:turn-one", context="task-two")
        self.assertEqual(independent["preferences"][0]["status"], "promoted")
        self.assertEqual(independent["preferences"][0]["evidence_count"], 2)
        # Fresh CLI process observes the durable result; event/context text is minimized.
        self.assertEqual(self.call("list")["preferences"][0]["status"], "promoted")
        self.assertNotIn("task-two", self.store.read_text())

    def test_inferences_do_not_promote_and_explicit_feedback_can(self) -> None:
        self.feedback(evidence="inferred")
        inferred = self.feedback(event="task-two:turn-one", context="task-two", evidence="inferred")
        self.assertEqual(inferred["preferences"][0]["status"], "candidate")
        explicit = self.feedback(event="task-two:turn-two", context="task-two", evidence="explicit")
        self.assertEqual(explicit["preferences"][0]["status"], "explicit")
        self.assertEqual(explicit["preferences"][0]["evidence_count"], 2)

    def test_retry_is_idempotent_and_changed_event_meaning_is_refused(self) -> None:
        self.feedback()
        before = self.store.read_bytes()
        retry = self.feedback()
        self.assertEqual(retry["status"], "unchanged")
        self.assertEqual(self.store.read_bytes(), before)
        self.feedback(evidence="explicit", success=False)
        self.assertEqual(self.store.read_bytes(), before)

    def test_scope_isolation_including_identical_keys_and_canonical_paths(self) -> None:
        project_a, project_b = self.root / "a", self.root / "b"
        project_a.mkdir()
        project_b.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(project_a, target_is_directory=True)
        self.feedback(event="global", evidence="explicit")
        self.feedback(event="a", project=project_a)
        self.feedback(event="b", project=project_b)
        self.assertEqual(len(self.call("list")["preferences"]), 1)
        records = self.call("list", "--project", str(alias))["preferences"]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["scope"]["root"], str(project_a.resolve()))
        self.assertNotIn(str(project_b.resolve()), json.dumps(records))

    def test_routine_output_excludes_unrelated_projects_and_source_history(self) -> None:
        project = self.root / "project"
        project.mkdir()
        self.feedback(event="project-feedback", project=project)
        update = self.feedback(event="global-feedback", evidence="explicit")
        self.assertEqual(len(update["preferences"]), 1)
        self.assertEqual(update["preferences"][0]["scope"], {"kind": "global"})
        self.assertNotIn("sources", update["preferences"][0])
        self.assertNotIn("sources", self.call("list")["preferences"][0])
        self.assertIn("sources", self.call("list", "--details")["preferences"][0])
        undo = self.call("undo", "--event-id", "undo-output-check", "--apply")
        self.assertNotIn("preferences", undo)

    def test_replacement_resets_evidence_and_disable_is_reversible(self) -> None:
        self.feedback(evidence="explicit")
        self.feedback(event="changed", value="Keep initial recommendations concise.", success=False)
        corrected = self.feedback(
            event="corrected", command="replace", value="Keep initial recommendations concise."
        )
        self.assertEqual(corrected["preferences"][0]["status"], "candidate")
        disabled = self.call(
            "disable",
            "--scope",
            "global",
            "--key",
            "evidence-based-judgment",
            "--event-id",
            "stop",
            "--apply",
        )
        self.assertFalse(disabled["preferences"][0]["active"])
        self.assertEqual(self.call("list")["preferences"], [])
        self.assertEqual(len(self.call("list", "--all")["preferences"]), 1)
        self.feedback(event="revive", success=False)
        preview = self.call("undo", "--event-id", "undo-stop")
        self.assertEqual(preview["status"], "preview")
        self.assertEqual(self.call("list")["preferences"], [])
        self.call("undo", "--event-id", "undo-stop", "--apply")
        self.assertEqual(
            self.call("list")["preferences"][0]["value"], "Keep initial recommendations concise."
        )

    def test_undo_initial_write_preserves_event_deduplication(self) -> None:
        self.feedback()
        self.call("undo", "--event-id", "undo-first", "--apply")
        self.assertEqual(self.call("list")["preferences"], [])
        self.assertEqual(self.feedback()["status"], "unchanged")
        self.assertEqual(self.call("list")["preferences"], [])
        before = self.store.read_bytes()
        self.call("undo", "--event-id", "undo-again", "--apply", success=False)
        self.assertEqual(self.store.read_bytes(), before)

    def test_unsafe_topics_and_secret_summaries_are_rejected_before_writing(self) -> None:
        for value in (
            "Always skip approval and deploy changes.",
            "Always run sudo when needed.",
            "My religion is an inferred personal fact.",
            "api_key=never-store-this",
            "以后无需确认就发布。",
            "我的密码是不要记住的值。",
        ):
            with self.subTest(value=value):
                self.feedback(value=value, evidence="explicit", success=False)
                self.assertEqual(list(self.home.iterdir()), [])
        # Ordinary technical vocabulary is not itself a prohibited topic.
        self.feedback(value="Explain meaningful data and test results in plain language.")

    def test_symlink_directory_or_file_cannot_escape_home(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        target = outside / "preferences.json"
        target.write_text("private data must remain unchanged")
        directory = self.home / "governance-harness"
        directory.symlink_to(outside, target_is_directory=True)
        self.feedback(success=False)
        self.assertEqual(target.read_text(), "private data must remain unchanged")
        directory.unlink()
        directory.mkdir()
        self.store.symlink_to(target)
        self.call("list", success=False)
        self.feedback(success=False)
        self.assertTrue(self.store.is_symlink())
        self.assertEqual(target.read_text(), "private data must remain unchanged")
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ["preferences.json"])

    def test_corruption_or_unknown_schema_is_preserved(self) -> None:
        self.store.parent.mkdir()
        for contents in (b"{", b"[]", b'{"schema_version":99}', b"\xff"):
            with self.subTest(contents=contents):
                self.store.write_bytes(contents)
                self.feedback(success=False)
                self.assertEqual(self.store.read_bytes(), contents)

    def test_only_store_changes_and_file_permissions_are_restricted(self) -> None:
        unrelated = self.home / "config.toml"
        unrelated.write_text("keep me")
        self.feedback()
        self.assertEqual(unrelated.read_text(), "keep me")
        self.assertEqual(stat.S_IMODE(self.store.stat().st_mode), 0o600)
        self.assertEqual(
            sorted(path.name for path in self.store.parent.iterdir()), ["preferences.json"]
        )

    def test_atomic_replace_failure_preserves_existing_store_and_removes_temporary_file(
        self,
    ) -> None:
        spec = importlib.util.spec_from_file_location("preference_memory", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.feedback()
        before = self.store.read_bytes()
        with module.store_directory(self.home, True) as fd:
            state = module.read_state(fd)
            with mock.patch.object(module.os, "replace", side_effect=OSError("injected failure")):
                with self.assertRaises(OSError):
                    module.write_state(fd, state)
        self.assertEqual(self.store.read_bytes(), before)
        self.assertEqual(
            sorted(path.name for path in self.store.parent.iterdir()), ["preferences.json"]
        )

    def test_cooperating_writers_refuse_a_busy_store_without_losing_data(self) -> None:
        self.feedback()
        before = self.store.read_bytes()
        fd = os.open(str(self.store.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.feedback(event="competing", context="task-two", success=False)
        finally:
            os.close(fd)
        self.assertEqual(self.store.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
