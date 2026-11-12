#!/usr/bin/env python3
"""One steward-owned, immutable baseline/candidate blind-comparison campaign.

The fixed launcher consumes a role before starting Python. A crashed/launched run
cannot be retried: missing output does not prove that no questions were scored.
Preflight failures have an append-only receipt and consume no run. This is an
audit/control tool, not protection against an operator replacing its directory.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from generalization_common import (VERSION, canonical, digest, file_hash, indexed, load_gold,
                                   private_path, rows, write_json)

ROOT = Path(__file__).resolve().parents[1]
PINNED_FILES = ("harness/run_eval.py", "harness/scoring.py", "harness/contract.py", "scripts/_guarded_run_eval.py",
                "scripts/generalization_common.py", "scripts/generalization_audit.py",
                "scripts/generalization_report.py", "scripts/generalization_ledger.py")
SHA = re.compile(r"[0-9a-f]{40}")


def now():
    return datetime.now(timezone.utc).isoformat()


def tools_hashes():
    return {name: file_hash(ROOT / name) for name in PINNED_FILES}


def source_digest(snapshots):
    manifests = sorted(snapshots.glob("*/manifest.json"))
    if not manifests:
        raise ValueError("local extracted source snapshots are required")
    hashes = {}
    for manifest_path in manifests:
        hashes[str(manifest_path.relative_to(snapshots))] = file_hash(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for page in manifest["pages"]:
            path = (manifest_path.parent / page["file"]).resolve()
            path.relative_to(manifest_path.parent.resolve())
            hashes[manifest_path.parent.name + "/" + page["file"]] = file_hash(path)
    return digest(hashes)


@contextmanager
def locked(root):
    root = private_path(Path(root))
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".lock"
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("campaign is locked; investigate an interrupted steward operation") from exc
    try:
        os.close(fd)
        yield root
    finally:
        lock.unlink()


def read_campaign(root):
    manifest = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
    expected = (root / "campaign.sha256").read_text().strip()
    if digest(manifest) != expected:
        raise ValueError("immutable campaign manifest was modified")
    events, previous = [], expected
    path = root / "events.jsonl"
    if path.exists():
        for event in rows(path):
            sha = event.pop("event_sha256", None)
            if event.get("sequence") != len(events) or event.get("previous_sha256") != previous or digest(event) != sha:
                raise ValueError("campaign event chain is invalid")
            event["event_sha256"] = sha
            events.append(event)
            previous = sha
    head = root / "events.sha256"
    if (not events or events[0]["action"] != "registered" or not head.is_file()
            or head.read_text().strip() != previous):
        raise ValueError("campaign event chain is incomplete or its tail was modified")
    return manifest, events, previous


def append(root, events, previous, action, **fields):
    event = {"sequence": len(events), "previous_sha256": previous, "at": now(), "action": action, **fields}
    event["event_sha256"] = digest(event)
    with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(canonical(event).decode() + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    # A separate atomic head catches deleted tail events; a crash between these
    # writes fails closed and requires custodian review rather than reopening a role.
    head = root / "events.sha256.tmp"
    with head.open("w", encoding="utf-8") as stream:
        stream.write(event["event_sha256"] + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    head.replace(root / "events.sha256")
    return event


def verify_review(path, question_hash, rubric_hash):
    review = json.loads(path.read_text(encoding="utf-8"))
    if (review.get("status") != "passed" or review.get("independent") is not True
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or review.get("questions_sha256") != question_hash or review.get("rubrics_sha256") != rubric_hash):
        raise ValueError("independent source-review attestation does not bind the final gold")


def register(root, questions, rubrics, freeze, source_review, baseline, candidate, scorer_version, snapshots):
    if not all(isinstance(x, str) and SHA.fullmatch(x) for x in (baseline, candidate)) or baseline == candidate:
        raise ValueError("two distinct full commit SHAs are required")
    if not isinstance(scorer_version, str) or not scorer_version.strip():
        raise ValueError("scoring policy version is required")
    gold, manifest = load_gold(questions, rubrics, freeze)
    if manifest.get("schema_version") != "phase4-source-blind-freeze-v1":
        raise ValueError("sealed campaign requires the explicit blind freeze schema")
    qh, rh = file_hash(questions), file_hash(rubrics)
    verify_review(source_review, qh, rh)
    paths = {"questions": questions, "rubrics": rubrics, "freeze": freeze, "source_review": source_review}
    campaign = {"version": VERSION, "registered_at": now(), "scorer_version": scorer_version,
                "commits": {"baseline": baseline, "candidate": candidate},
                "inputs": {name: {"path": str(path.resolve()), "sha256": file_hash(path)} for name, path in paths.items()},
                "tool_sha256": tools_hashes(), "question_count": len(gold), "allowed_runs": 2,
                "source_tree_sha256": source_digest(snapshots),
                "retry_policy": "preflight only; launching consumes the role permanently"}
    with locked(root) as directory:
        if (directory / "campaign.json").exists() or (directory / "events.jsonl").exists():
            raise ValueError("campaign already registered; changing commits/labels cannot reopen it")
        write_json(directory / "campaign.json", campaign)
        (directory / "campaign.sha256").write_text(digest(campaign) + "\n", encoding="utf-8")
        append(directory, [], digest(campaign), "registered")
    return campaign


def check_runtime(checkout, expected):
    def git(*args):
        value = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True)
        if value.returncode:
            raise ValueError("runtime checkout cannot be verified")
        return value.stdout.strip()
    if git("rev-parse", "HEAD") != expected:
        raise ValueError("runtime commit is not the registered role")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("runtime checkout is dirty")
    if not (checkout / "submission" / "solution.py").is_file():
        raise ValueError("runtime entry point is missing")


def preflight(campaign, role, checkout, snapshots, python):
    if role not in ("baseline", "candidate"):
        raise ValueError("only the registered baseline/candidate roles are allowed")
    if tools_hashes() != campaign["tool_sha256"]:
        raise ValueError("frozen scoring/launcher code changed")
    for item in campaign["inputs"].values():
        if file_hash(Path(item["path"])) != item["sha256"]:
            raise ValueError("frozen dataset/rubric/review/policy changed")
    check_runtime(checkout, campaign["commits"][role])
    if source_digest(snapshots) != campaign["source_tree_sha256"]:
        raise ValueError("frozen source corpus changed")
    if not python.is_file() or not os.access(str(python), os.X_OK):
        raise ValueError("Python executable is unavailable")


def reserve(root, role, checkout, snapshots, python):
    """Reserve before process launch; cannot be reset by a different purpose/label."""
    with locked(root) as directory:
        campaign, events, previous = read_campaign(directory)
        if role not in campaign["commits"]:
            raise ValueError("unknown comparison role")
        if any(event["action"] == "started" and event.get("role") == role for event in events):
            raise ValueError("this registered role has already consumed its single run")
        try:
            preflight(campaign, role, checkout, snapshots, python)
            out = directory / (role + "-run")
            if out.exists():
                raise ValueError("run output already exists")
        except (OSError, ValueError, KeyError) as exc:
            append(directory, events, previous, "preflight_failed", role=role, reason=str(exc),
                   process_launched=False, answers_scored=0)
            raise
        out.mkdir()
        append(directory, events, previous, "started", role=role, commit=campaign["commits"][role],
               checkout=str(checkout.resolve()), output=str(out), process_launch_pending=True)
    return campaign, out


def finish(root, role, returncode, output, failure=None):
    with locked(root) as directory:
        _, events, previous = read_campaign(directory)
        started = [e for e in events if e["action"] == "started" and e.get("role") == role]
        if len(started) != 1:
            raise ValueError("run was not reserved")
        if any(e["action"] == "finished" and e.get("role") == role for e in events):
            raise ValueError("completion already recorded")
        if output.resolve() != Path(started[0]["output"]).resolve():
            raise ValueError("completion must bind the registered output directory")
        hashes = {path.name: file_hash(path) for path in output.iterdir() if path.is_file()}
        append(directory, events, previous, "finished", role=role, returncode=returncode,
               output_sha256=hashes, failure=failure, retry_allowed=False)


def run(root, role, checkout, snapshots, python):
    campaign, output = reserve(root, role, checkout, snapshots, python)
    command = [str(python), str(ROOT / "scripts/_guarded_run_eval.py"), "--submission", str(checkout / "submission"),
               "--snapshots", str(snapshots), "--eval", campaign["inputs"]["questions"]["path"],
               "--out", str(output), "--repeat-sample", "0"]
    failure, code = None, -1
    try:
        with (output / "harness.log").open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=str(checkout), stdout=stream, stderr=subprocess.STDOUT,
                                    env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
                                         "PYTHONHASHSEED": "0"})
            code = result.returncode
        if code == 0:
            expected = indexed(rows(Path(campaign["inputs"]["questions"]["path"])))
            actual = indexed(rows(output / "per_question.jsonl"))
            if set(actual) != set(expected):
                raise ValueError("run did not produce exact question coverage")
            preflight(campaign, role, checkout, snapshots, python)
    except BaseException as exc:
        failure = type(exc).__name__
        finish(root, role, code, output, failure)
        raise
    finish(root, role, code, output, failure)
    return {"role": role, "returncode": code, "slot_consumed": True, "retry_allowed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register")
    reg.add_argument("--root", type=Path, required=True)
    for name in ("questions", "rubrics", "freeze", "source-review", "snapshots"):
        reg.add_argument("--" + name, type=Path, required=True)
    for name in ("baseline", "candidate", "scorer-version"):
        reg.add_argument("--" + name, required=True)
    launch = sub.add_parser("run")
    launch.add_argument("--root", type=Path, required=True)
    launch.add_argument("--role", choices=("baseline", "candidate"), required=True)
    launch.add_argument("--checkout", type=Path, required=True)
    launch.add_argument("--snapshots", type=Path, required=True)
    launch.add_argument("--python", type=Path, default=Path(sys.executable))
    status = sub.add_parser("status")
    status.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "register":
            register(args.root, args.questions, args.rubrics, args.freeze, args.source_review,
                     args.baseline, args.candidate, args.scorer_version, args.snapshots)
            result = {"registered": True, "allowed_runs": 2}
        elif args.command == "run":
            result = run(args.root.resolve(), args.role, args.checkout.resolve(), args.snapshots.resolve(), args.python.resolve())
        else:
            _, events, _ = read_campaign(args.root.resolve())
            result = {"events": len(events), "consumed_roles": sorted({e["role"] for e in events if e["action"] == "started"}),
                      "completed_roles": sorted({e["role"] for e in events if e["action"] == "finished"})}
        print(json.dumps(result, sort_keys=True))
        return result.get("returncode", 0)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error("sealed campaign rejected: " + str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
