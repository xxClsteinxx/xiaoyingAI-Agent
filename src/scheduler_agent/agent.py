"""Bounded observe-decide-act loop and public result contract."""

from __future__ import annotations

from typing import Any, Dict, List

from .models import ModelError
from .tools import BusinessTools, summarize_observation


class SchedulingAgent:
    def __init__(self, model: Any, tools: BusinessTools, max_steps: int = 6) -> None:
        self.model = model
        self.tools = tools
        self.max_steps = max_steps

    def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
        errors = self._validate_request(request)
        if errors:
            return self._base_result(
                request,
                status="invalid_request",
                message="请求字段无效",
                trace=[],
                details={"validation_errors": errors},
            )
        observations: List[Dict[str, Any]] = []
        trace: List[Dict[str, Any]] = []
        for step in range(1, self.max_steps + 1):
            try:
                decision = self.model.decide(request, observations)
            except ModelError as error:
                return self._base_result(
                    request, "model_failed", str(error), trace, {"model_error": True}
                )
            action = decision.get("action")
            arguments = decision.get("arguments", {})
            basis = decision.get("decision_basis", "未提供")
            if trace:
                trace[-1]["next_action"] = action
            if action == "finish":
                trace.append(
                    {
                        "step": step,
                        "action": "finish",
                        "tool_parameters": arguments,
                        "return_summary": {"completed": True},
                        "next_action": None,
                        "decision_basis": basis,
                    }
                )
                return self._build_final(request, arguments, observations, trace)
            if action not in BusinessTools.TOOL_NAMES:
                return self._base_result(
                    request,
                    "model_failed",
                    "模型选择了未知动作",
                    trace,
                    {"unknown_action": action},
                )
            observation = self.tools.execute(action, arguments)
            observations.append({"action": action, "arguments": arguments, "observation": observation})
            trace.append(
                {
                    "step": step,
                    "action": action,
                    "tool_parameters": arguments,
                    "return_summary": summarize_observation(observation),
                    "next_action": None,
                    "decision_basis": basis,
                }
            )
        return self._base_result(
            request,
            "incomplete_step_limit",
            "达到最大执行步数，任务未完成",
            trace,
            {"max_steps": self.max_steps},
        )

    @staticmethod
    def _validate_request(request: Dict[str, Any]) -> List[str]:
        required = ["request_id", "asset_id", "publish_date", "required_time"]
        return ["missing:%s" % key for key in required if not request.get(key)]

    def _build_final(
        self,
        request: Dict[str, Any],
        finish: Dict[str, Any],
        observations: List[Dict[str, Any]],
        trace: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        by_tool = {item["action"]: item["observation"] for item in observations}
        review = by_tool.get("check_rules", {})
        slots = by_tool.get("query_slots", {})
        saved = by_tool.get("save_draft", {})
        requested_status = finish.get("status", "unknown")
        status = requested_status
        message = finish.get("message", "")
        # A model can choose actions, but cannot overrule observed business state.
        if "save_draft" in by_tool:
            if saved.get("saved"):
                status = "draft_exists" if saved.get("duplicate") else "draft_saved"
                message = "检测到重复提交，复用已有草稿" if saved.get("duplicate") else "草稿已保存；内容未发布"
            else:
                status = "save_failed"
                message = "草稿保存失败，不能声称已保存"
        elif review.get("review_status") == "incomplete":
            status = "needs_information"
            message = "素材必填信息缺失，阻断排期"
        elif review.get("review_status") == "blocked":
            status = "blocked"
            message = "素材存在高风险规则命中，禁止保存草稿"
        elif requested_status in ("draft_saved", "draft_exists"):
            status = "incomplete_model_termination"
            message = "模型声称保存成功，但没有成功的保存工具结果"
        proposed = None
        confirmation = "not_applicable"
        if "save_draft" in by_tool:
            save_action = next(item for item in observations if item["action"] == "save_draft")
            proposed = save_action["arguments"].get("proposed_time")
            confirmation = save_action["arguments"].get("confirmation_status", "not_applicable")
        elif slots.get("available_alternatives"):
            proposed = slots["available_alternatives"][0]
            confirmation = "pending_user_confirmation"
        details = {
            "asset_id": request["asset_id"],
            "review_status": review.get("review_status", "not_completed"),
            "risk_reasons": review.get("risks", []),
            "missing_fields": review.get("missing_fields", []),
            "requested_slot": "%s %s" % (request["publish_date"], request["required_time"]),
            "suggested_slot": ("%s %s" % (request["publish_date"], proposed)) if proposed else None,
            "confirmation_status": confirmation,
            "draft_save": {
                "attempted": "save_draft" in by_tool,
                "saved": bool(saved.get("saved")),
                "duplicate": bool(saved.get("duplicate")),
                "draft_id": saved.get("draft_id"),
                "error": saved.get("error"),
            },
            "published": False,
        }
        return self._base_result(
            request,
            status,
            message,
            trace,
            details,
        )

    def _base_result(
        self,
        request: Dict[str, Any],
        status: str,
        message: str,
        trace: List[Dict[str, Any]],
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "request_id": request.get("request_id"),
            "status": status,
            "message": message,
            "model": self.model.name,
            "real_model": self.model.is_real_model,
            "max_steps": self.max_steps,
            "steps_used": len(trace),
            "result": details,
            "trace": trace,
        }
