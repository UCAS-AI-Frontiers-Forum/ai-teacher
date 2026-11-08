"""State invariants, not an LLM-behavior or usefulness evaluation."""
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/ai-teacher/skills/ai-teacher"
spec = importlib.util.spec_from_file_location("teacher_state", SKILL / "scripts/teacher_state.py")
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)
TODAY = date(2026, 11, 8)


def template(name):
    return json.loads((SKILL / f"assets/{name}.template.json").read_text())


def create_fixture(parent):
    root = state.init(Path(parent) / "ai-teacher-work", TODAY)
    profile = template("profile")
    profile.update(synthetic=True)
    profile["expertise"] = {"domain": "video generation", "engineering": "experienced", "ai_workflow": "basic"}
    profile["task"] = {"goal": "整理模拟实验记录并生成可核对的对比报告", "current_process": ["手工复制公开样例日志"], "bottleneck": "重复整理"}
    profile["constraints"].update(environment=["Python 3.10+ local"], budget="0 GPU minutes / 0 paid calls", time="30 minutes")
    state.save(root, profile, TODAY)
    for name, text in {
        "source.md": "SYNTHETIC source note for a fixture; no web reading claimed.\n",
        "smoke.md": "SYNTHETIC smoke test evidence for state validation only.\n",
        "result.md": "SYNTHETIC result fixture; no real research effectiveness claim.\n",
        "reuse.md": "SYNTHETIC reuse fixture; not a human trial.\n",
    }.items():
        (root / "evidence" / name).write_text(text)
    cap = template("capability")
    cap.update(id="fixture-parser", synthetic=True, title="合成的本地解析能力", status="usable", access="verified", license="not-applicable", cost="0 paid calls")
    cap["sources"] = [{"url": "https://example.invalid/fixture-doc", "checked_on": "2026-11-08", "claim": "synthetic reference", "evidence": "evidence/source.md"}]
    cap["environment"] = ["Python 3.10+ local"]
    cap["validation"] = {"level": "smoke-tested", "tested_on": "2026-11-08", "evidence": ["evidence/smoke.md"], "limitations": ["synthetic fixture only"]}
    state.save(root, cap, TODAY)
    workflow = template("workflow")
    workflow.update(id="experiment-records", synthetic=True, goal=profile["task"]["goal"])
    workflow["capabilities"] = [{"id": cap["id"], "revision": 1, "fit": "synthetic local Python environment"}]
    workflow["steps"][0].update(action="用模拟样例说明如何整理实验记录", capabilities=[cap["id"]])
    workflow["executor_brief"].update(goal=workflow["goal"], environment=["Python 3.10+ local"])
    workflow["costs"] = {"learning": "only invocation and checking", "migration": "none", "execution": "small local sample"}
    return root, profile, cap, workflow


class TeacherStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root, self.profile, self.cap, self.flow = create_fixture(self.parent)

    def test_init_does_not_claim_background_or_current_knowledge(self):
        result = state.status(self.root, TODAY)
        self.assertFalse(result["background_monitoring"])
        self.assertFalse(result["network_checked"])
        other = state.init(self.parent / "other", TODAY)
        self.assertEqual(state.all_latest(other, "capability"), [])

    def test_init_refuses_existing_and_preserves_records(self):
        p = self.root / "profiles/local-user/r0001.json"
        before = p.read_bytes()
        with self.assertRaises(ValueError):
            state.init(self.root, TODAY)
        self.assertEqual(p.read_bytes(), before)

    def test_revisions_are_immutable_and_consecutive(self):
        state.save(self.root, self.flow, TODAY)
        self.assertIsNone(state.status(self.root, TODAY)["workflows"][0]["effective_revision"])
        with self.assertRaises(ValueError):
            state.save(self.root, self.flow, TODAY)
        self.flow["revision"] = 3
        with self.assertRaises(ValueError):
            state.save(self.root, self.flow, TODAY)
        self.assertEqual(state.latest(self.root, "workflow", self.flow["id"])["revision"], 1)

    def test_documented_cannot_be_marked_usable(self):
        self.cap["validation"] = {"level": "documented", "tested_on": None, "evidence": [], "limitations": []}
        with self.assertRaisesRegex(ValueError, "actual smoke"):
            state.validate(self.root, self.cap, TODAY)

    def test_active_flow_rejects_candidate_capability(self):
        self.cap.update(revision=2, status="candidate")
        state.save(self.root, self.cap, TODAY)
        self.flow["status"] = "pilot-ready"
        self.flow["capabilities"][0]["revision"] = 2
        with self.assertRaisesRegex(ValueError, "unverified"):
            state.validate(self.root, self.flow, TODAY)

    def test_active_flow_rejects_expired_evidence(self):
        self.flow["status"] = "pilot-ready"
        with self.assertRaisesRegex(ValueError, "current review"):
            state.validate(self.root, self.flow, date(2026, 11, 16))

    def test_no_synthetic_capability_in_real_workflow(self):
        self.flow["synthetic"] = False
        with self.assertRaisesRegex(ValueError, "synthetic"):
            state.validate(self.root, self.flow, TODAY)

    def test_no_placeholder_source_for_real_capability(self):
        self.cap["synthetic"] = False
        with self.assertRaisesRegex(ValueError, "placeholder"):
            state.validate(self.root, self.cap, TODAY)

    def test_no_future_test_or_source(self):
        for field in ("test", "source"):
            with self.subTest(field=field):
                cap = deepcopy(self.cap)
                if field == "test":
                    cap["validation"]["tested_on"] = "2026-11-09"
                else:
                    cap["sources"][0]["checked_on"] = "2026-11-09"
                with self.assertRaisesRegex(ValueError, "future"):
                    state.validate(self.root, cap, TODAY)

    def test_validation_requires_all_criteria_and_nonempty_evidence(self):
        self.flow.update(status="validated", conclusion="adopt")
        with self.assertRaisesRegex(ValueError, "all criteria"):
            state.validate(self.root, self.flow, TODAY)
        self.flow["results"][0].update(status="pass")
        with self.assertRaises(ValueError):
            state.validate(self.root, self.flow, TODAY)
        self.flow["results"][0]["evidence"] = ["evidence/result.md"]
        state.validate(self.root, self.flow, TODAY)

    def test_in_use_requires_reuse_evidence(self):
        self.flow.update(status="in-use", conclusion="adopt")
        self.flow["results"][0].update(status="pass", evidence=["evidence/result.md"])
        with self.assertRaises(ValueError):
            state.validate(self.root, self.flow, TODAY)
        self.flow["reuse_evidence"] = ["evidence/reuse.md"]
        state.save(self.root, self.flow, TODAY)

    def test_draft_adopt_is_rejected(self):
        self.flow["conclusion"] = "adopt"
        with self.assertRaisesRegex(ValueError, "adopt"):
            state.validate(self.root, self.flow, TODAY)

    def test_active_permissions_require_scope_and_basis(self):
        self.flow["status"] = "pilot-ready"
        self.flow["steps"][0]["requires"] = ["paid-api"]
        self.flow["permissions"]["pending"] = ["paid-api"]
        with self.assertRaisesRegex(ValueError, "ungranted"):
            state.validate(self.root, self.flow, TODAY)
        self.flow["permissions"] = {"granted": [{"action": "paid-api", "scope": "fixture-only", "basis": "synthetic authorization example"}], "pending": []}
        state.validate(self.root, self.flow, TODAY)

    def test_cycles_and_wrong_executor_order_are_rejected(self):
        step2 = deepcopy(self.flow["steps"][0])
        step2.update(id="step-2", needs=["step-1"])
        self.flow["steps"].append(step2)
        self.flow["executor_brief"]["step_ids"] = ["step-2", "step-1"]
        with self.assertRaisesRegex(ValueError, "order"):
            state.validate(self.root, self.flow, TODAY)
        self.flow["steps"][0]["needs"] = ["step-2"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            state.validate(self.root, self.flow, TODAY)

    def test_evidence_path_traversal_symlink_and_empty_rejected(self):
        outside = self.parent / "external.md"
        outside.write_text("external")
        (self.root / "evidence/link.md").symlink_to(outside)
        (self.root / "evidence/empty.md").touch()
        for path in ("../external.md", "evidence/link.md", "evidence/empty.md"):
            with self.subTest(path=path):
                self.cap["validation"]["evidence"] = [path]
                with self.assertRaises(ValueError):
                    state.validate(self.root, self.cap, TODAY)

    def test_status_impacts_only_dependent_flows_and_preserves_revision(self):
        state.save(self.root, self.flow, TODAY)
        independent = deepcopy(self.flow)
        independent.update(id="no-dependency", capabilities=[], conclusion="keep")
        independent["steps"][0]["capabilities"] = []
        state.save(self.root, independent, TODAY)
        result = state.status(self.root, date(2026, 11, 16))
        flows = {f["id"]: f for f in result["workflows"]}
        self.assertTrue(flows[self.flow["id"]]["needs_review"])
        self.assertFalse(flows["no-dependency"]["needs_review"])
        self.assertEqual(state.latest(self.root, "workflow", self.flow["id"])["revision"], 1)

    def test_failure_feedback_and_profile_change_trigger_review(self):
        state.save(self.root, self.flow, TODAY)
        feedback = template("feedback")
        feedback.update(id="trial-feedback", synthetic=True, workflow_ref={"id": self.flow["id"], "revision": 1})
        state.save(self.root, feedback, TODAY)
        self.profile["revision"] = 3
        self.profile["constraints"]["environment"] = ["browser only"]
        state.save(self.root, self.profile, TODAY)
        reasons = state.status(self.root, TODAY)["workflows"][0]["reasons"]
        self.assertIn("profile-changed", reasons)
        self.assertTrue(any(r.startswith("feedback-partial:") for r in reasons))

    def test_new_draft_does_not_erase_old_verified_or_in_use_version(self):
        self.flow.update(status="in-use", conclusion="adopt", reuse_evidence=["evidence/reuse.md"])
        self.flow["results"][0].update(status="pass", evidence=["evidence/result.md"])
        state.save(self.root, self.flow, TODAY)
        self.flow.update(revision=2, status="draft", conclusion="pilot", reuse_evidence=[])
        self.flow["results"][0].update(status="not-run", evidence=[])
        state.save(self.root, self.flow, TODAY)
        result = state.status(self.root, TODAY)["workflows"][0]
        self.assertEqual((result["revision"], result["last_verified_revision"], result["last_in_use_revision"]), (2, 1, 1))
        self.assertEqual(result["effective_revision"], 1)
        feedback = template("feedback")
        feedback.update(id="old-active-failure", synthetic=True, signal="failed",
                        workflow_ref={"id": self.flow["id"], "revision": 1})
        state.save(self.root, feedback, TODAY)
        result = state.status(self.root, TODAY)["workflows"][0]
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["reviewed_revisions"], [1, 2])

    def test_realistic_keep_without_new_tool_is_allowed(self):
        self.flow.update(capabilities=[], conclusion="keep", status="pilot-ready")
        self.flow["steps"][0].update(capabilities=[], owner="human")
        state.save(self.root, self.flow, TODAY)

    def test_duplicate_json_keys_and_nonfinite_are_rejected(self):
        p = self.parent / "bad.json"
        for payload in ('{"status":"draft","status":"in-use"}', '{"value":NaN}'):
            p.write_text(payload)
            with self.assertRaises(ValueError):
                state.read_json(p)

    def test_installer_and_installed_state_script(self):
        project = self.parent / "project"
        project.mkdir()
        install = ROOT / "scripts/install_skills.py"
        dry = subprocess.run([sys.executable, str(install), "--project", str(project), "--dry-run"], capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse((project / ".agents").exists())
        actual = subprocess.run([sys.executable, str(install), "--project", str(project)], capture_output=True, text=True)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        installed_skills = project / ".agents/skills"
        for name in ("ai-teacher", "work-memory"):
            source = ROOT / "plugins/ai-teacher/skills" / name
            for original in source.rglob("*"):
                if original.is_file():
                    installed = installed_skills / name / original.relative_to(source)
                    self.assertEqual(installed.read_bytes(), original.read_bytes())
        duplicate = subprocess.run([sys.executable, str(install), "--project", str(project)], capture_output=True, text=True)
        self.assertEqual(duplicate.returncode, 2)
        script = project / ".agents/skills/ai-teacher/scripts/teacher_state.py"
        result = subprocess.run([sys.executable, str(script), "status", "--workspace", str(self.root), "--as-of", TODAY.isoformat()], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["background_monitoring"])


if __name__ == "__main__":
    unittest.main()
