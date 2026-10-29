"""Decision-model adapters: offline flow mock and live Responses API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List


class ModelError(RuntimeError):
    pass


class OfflineDecisionModel:
    """Transparent deterministic flow mock; it does not prove LLM quality."""

    name = "offline-policy-mock"
    is_real_model = False

    def decide(
        self, request: Dict[str, Any], observations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        by_tool = {item["action"]: item["observation"] for item in observations}
        asset_id = request["asset_id"]
        if "read_asset" not in by_tool:
            return self._action("read_asset", {"asset_id": asset_id}, "先读取素材元数据")
        asset_result = by_tool["read_asset"]
        if not asset_result.get("ok"):
            return self._finish("blocked", "素材不存在，无法继续审核", "missing_asset")

        if "check_rules" not in by_tool:
            return self._action("check_rules", {"asset_id": asset_id}, "元数据已读取，执行审核规则")
        review = by_tool["check_rules"]
        if review.get("review_status") == "incomplete":
            return self._finish("needs_information", "素材必填信息缺失，阻断排期", "missing_metadata")
        if review.get("review_status") == "blocked":
            return self._finish("blocked", "素材存在高风险规则命中，禁止保存草稿", "rule_risk")

        if "query_slots" not in by_tool:
            return self._action(
                "query_slots",
                {
                    "publish_date": request["publish_date"],
                    "requested_time": request["required_time"],
                    "alternative_times": request.get("alternative_times", []),
                },
                "审核通过，检查要求时段和备选时段",
            )
        slots = by_tool["query_slots"]
        if "save_draft" not in by_tool:
            requested = request["required_time"]
            if slots.get("requested_available"):
                proposed = requested
                confirmation = "not_required"
                basis = "要求时段可用，保存无需额外确认的草稿"
            elif request.get("hard_time_requirement"):
                return self._finish("needs_confirmation", "硬性时段冲突，不擅自改期", "hard_time_conflict")
            elif slots.get("available_alternatives"):
                proposed = slots["available_alternatives"][0]
                confirmation = "pending_user_confirmation"
                basis = "要求时段冲突，选择首个可用备选并标记待用户确认"
            else:
                return self._finish("needs_confirmation", "时段冲突且没有可用备选", "no_available_slot")
            return self._action(
                "save_draft",
                {
                    "request_id": request["request_id"],
                    "asset_id": asset_id,
                    "publish_date": request["publish_date"],
                    "proposed_time": proposed,
                    "requested_time": requested,
                    "review_status": review["review_status"],
                    "confirmation_status": confirmation,
                },
                basis,
            )
        saved = by_tool["save_draft"]
        if not saved.get("ok"):
            return self._finish("save_failed", "草稿保存失败，不能声称已保存", "save_tool_failure")
        if saved.get("duplicate"):
            return self._finish("draft_exists", "检测到重复提交，复用已有草稿", "idempotent_duplicate")
        return self._finish("draft_saved", "草稿已保存；内容未发布", "draft_only")

    @staticmethod
    def _action(action: str, arguments: Dict[str, Any], basis: str) -> Dict[str, Any]:
        return {"action": action, "arguments": arguments, "decision_basis": basis}

    @staticmethod
    def _finish(status: str, message: str, basis: str) -> Dict[str, Any]:
        return {
            "action": "finish",
            "arguments": {"status": status, "message": message},
            "decision_basis": basis,
        }


class OpenAIResponsesDecisionModel:
    """Minimal dependency-free OpenAI Responses API adapter."""

    is_real_model = True

    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ModelError("OPENAI_API_KEY is required for --model openai")
        self.name = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def decide(
        self, request_data: Dict[str, Any], observations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read_asset", "check_rules", "query_slots", "save_draft", "finish"]},
                "arguments": {"type": "object", "additionalProperties": True},
                "decision_basis": {"type": "string"},
            },
            "required": ["action", "arguments", "decision_basis"],
            "additionalProperties": False,
        }
        instructions = (
            "你是素材审核与发布排期 Agent。每轮只返回一个 JSON 动作。"
            "可用动作 read_asset/check_rules/query_slots/save_draft/finish。"
            "必须先读素材再检查规则，再查时段；高风险或信息缺失时 finish。"
            "时段冲突时可选备选，但改变用户时段必须将 confirmation_status 设为 "
            "pending_user_confirmation；硬性要求不可改。只保存 draft，绝不能声称发布。"
            "工具失败必须明确 finish，保存失败不能声称成功。"
        )
        prompt = json.dumps(
            {"request": request_data, "tool_observations": observations},
            ensure_ascii=False,
        )
        payload = {
            "model": self.name,
            "instructions": instructions,
            "input": prompt,
            "store": False,
            "text": {"format": {"type": "json_schema", "name": "agent_action", "strict": False, "schema": schema}},
        }
        req = urllib.request.Request(
            self.base_url + "/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ModelError("Responses API HTTP %s: %s" % (error.code, detail[:500]))
        except (urllib.error.URLError, TimeoutError) as error:
            raise ModelError("Responses API unavailable: %s" % error)
        text_parts = []
        for output in body.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    text_parts.append(content.get("text", ""))
        if not text_parts:
            raise ModelError("Responses API returned no output_text")
        try:
            return json.loads("".join(text_parts))
        except json.JSONDecodeError as error:
            raise ModelError("Model returned invalid JSON: %s" % error)
