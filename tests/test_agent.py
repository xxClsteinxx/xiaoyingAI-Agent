import json
import tempfile
import unittest
from pathlib import Path

from src.scheduler_agent.agent import SchedulingAgent
from src.scheduler_agent.models import OfflineDecisionModel
from src.scheduler_agent.tools import BusinessTools


ROOT = Path(__file__).resolve().parents[1]


def load_request(name):
    with (ROOT / "data" / "requests" / (name + ".json")).open(encoding="utf-8") as handle:
        return json.load(handle)


class SchedulingAgentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name) / "drafts.json"

    def tearDown(self):
        self.temp.cleanup()

    def run_case(self, request, max_steps=6):
        tools = BusinessTools(draft_store=self.store, request=request)
        return SchedulingAgent(OfflineDecisionModel(), tools, max_steps=max_steps).run(request)

    def test_normal_schedule_saves_draft(self):
        result = self.run_case(load_request("normal"))
        self.assertEqual("draft_saved", result["status"])
        self.assertTrue(result["result"]["draft_save"]["saved"])
        self.assertEqual("not_required", result["result"]["confirmation_status"])
        self.assertFalse(result["result"]["published"])

    def test_missing_metadata_blocks_before_slot_query(self):
        result = self.run_case(load_request("missing"))
        self.assertEqual("needs_information", result["status"])
        self.assertEqual(["target_channel"], result["result"]["missing_fields"])
        self.assertNotIn("query_slots", [step["action"] for step in result["trace"]])
        self.assertFalse(result["result"]["draft_save"]["attempted"])

    def test_rule_risk_blocks_draft(self):
        result = self.run_case(load_request("risk"))
        self.assertEqual("blocked", result["status"])
        self.assertEqual("BLOCKED_WORD", result["result"]["risk_reasons"][0]["code"])
        self.assertFalse(result["result"]["draft_save"]["attempted"])

    def test_conflict_changes_to_available_slot_and_requires_confirmation(self):
        result = self.run_case(load_request("conflict"))
        self.assertEqual("draft_saved", result["status"])
        self.assertEqual("2026-11-01 19:00", result["result"]["suggested_slot"])
        self.assertEqual("pending_user_confirmation", result["result"]["confirmation_status"])
        self.assertFalse(result["result"]["published"])

    def test_duplicate_submission_reuses_one_draft(self):
        request = load_request("conflict")
        first = self.run_case(request)
        second = self.run_case(request)
        self.assertEqual("draft_saved", first["status"])
        self.assertEqual("draft_exists", second["status"])
        self.assertEqual(
            first["result"]["draft_save"]["draft_id"],
            second["result"]["draft_save"]["draft_id"],
        )
        with self.store.open(encoding="utf-8") as handle:
            self.assertEqual(1, len(json.load(handle)["drafts"]))

    def test_save_failure_is_explicit(self):
        result = self.run_case(load_request("save_failure"))
        self.assertEqual("save_failed", result["status"])
        self.assertFalse(result["result"]["draft_save"]["saved"])
        self.assertEqual("draft_store_unavailable", result["result"]["draft_save"]["error"])

    def test_hard_requirement_is_not_changed(self):
        request = load_request("conflict")
        request["request_id"] = "REQ-HARD-001"
        request["hard_time_requirement"] = True
        result = self.run_case(request)
        self.assertEqual("needs_confirmation", result["status"])
        self.assertFalse(result["result"]["draft_save"]["attempted"])

    def test_step_limit_returns_incomplete(self):
        result = self.run_case(load_request("normal"), max_steps=2)
        self.assertEqual("incomplete_step_limit", result["status"])
        self.assertEqual(2, result["steps_used"])

    def test_trace_has_required_audit_fields(self):
        result = self.run_case(load_request("conflict"))
        required = {"step", "action", "tool_parameters", "return_summary", "next_action", "decision_basis"}
        for step in result["trace"]:
            self.assertEqual(required, set(step))


if __name__ == "__main__":
    unittest.main()

