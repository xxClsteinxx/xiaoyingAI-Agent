import tempfile
import unittest
from pathlib import Path

from src.scheduler_agent.tools import BusinessTools


class GuardrailTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tools = BusinessTools(draft_store=Path(self.temp.name) / "drafts.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_cannot_save_unapproved_asset(self):
        result = self.tools.save_draft(
            "R1", "M03", "2026-11-01", "19:00", "19:00", "blocked", "not_required"
        )
        self.assertEqual("review_not_approved", result["error"])

    def test_changed_time_must_be_pending_confirmation(self):
        result = self.tools.save_draft(
            "R2", "M01", "2026-11-01", "19:00", "18:00", "approved", "not_required"
        )
        self.assertEqual("changed_time_requires_confirmation", result["error"])

    def test_model_cannot_lie_about_review(self):
        result = self.tools.save_draft(
            "R3", "M03", "2026-11-01", "19:00", "19:00", "approved", "not_required"
        )
        self.assertEqual("review_not_approved", result["error"])

    def test_occupied_slot_cannot_be_saved(self):
        result = self.tools.save_draft(
            "R4", "M01", "2026-11-01", "18:00", "18:00", "approved", "not_required"
        )
        self.assertEqual("proposed_slot_occupied", result["error"])


if __name__ == "__main__":
    unittest.main()
