#!/usr/bin/env python3
"""Synthetic state lifecycle demo; no web research or model-behavior evaluation."""
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_fixture", ROOT / "tests/test_teacher_state.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
state = fixture.state

parent = Path(tempfile.mkdtemp(prefix="ai-teacher-demo-"))
root, profile, cap, flow = fixture.create_fixture(parent)
state.save(root, flow, fixture.TODAY)
initial = state.status(root, fixture.TODAY)
expired = state.status(root, date(2026, 11, 16))
feedback = fixture.template("feedback")
feedback.update(id="demo-feedback", synthetic=True,
                workflow_ref={"id": flow["id"], "revision": 1},
                detail="Synthetic feedback: report lacks one needed grouping condition.")
state.save(root, feedback, fixture.TODAY)
after_feedback = state.status(root, fixture.TODAY)
report = {
    "synthetic_only": True,
    "what_was_run": "state persistence, dependency expiry and feedback review flags",
    "not_run": ["web research", "model behavior", "scientific workflow", "human trial"],
    "initial": initial, "after_review_date": expired, "after_feedback": after_feedback,
    "workflow_revision_unchanged": state.latest(root, "workflow", flow["id"])["revision"] == 1,
}
path = parent / "demo-report.json"
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"demo_workspace": str(root), "report": str(path), "synthetic_only": True}, ensure_ascii=False, indent=2))
