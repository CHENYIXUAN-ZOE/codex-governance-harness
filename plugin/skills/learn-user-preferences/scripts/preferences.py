#!/usr/bin/env python3
"""Small local preference memory; Python standard library, macOS/Linux."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

FILENAME = "preferences.json"
MAX_BYTES = 1024 * 1024
CATEGORIES = ("communication", "workflow", "output")
EVIDENCE = ("inferred", "correction", "explicit")
# Conservative catches, not a classifier or a proof that arbitrary text is safe.
UNSAFE = re.compile(
    r"(?i)(-----BEGIN .*PRIVATE KEY|\b(?:api[_ -]?key|access[_ -]?token|password)\s*[:=]|"
    r"\b(?:sk[-_]|ghp_|gho_)[A-Za-z0-9_-]{12,}|\bBearer\s+[A-Za-z0-9._-]{12,}|"
    r"\b(?:credentials?|sudo|chmod|approval|authorization|permissions?|"
    r"security exceptions?|publish|deploy|send emails?|religion|ethnicity|"
    r"sexual orientation|medical diagnosis)\b|"
    r"授权|权限|密钥|密码|令牌|绕过.*(?:审核|安全)|跳过.*(?:确认|审批)|"
    r"无需.*(?:确认|审批)|总是.*(?:发信|发送|发布|部署)|"
    r"宗教|民族|性取向|诊断|身份证)"
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_state() -> dict:
    return {
        "schema_version": 1,
        "revision": 0,
        "updated_at": None,
        "preferences": [],
        "events": {},
        "undo": None,
    }


def short_text(value: str, name: str, limit: int) -> str:
    value = value.strip()
    if not value or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(
            f"{name} must be a nonempty single-line summary of at most {limit} characters"
        )
    if UNSAFE.search(value):
        raise ValueError(
            f"{name} contains a prohibited or potentially sensitive topic; "
            "do not persist it as a preference"
        )
    return value


def scope_for(args: argparse.Namespace) -> dict:
    if args.scope == "global":
        if args.project:
            raise ValueError("global mutations must not include --project")
        return {"kind": "global"}
    if not args.project:
        raise ValueError("project scope requires --project")
    project = Path(args.project).expanduser()
    if not project.is_absolute() or not project.is_dir():
        raise ValueError("--project must be an existing absolute directory")
    return {"kind": "project", "root": str(project.resolve())}


def validate_state(state: dict, *, snapshot: bool = False) -> None:
    expected = {"schema_version", "revision", "updated_at", "preferences", "events", "undo"}
    if not isinstance(state, dict) or set(state) != expected or state["schema_version"] != 1:
        raise ValueError("unsupported or damaged preference store")
    if not isinstance(state["revision"], int) or state["revision"] < 0:
        raise ValueError("invalid preference revision")
    if not isinstance(state["events"], dict) or not isinstance(state["preferences"], list):
        raise ValueError("invalid preference records")
    if len(state["preferences"]) > 200:
        raise ValueError("preference store exceeds 200 records; review and consolidate it")
    identities = set()
    for record in state["preferences"]:
        fields = {
            "key",
            "scope",
            "category",
            "value",
            "when",
            "status",
            "active",
            "created_at",
            "updated_at",
            "sources",
        }
        if not isinstance(record, dict) or set(record) != fields:
            raise ValueError("invalid preference entry")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", record["key"]):
            raise ValueError("invalid preference key")
        scope = record["scope"]
        if scope != {"kind": "global"} and not (
            isinstance(scope, dict)
            and set(scope) == {"kind", "root"}
            and scope["kind"] == "project"
            and isinstance(scope["root"], str)
            and Path(scope["root"]).is_absolute()
        ):
            raise ValueError("invalid preference scope")
        identity = (record["key"], json.dumps(scope, sort_keys=True))
        if identity in identities:
            raise ValueError("duplicate preference key within scope")
        identities.add(identity)
        if record["category"] not in CATEGORIES or record["status"] not in (
            "candidate",
            "promoted",
            "explicit",
        ):
            raise ValueError("invalid preference category or confidence")
        if not isinstance(record["active"], bool) or not isinstance(record["sources"], list):
            raise ValueError("invalid preference activity or evidence")
        short_text(record["value"], "value", 280)
        short_text(record["when"], "when", 200)
        for source in record["sources"]:
            if not isinstance(source, dict) or set(source) != {
                "context",
                "evidence",
                "summary",
                "at",
            }:
                raise ValueError("invalid preference source")
            if source["evidence"] not in EVIDENCE or not re.fullmatch(
                r"[0-9a-f]{64}", source["context"]
            ):
                raise ValueError("invalid preference evidence")
            short_text(source["summary"], "source-summary", 160)
    for event, fingerprint in state["events"].items():
        if (
            not re.fullmatch(r"[0-9a-f]{64}", event)
            or not isinstance(fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        ):
            raise ValueError("invalid preference event history")
    if state["undo"] is not None:
        if snapshot:
            raise ValueError("nested undo history is not supported")
        validate_state(state["undo"], snapshot=True)


@contextmanager
def store_directory(home: Path, apply: bool):
    """Anchor operations to directory descriptors; never follow store symlinks."""
    home = home.expanduser()
    if not home.is_absolute() or not home.is_dir():
        raise ValueError("CODEX_HOME must be an existing absolute directory")
    # Canonicalizing the user-selected home supports legitimate home symlinks.
    home_fd = os.open(str(home.resolve()), os.O_RDONLY | os.O_DIRECTORY)
    directory_fd = None
    try:
        if apply:
            with suppress(FileExistsError):
                os.mkdir("governance-harness", mode=0o700, dir_fd=home_fd)
        try:
            directory_fd = os.open(
                "governance-harness", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd
            )
        except FileNotFoundError:
            if apply:
                raise
            yield None
            return
        try:
            fcntl.flock(directory_fd, (fcntl.LOCK_EX if apply else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("preference store is busy; retry the same event ID later") from error
        yield directory_fd
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(home_fd)


def read_state(directory_fd) -> dict:
    if directory_fd is None:
        return empty_state()
    try:
        fd = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except FileNotFoundError:
        return empty_state()
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            raise ValueError("preference store must be a regular, single-linked file below 1 MiB")
        state = json.loads(stream.read(MAX_BYTES + 1))
    validate_state(state)
    return state


def write_state(directory_fd: int, state: dict) -> None:
    validate_state(state)
    data = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("preference store exceeds 1 MiB; review and consolidate it")
    temporary = f".preferences-{uuid.uuid4().hex}.tmp"
    fd = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, FILENAME, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)


def mutation_payload(args: argparse.Namespace) -> dict:
    event_id = args.event_id.strip()
    if not event_id or len(event_id) > 200:
        raise ValueError(
            "--event-id must identify one actual feedback occurrence (1-200 characters)"
        )
    payload = {"command": args.command, "event": digest(event_id)}
    if args.command == "undo":
        return payload
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", args.key):
        raise ValueError(
            "--key must use lowercase letters, digits, hyphens, or underscores (1-64 characters)"
        )
    payload.update(key=args.key, scope=scope_for(args))
    if args.command in ("record", "replace"):
        if not args.context_id.strip() or len(args.context_id) > 200:
            raise ValueError(
                "--context-id must identify the independent task or correction episode"
            )
        payload.update(
            category=args.category,
            value=short_text(args.value, "value", 280),
            when=short_text(args.when, "when", 200),
            summary=short_text(args.source_summary, "source-summary", 160),
            evidence=args.evidence,
            context=digest(args.context_id.strip()),
        )
    return payload


def mutate(state: dict, payload: dict) -> tuple:
    fingerprint = digest(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    prior = state["events"].get(payload["event"])
    if prior:
        if prior != fingerprint:
            raise ValueError(
                "event ID was already used for different feedback; do not rewrite its meaning"
            )
        return state, "unchanged"
    result = copy.deepcopy(state)
    stamp = now()
    if payload["command"] == "undo":
        if state["undo"] is None:
            raise ValueError("there is no storage update to undo")
        result = copy.deepcopy(state["undo"])
        # A replay of revoked feedback must not silently bring it back.
        result["events"] = copy.deepcopy(state["events"])
        result["undo"] = None
    else:
        result["undo"] = copy.deepcopy(state)
        result["undo"]["undo"] = None
        record = next(
            (
                item
                for item in result["preferences"]
                if item["key"] == payload["key"] and item["scope"] == payload["scope"]
            ),
            None,
        )
        if payload["command"] in ("replace", "disable") and record is None:
            raise ValueError("preference does not exist in the specified scope")
        if payload["command"] == "disable":
            record["active"] = False
            record["updated_at"] = stamp
        else:
            if record and payload["command"] == "record":
                if not record["active"]:
                    raise ValueError(
                        "preference is disabled; only a deliberate replace can re-enable it"
                    )
                if any(record[name] != payload[name] for name in ("category", "value", "when")):
                    raise ValueError(
                        "formulation changed; use replace to reset evidence "
                        "for the new interpretation"
                    )
            if record is None or payload["command"] == "replace":
                if record is not None:
                    result["preferences"].remove(record)
                record = {
                    name: payload[name] for name in ("key", "scope", "category", "value", "when")
                }
                record.update(
                    status="candidate", active=True, created_at=stamp, updated_at=stamp, sources=[]
                )
                result["preferences"].append(record)
            source = {
                "context": payload["context"],
                "evidence": payload["evidence"],
                "summary": payload["summary"],
                "at": stamp,
            }
            # One strongest evidence entry per context; repeated turns do not inflate support.
            existing = next(
                (item for item in record["sources"] if item["context"] == source["context"]), None
            )
            rank = {"inferred": 0, "correction": 1, "explicit": 2}
            if existing is None:
                record["sources"].append(source)
            elif rank[source["evidence"]] > rank[existing["evidence"]]:
                record["sources"].remove(existing)
                record["sources"].append(source)
            evidence = [item["evidence"] for item in record["sources"]]
            record["status"] = (
                "explicit"
                if "explicit" in evidence
                else "promoted"
                if evidence.count("correction") >= 2
                else "candidate"
            )
            record["updated_at"] = stamp
    result["revision"] = state["revision"] + 1
    result["updated_at"] = stamp
    result["events"][payload["event"]] = fingerprint
    validate_state(result)
    return result, "changed"


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--codex-home",
        default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
        help="Existing absolute Codex home; defaults to CODEX_HOME or ~/.codex",
    )
    commands = cli.add_subparsers(dest="command", required=True)
    listing = commands.add_parser(
        "list", help="Read global and optional exact-project preferences without writing"
    )
    listing.add_argument("--project", help="Existing absolute project root to include")
    listing.add_argument("--category", choices=CATEGORIES)
    listing.add_argument("--key")
    listing.add_argument("--all", action="store_true", help="Include disabled preferences")
    listing.add_argument(
        "--details", action="store_true", help="Include brief evidence sources for inspection"
    )
    for name in ("record", "replace", "disable", "undo"):
        action = commands.add_parser(
            name,
            help={
                "record": "Add a candidate or supporting user feedback",
                "replace": "Correct a preference and reset its evidence",
                "disable": "Stop applying a preference while retaining its short record",
                "undo": "Reverse the last storage update; undo has no redo",
            }[name],
        )
        action.add_argument(
            "--event-id", required=True, help="Stable ID for this actual feedback; retries reuse it"
        )
        action.add_argument(
            "--apply",
            action="store_true",
            help="Persist the update; without this flag only preview",
        )
        if name == "undo":
            continue
        action.add_argument("--scope", choices=("global", "project"), required=True)
        action.add_argument("--project", help="Required only for project scope")
        action.add_argument("--key", required=True)
        if name == "disable":
            continue
        action.add_argument("--category", choices=CATEGORIES, required=True)
        action.add_argument(
            "--value", required=True, help="Reusable preference, at most 280 characters"
        )
        action.add_argument(
            "--when", required=True, help="Applicable conditions, at most 200 characters"
        )
        action.add_argument(
            "--source-summary",
            required=True,
            help="Brief user-feedback summary, at most 160 characters; no transcript",
        )
        action.add_argument("--evidence", choices=EVIDENCE, required=True)
        action.add_argument(
            "--context-id",
            required=True,
            help="Independent task/episode ID; repeated corrections in one episode share it",
        )
    return cli


def summary(record: dict) -> dict:
    result = {key: value for key, value in record.items() if key not in ("created_at", "sources")}
    result["evidence_count"] = len(record["sources"])
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        payload = None if args.command == "list" else mutation_payload(args)
        apply = bool(getattr(args, "apply", False))
        with store_directory(Path(args.codex_home), apply) as directory_fd:
            state = read_state(directory_fd)
            if args.command == "list":
                project = (
                    scope_for(argparse.Namespace(scope="project", project=args.project))
                    if args.project
                    else None
                )
                records = [
                    item
                    for item in state["preferences"]
                    if (item["scope"] == {"kind": "global"} or item["scope"] == project)
                    and (args.all or item["active"])
                    and (not args.key or item["key"] == args.key)
                    and (not args.category or item["category"] == args.category)
                ]
                report = {
                    "status": "ok",
                    "revision": state["revision"],
                    "preferences": records if args.details else [summary(item) for item in records],
                }
            else:
                result, change = mutate(state, payload)
                if apply and change == "changed":
                    write_state(directory_fd, result)
                report = {
                    "status": "unchanged"
                    if change == "unchanged"
                    else "applied"
                    if apply
                    else "preview",
                    "revision": result["revision"],
                }
                if args.command == "undo":
                    report["change"] = (
                        "restore the previous preference state; consumed event IDs remain recorded"
                    )
                else:
                    report["preferences"] = [
                        summary(item)
                        for item in result["preferences"]
                        if item["key"] == payload["key"] and item["scope"] == payload["scope"]
                    ]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(
            json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
