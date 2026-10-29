"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import SchedulingAgent
from .models import ModelError, OfflineDecisionModel, OpenAIResponsesDecisionModel
from .tools import BusinessTools


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="素材审核与发布排期 Agent")
    parser.add_argument("--input", required=True, help="请求 JSON 文件")
    parser.add_argument("--model", choices=("offline", "openai"), default="offline")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--draft-store", help="草稿存储路径；默认 runtime/drafts.json")
    parser.add_argument("--output", help="将结果同时写入指定 JSON")
    return parser


def main(argv=None) -> int:
    # Keep redirected output and Windows terminals consistent with JSON files.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    if args.max_steps < 1:
        print("--max-steps must be >= 1", file=sys.stderr)
        return 2
    with Path(args.input).open("r", encoding="utf-8") as handle:
        request = json.load(handle)
    try:
        model = OfflineDecisionModel() if args.model == "offline" else OpenAIResponsesDecisionModel()
    except ModelError as error:
        print(json.dumps({"status": "configuration_error", "message": str(error)}, ensure_ascii=False))
        return 2
    tools = BusinessTools(
        draft_store=Path(args.draft_store) if args.draft_store else None,
        request=request,
    )
    result = SchedulingAgent(model=model, tools=tools, max_steps=args.max_steps).run(request)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    successful = {"draft_saved", "draft_exists", "needs_information", "needs_confirmation", "blocked"}
    return 0 if result["status"] in successful else 1


if __name__ == "__main__":
    sys.exit(main())
