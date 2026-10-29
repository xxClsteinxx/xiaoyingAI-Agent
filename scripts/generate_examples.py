"""Regenerate committed evaluation artifacts from executable code."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scheduler_agent.agent import SchedulingAgent
from src.scheduler_agent.models import OfflineDecisionModel
from src.scheduler_agent.tools import BusinessTools


EXAMPLES = ROOT / "examples"


def load(name):
    return json.loads((ROOT / "data" / "requests" / (name + ".json")).read_text(encoding="utf-8"))


def run(request, store):
    tools = BusinessTools(draft_store=store, request=request)
    return SchedulingAgent(OfflineDecisionModel(), tools, max_steps=6).run(request)


def write(name, value):
    target = EXAMPLES / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    EXAMPLES.mkdir(exist_ok=True)
    for case_name in ("normal", "conflict", "missing", "risk", "save_failure"):
        write("inputs/%s.json" % case_name, load(case_name))
    with tempfile.TemporaryDirectory() as temp:
        common_store = Path(temp) / "drafts.json"
        write("01-normal-output.json", run(load("normal"), common_store))
        write("02-conflict-output.json", run(load("conflict"), common_store))
        write("03-conflict-duplicate-output.json", run(load("conflict"), common_store))
        write("04-missing-output.json", run(load("missing"), common_store))
        write("05-risk-output.json", run(load("risk"), common_store))
        write("06-save-failure-output.json", run(load("save_failure"), common_store))

    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    (EXAMPLES / "test-results.txt").write_text(
        "$ python -m unittest discover -s tests -v\n\n" + completed.stdout,
        encoding="utf-8",
    )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
