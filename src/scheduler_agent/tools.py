"""Deterministic business tools and guardrails.

The model may choose actions, but it cannot bypass these invariants:
hard risks block saving; changed times are pending confirmation; drafts are
idempotent; this project never publishes content.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
    temporary.replace(path)


class BusinessTools:
    """Local function tools. External services can replace this adapter."""

    TOOL_NAMES = ("read_asset", "check_rules", "query_slots", "save_draft")

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        draft_store: Optional[Path] = None,
        request: Optional[Dict[str, Any]] = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self.data_dir = Path(data_dir or project_root / "data")
        self.draft_store = Path(draft_store or project_root / "runtime" / "drafts.json")
        self.request = request or {}
        self.assets = _read_json(self.data_dir / "assets.json")
        self.rules = _read_json(self.data_dir / "rules.json")
        self.schedule = _read_json(self.data_dir / "schedule.json")

    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self.TOOL_NAMES:
            return {"ok": False, "error": "unknown_tool", "tool": name}
        try:
            return getattr(self, name)(**arguments)
        except TypeError as error:
            return {"ok": False, "error": "invalid_arguments", "detail": str(error)}
        except Exception as error:  # Tool boundaries must return observable failures.
            return {"ok": False, "error": "tool_exception", "detail": str(error)}

    def read_asset(self, asset_id: str) -> Dict[str, Any]:
        asset = self.assets.get(asset_id)
        if asset is None:
            return {"ok": False, "error": "asset_not_found", "asset_id": asset_id}
        return {"ok": True, "asset": asset}

    def check_rules(self, asset_id: str) -> Dict[str, Any]:
        asset = self.assets.get(asset_id)
        if asset is None:
            return {"ok": False, "error": "asset_not_found", "asset_id": asset_id}

        missing = [field for field in self.rules["required_fields"] if not asset.get(field)]
        risks: List[Dict[str, Any]] = []
        found_words = sorted(set(asset.get("sensitive_words", [])) & set(self.rules["blocked_words"]))
        if found_words:
            risks.append(
                {
                    "code": "BLOCKED_WORD",
                    "severity": "high",
                    "detail": "命中禁用宣传词：" + "、".join(found_words),
                }
            )
        if asset.get("type") == "video" and asset.get("duration_seconds", 0) > self.rules["max_video_seconds"]:
            risks.append(
                {
                    "code": "VIDEO_TOO_LONG",
                    "severity": "high",
                    "detail": "视频超过 %s 秒" % self.rules["max_video_seconds"],
                }
            )

        status = "approved"
        if missing:
            status = "incomplete"
        elif any(item["severity"] == "high" for item in risks):
            status = "blocked"
        return {"ok": True, "review_status": status, "missing_fields": missing, "risks": risks}

    def query_slots(
        self,
        publish_date: str,
        requested_time: str,
        alternative_times: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        day = self.schedule.get(publish_date, {})
        candidates = alternative_times or []
        return {
            "ok": True,
            "publish_date": publish_date,
            "requested_time": requested_time,
            "requested_available": requested_time not in day,
            "conflict": day.get(requested_time),
            "available_alternatives": [slot for slot in candidates if slot not in day],
            "occupied_alternatives": [slot for slot in candidates if slot in day],
        }

    def save_draft(
        self,
        request_id: str,
        asset_id: str,
        publish_date: str,
        proposed_time: str,
        requested_time: str,
        review_status: str,
        confirmation_status: str,
    ) -> Dict[str, Any]:
        if self.request.get("simulate_save_failure"):
            return {"ok": False, "error": "draft_store_unavailable", "saved": False}
        actual_review = self.check_rules(asset_id)
        if review_status != "approved" or actual_review.get("review_status") != "approved":
            return {"ok": False, "error": "review_not_approved", "saved": False}
        if proposed_time in self.schedule.get(publish_date, {}):
            return {"ok": False, "error": "proposed_slot_occupied", "saved": False}
        if proposed_time != requested_time and self.request.get("hard_time_requirement"):
            return {"ok": False, "error": "hard_time_requirement_cannot_change", "saved": False}
        if proposed_time != requested_time and confirmation_status != "pending_user_confirmation":
            return {"ok": False, "error": "changed_time_requires_confirmation", "saved": False}
        if proposed_time == requested_time and confirmation_status != "not_required":
            return {"ok": False, "error": "invalid_confirmation_status", "saved": False}

        store: Dict[str, Any] = {"drafts": {}}
        if self.draft_store.exists():
            store = _read_json(self.draft_store)
        drafts = store.setdefault("drafts", {})
        payload = {
            "request_id": request_id,
            "asset_id": asset_id,
            "publish_date": publish_date,
            "proposed_time": proposed_time,
            "requested_time": requested_time,
            "review_status": review_status,
            "confirmation_status": confirmation_status,
            "state": "draft",
            "published": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        existing = drafts.get(request_id)
        if existing:
            if existing["fingerprint"] == fingerprint:
                return {
                    "ok": True,
                    "saved": True,
                    "duplicate": True,
                    "draft_id": existing["draft_id"],
                    "state": "draft",
                    "published": False,
                }
            return {"ok": False, "error": "idempotency_conflict", "saved": False}

        draft_id = "DR-" + fingerprint[:10].upper()
        drafts[request_id] = dict(payload, draft_id=draft_id, fingerprint=fingerprint)
        _write_json(self.draft_store, store)
        return {
            "ok": True,
            "saved": True,
            "duplicate": False,
            "draft_id": draft_id,
            "state": "draft",
            "published": False,
        }


def summarize_observation(observation: Dict[str, Any]) -> Dict[str, Any]:
    """Bound trace size without hiding decision-relevant facts."""
    if "asset" in observation:
        asset = observation["asset"]
        return {
            "ok": observation["ok"],
            "asset_id": asset.get("id"),
            "fields": sorted(asset.keys()),
        }
    return observation
