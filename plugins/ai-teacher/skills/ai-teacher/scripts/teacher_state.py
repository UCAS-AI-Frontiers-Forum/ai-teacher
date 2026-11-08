#!/usr/bin/env python3
"""Local evidence/version bookkeeping for AI Teacher; no network, model or workflow execution."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

COLLECTIONS = {"profile": "profiles", "capability": "capabilities",
               "workflow": "workflows", "feedback": "feedback"}
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ACTIVE = {"pilot-ready", "validated", "in-use"}


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicated JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    def reject(value):
        raise ValueError(f"invalid JSON constant: {value}")
    with Path(path).open(encoding="utf-8-sig") as handle:
        return json.load(handle, object_pairs_hook=object_pairs, parse_constant=reject)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: nonempty string required")


def sequence(value, label, nonempty=False):
    require(isinstance(value, list), f"{label}: array required")
    require(not nonempty or bool(value), f"{label}: nonempty array required")
    return value


def texts(value, label, nonempty=False):
    for item in sequence(value, label, nonempty):
        text(item, label)
    return value


def identity(value):
    require(isinstance(value, str) and bool(ID.fullmatch(value)), "invalid id")


def revision(value):
    require(type(value) is int and value >= 1, "revision must be a positive integer")


def day(value, label):
    require(isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), f"{label}: ISO date required")
    return date.fromisoformat(value)


def workspace(path):
    p = Path(path).absolute()
    require(not p.is_symlink() and p.is_dir(), "workspace must be an existing nonsymlink directory")
    return p.resolve()


def inside(root, relative, exists=True):
    require(isinstance(relative, str), "relative path required")
    rel = Path(relative)
    require(relative and not rel.is_absolute() and ".." not in rel.parts, "path must stay inside workspace")
    current = root
    for part in rel.parts:
        current = current / part
        require(not current.is_symlink(), "symlink in managed path")
    require(current.resolve().is_relative_to(root), "path escapes workspace")
    if exists:
        require(current.is_file(), f"missing evidence or record: {relative}")
        require(current.stat().st_size > 0, f"empty evidence or record: {relative}")
    return current


def evidence(root, values, label, required=False):
    for relative in texts(values, label, required):
        inside(root, relative)


def record_path(root, kind, key, rev, exists=False):
    require(kind in COLLECTIONS, "unknown record kind")
    identity(key)
    revision(rev)
    return inside(root, f"{COLLECTIONS[kind]}/{key}/r{rev:04d}.json", exists)


def latest(root, kind, key):
    identity(key)
    directory = inside(root, f"{COLLECTIONS[kind]}/{key}", exists=False)
    if not directory.exists():
        return None
    require(directory.is_dir(), "record directory is not a directory")
    files = []
    for path in directory.glob("r*.json"):
        require(not path.is_symlink(), "symlink record")
        match = re.fullmatch(r"r(\d+)\.json", path.name)
        require(match is not None, "invalid revision filename")
        files.append((int(match.group(1)), path))
    if not files:
        return None
    rev, path = max(files)
    obj = read_json(path)
    require(obj.get("kind") == kind and obj.get("id") == key and obj.get("revision") == rev,
            "record identity differs from storage path")
    return obj


def reference(root, kind, ref):
    require(isinstance(ref, dict), "reference object required")
    path = record_path(root, kind, ref.get("id"), ref.get("revision"), exists=True)
    obj = read_json(path)
    require(obj.get("kind") == kind and obj.get("id") == ref["id"] and obj.get("revision") == ref["revision"],
            "referenced record identity mismatch")
    return obj


def check_capability(root, obj, today):
    for key in ("title", "supports", "cost"):
        text(obj.get(key), key)
    require(obj.get("status") in {"candidate", "usable", "deprecated"}, "invalid capability status")
    texts(obj.get("environment"), "environment", True)
    require(obj.get("access") in {"verified", "unknown", "blocked"}, "invalid access status")
    require(obj.get("license") in {"verified", "unknown", "not-applicable", "blocked"}, "invalid license status")
    day(obj.get("review_on"), "review_on")
    validation = obj.get("validation", {})
    level = validation.get("level")
    require(level in {"observed", "documented", "smoke-tested", "task-validated"}, "invalid validation level")
    tested = level in {"smoke-tested", "task-validated"}
    if tested:
        require(day(validation.get("tested_on"), "tested_on") <= today, "test date is in the future")
    evidence(root, validation.get("evidence"), "validation.evidence", tested)
    texts(validation.get("limitations"), "limitations")
    sources = sequence(obj.get("sources"), "sources", True)
    for source in sources:
        require(isinstance(source, dict), "source object required")
        url = source.get("url", "")
        require(isinstance(url, str), "HTTPS source required")
        parsed = urlsplit(url)
        require(parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password,
                "HTTPS source without embedded credentials required")
        if not obj["synthetic"]:
            require(not parsed.hostname.endswith((".invalid", ".test", ".example")) and
                    parsed.hostname not in {"localhost", "example.com", "example.org", "example.net"},
                    "placeholder source cannot support a real capability")
        text(source.get("claim"), "source.claim")
        if level != "observed":
            require(day(source.get("checked_on"), "checked_on") <= today, "source date is in the future")
            inside(root, source.get("evidence"))
    if obj["status"] == "usable":
        require(tested, "usable capability requires actual smoke/task test evidence")
        require(obj["access"] == "verified" and obj["license"] in {"verified", "not-applicable"},
                "usable capability requires checked access and license")


def check_workflow(root, obj, today):
    profile = reference(root, "profile", obj.get("profile_ref"))
    for key in ("goal", "change_reason", "rollback"):
        text(obj.get(key), key)
    for key in ("current_process", "alternatives", "human_guide"):
        texts(obj.get(key), key, True)
    texts(obj.get("uncertainties"), "uncertainties")
    for key in ("learning", "migration", "execution"):
        text(obj.get("costs", {}).get(key), "costs." + key)
    status = obj.get("status")
    require(status in {"draft", "pilot-ready", "validated", "in-use", "retired"}, "invalid workflow status")
    require(obj.get("conclusion") in {"keep", "pilot", "adopt", "defer"}, "invalid conclusion")
    if obj["conclusion"] == "adopt":
        require(status in {"validated", "in-use"}, "adopt requires a validated workflow")
    if status in ACTIVE:
        require(profile.get("task", {}).get("goal") not in {None, "", "unknown"}, "active workflow needs diagnosed goal")
    cap_refs = sequence(obj.get("capabilities"), "capabilities")
    selected = set()
    for ref in cap_refs:
        text(ref.get("fit"), "capability fit")
        cap = reference(root, "capability", ref)
        require(cap["id"] not in selected, "duplicate selected capability")
        selected.add(cap["id"])
        require(cap.get("synthetic") == obj["synthetic"], "cannot mix synthetic and real workflow/capability")
        if status in ACTIVE:
            check_capability(root, cap, today)
            require(cap["status"] == "usable", "active workflow cannot use an unverified capability")
            require(day(cap["review_on"], "review_on") >= today, "capability evidence needs current review")
            newest = latest(root, "capability", cap["id"])
            require(newest["status"] != "deprecated", "selected capability has been deprecated")
    permissions = obj.get("permissions", {})
    granted = set()
    for grant in sequence(permissions.get("granted"), "granted permissions"):
        for key in ("action", "scope", "basis"):
            text(grant.get(key), "permission." + key)
        require(grant["action"] not in granted, "duplicate granted action")
        granted.add(grant["action"])
    pending = set(texts(permissions.get("pending"), "pending permissions"))
    require(not (pending & granted), "same action cannot be both granted and pending")
    steps = sequence(obj.get("steps"), "steps", True)
    ids, dependencies = set(), {}
    for step in steps:
        key = step.get("id")
        identity(key)
        require(key not in ids, "duplicate step id")
        ids.add(key)
        require(step.get("owner") in {"human", "agent", "tool"}, "invalid step owner")
        for field in ("action", "check", "if_failed"):
            text(step.get(field), "step." + field)
        for field in ("inputs", "outputs"):
            texts(step.get(field), "step." + field, True)
        needs = texts(step.get("needs"), "step.needs")
        dependencies[key] = needs
        require(set(texts(step.get("capabilities"), "step.capabilities")) <= selected,
                "step refers to unselected capability")
        requires = set(texts(step.get("requires"), "step.requires"))
        require(requires <= granted | pending, "undeclared step permission")
        if status in ACTIVE:
            require(requires <= granted, "active step requires ungranted action")
    for key, needs in dependencies.items():
        require(set(needs) <= ids and key not in needs, "invalid step dependency")
    done, visiting = set(), set()
    def visit(key):
        require(key not in visiting, "workflow dependency cycle")
        if key in done:
            return
        visiting.add(key)
        for dependency in dependencies[key]:
            visit(dependency)
        visiting.remove(key)
        done.add(key)
    for key in ids:
        visit(key)
    criteria = sequence(obj.get("criteria"), "criteria", True)
    criteria_ids = set()
    for criterion in criteria:
        identity(criterion.get("id"))
        require(criterion["id"] not in criteria_ids, "duplicate criterion id")
        criteria_ids.add(criterion["id"])
        text(criterion.get("description"), "criterion.description")
    result_ids, passed = set(), set()
    for result in sequence(obj.get("results"), "results"):
        key = result.get("criterion_id")
        require(key in criteria_ids and key not in result_ids, "unknown or repeated result criterion")
        result_ids.add(key)
        require(result.get("status") in {"pass", "fail", "not-run"}, "invalid criterion result")
        evidence(root, result.get("evidence"), "result.evidence", result["status"] == "pass")
        if result["status"] == "pass":
            passed.add(key)
    if status in {"validated", "in-use"}:
        require(passed == criteria_ids, "validated workflow needs evidence for all criteria")
    evidence(root, obj.get("reuse_evidence"), "reuse_evidence", status == "in-use")
    brief = obj.get("executor_brief", {})
    for key in ("goal", "handoff"):
        text(brief.get(key), "executor_brief." + key)
    for key in ("allowed_inputs", "environment", "stop_conditions"):
        texts(brief.get(key), "executor_brief." + key, True)
    step_ids = texts(brief.get("step_ids"), "executor_brief.step_ids", True)
    require(set(step_ids) == ids and len(step_ids) == len(ids), "executor brief must cover every step once")
    acceptance = texts(brief.get("acceptance"), "executor_brief.acceptance", True)
    require(set(acceptance) == criteria_ids, "executor brief must reference all acceptance criteria")
    positions = {key: index for index, key in enumerate(step_ids)}
    require(all(positions[dep] < positions[key] for key, needs in dependencies.items() for dep in needs),
            "executor step order violates dependencies")
    if status in ACTIVE:
        require("unknown" not in brief["environment"], "active workflow needs known execution environment")


def validate(root, obj, today):
    require(isinstance(obj, dict), "record must be an object")
    require(type(obj.get("schema_version")) is int and obj["schema_version"] == 1, "unsupported schema")
    kind = obj.get("kind")
    require(kind in COLLECTIONS, "unknown kind")
    identity(obj.get("id"))
    revision(obj.get("revision"))
    require(type(obj.get("synthetic")) is bool, "explicit synthetic boolean required")
    if kind == "profile":
        for key in ("domain", "engineering", "ai_workflow"):
            text(obj.get("expertise", {}).get(key), "expertise." + key)
        task = obj.get("task", {})
        text(task.get("goal"), "task.goal")
        texts(task.get("current_process"), "task.current_process")
        text(task.get("bottleneck"), "task.bottleneck")
        constraints = obj.get("constraints", {})
        require(constraints.get("data_policy") == "public-or-synthetic-only", "unsupported data policy")
        texts(constraints.get("environment"), "environment", True)
        for key in ("budget", "time"):
            text(constraints.get(key), "constraints." + key)
        require(obj.get("delivery_mode") in {"human", "agent", "both"}, "invalid delivery mode")
    elif kind == "capability":
        check_capability(root, obj, today)
    elif kind == "workflow":
        check_workflow(root, obj, today)
    else:
        reference(root, "workflow", obj.get("workflow_ref"))
        require(obj.get("signal") in {"success", "partial", "failed", "not-used"}, "invalid feedback signal")
        require(obj.get("observation") in {"self-report", "artifact-backed"}, "invalid feedback observation")
        text(obj.get("detail"), "feedback.detail")
        evidence(root, obj.get("evidence"), "feedback.evidence", obj["observation"] == "artifact-backed")
    return obj


def save(root, obj, today):
    validate(root, obj, today)
    previous = latest(root, obj["kind"], obj["id"])
    expected = previous["revision"] + 1 if previous else 1
    require(obj["revision"] == expected, f"next revision must be {expected}; existing records are immutable")
    dst = record_path(root, obj["kind"], obj["id"], obj["revision"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("x", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return dst.relative_to(root).as_posix()


def init(path, today):
    root = Path(path).absolute()
    require(not root.exists() and not root.is_symlink(), "init refuses an existing workspace")
    require(root.parent.is_dir(), "workspace parent must already exist")
    root.mkdir()
    root = root.resolve()
    for directory in (*COLLECTIONS.values(), "evidence", "notes"):
        (root / directory).mkdir()
    profile = {
        "schema_version": 1, "kind": "profile", "id": "local-user", "revision": 1, "synthetic": False,
        "expertise": {"domain": "unknown", "engineering": "unknown", "ai_workflow": "unknown"},
        "task": {"goal": "unknown", "current_process": [], "bottleneck": "unknown"},
        "constraints": {"data_policy": "public-or-synthetic-only", "environment": ["unknown"],
                        "budget": "unknown", "time": "unknown"}, "delivery_mode": "both",
    }
    save(root, profile, today)
    return root


def all_latest(root, kind):
    folder = inside(root, COLLECTIONS[kind], exists=False)
    require(folder.is_dir(), "missing state collection")
    result = []
    for directory in sorted(folder.iterdir()):
        require(not directory.is_symlink() and directory.is_dir(), "unexpected item in state collection")
        item = latest(root, kind, directory.name)
        if item:
            result.append(item)
    return result


def status(root, today):
    caps = {item["id"]: item for item in all_latest(root, "capability")}
    workflows = all_latest(root, "workflow")
    feedback = all_latest(root, "feedback")
    profiles = {item["id"]: item for item in all_latest(root, "profile")}
    due = [key for key, cap in caps.items() if day(cap["review_on"], "review_on") < today]
    affected = []
    for flow in workflows:
        reasons = []
        verified, in_use, history = [], [], {}
        for rev in range(1, flow["revision"] + 1):
            old = reference(root, "workflow", {"id": flow["id"], "revision": rev})
            history[rev] = old
            if old["status"] in {"validated", "in-use"}:
                verified.append(rev)
            if old["status"] == "in-use":
                in_use.append(rev)
        effective = max(in_use) if in_use else max(verified) if verified else None
        watched = {flow["revision"]} if flow["status"] != "retired" else set()
        if watched and effective is not None:
            watched.add(effective)
        for rev in sorted(watched):
            target = history[rev]
            profile = profiles.get(target["profile_ref"]["id"])
            if not profile or profile["revision"] != target["profile_ref"]["revision"]:
                reasons.append("profile-changed")
            for ref in target["capabilities"]:
                cap = caps.get(ref["id"])
                if not cap:
                    reasons.append("capability-missing:" + ref["id"])
                elif cap["status"] == "deprecated":
                    reasons.append("capability-deprecated:" + ref["id"])
                elif cap["status"] != "usable":
                    reasons.append("capability-not-usable:" + ref["id"])
                elif cap["revision"] != ref["revision"]:
                    reasons.append("capability-revised:" + ref["id"])
                if ref["id"] in due:
                    reasons.append("capability-review-due:" + ref["id"])
            for note in feedback:
                if note["workflow_ref"] == {"id": flow["id"], "revision": rev} and note["signal"] in {"partial", "failed"}:
                    reasons.append("feedback-" + note["signal"] + ":" + note["id"])
        reasons = list(dict.fromkeys(reasons))
        affected.append({"id": flow["id"], "revision": flow["revision"], "status": flow["status"],
                         "last_verified_revision": max(verified) if verified else None,
                         "last_in_use_revision": max(in_use) if in_use else None,
                         "effective_revision": effective if watched else None,
                         "reviewed_revisions": sorted(watched),
                         "needs_review": bool(reasons), "reasons": reasons})
    return {"as_of": today.isoformat(), "due_capabilities": due,
            "profiles": [{"id": p["id"], "revision": p["revision"]} for p in profiles.values()],
            "workflows": affected, "network_checked": False, "background_monitoring": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "check", "save"):
        child = sub.add_parser(name)
        child.add_argument("--workspace", required=True, type=Path)
        child.add_argument("--as-of", default=date.today().isoformat())
        if name in {"check", "save"}:
            child.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()
    try:
        today = day(args.as_of, "as-of")
        if args.command == "init":
            result = {"workspace": str(init(args.workspace, today)), "initialized": True}
        else:
            root = workspace(args.workspace)
            if args.command == "status":
                result = status(root, today)
            else:
                obj = read_json(args.file)
                if args.command == "check":
                    validate(root, obj, today)
                    result = {"valid": True, "executed": False,
                              "note": "structural checks only; evidence meaning and permissions need review"}
                else:
                    result = {"saved": save(root, obj, today), "executed": False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
