"""Phase 0 probe (one small live call, ~$0.05): does the hosted code tool work with the model llm.pick_models() picks,
at high reasoning, with files uploaded in and a file downloaded back, and is the transcript returned?

    OPENAI_API_KEY=... .venv/bin/python experiments/scripts/probe_code_tool.py

Prints what worked; writes the raw response to data/runs/probe-code-tool/response.json. Uploads only a toy file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core import llm  # noqa: E402


def main():
    c = llm.client()
    model = llm.pick_models()[0]
    print("model:", model)
    box = c.containers.create(name="aira-probe", memory_limit="1g")
    print("container:", box.id)
    c.containers.files.create(box.id, file=("guideline.txt", b"[g0001] The varicosities are at least 3 millimeters in size.\n"))
    c.containers.files.create(box.id, file=("helpers.py", b"T = open('guideline.txt').read()\ndef fq(q):\n    assert q in T, q\n    return q\n"))
    r = c.responses.create(
        model=model, reasoning={"effort": "high"},
        tools=[{"type": "code_interpreter", "container": box.id}], tool_choice="required",
        include=["code_interpreter_call.outputs"],
        input="In the python tool: import helpers; call helpers.fq('at least 3 millimeters') and also "
              "helpers.fq('at least 4 millimeters') (expect it to fail, then fix by using the right quote); "
              "write tree.json = {\"ok\": true, \"quote\": <the found quote>}; print OK.")
    out = ROOT / "data" / "runs" / "probe-code-tool"
    out.mkdir(parents=True, exist_ok=True)
    (out / "response.json").write_text(r.model_dump_json(indent=1))
    calls = [o for o in r.output if o.type == "code_interpreter_call"]
    print("code calls:", len(calls), "| first code:", (calls[0].code or "")[:120] if calls else None)
    print("outputs returned:", any(getattr(x, "outputs", None) for x in calls))
    print("usage:", r.usage.model_dump() if r.usage else None)
    files = c.containers.files.list(box.id)
    names = {f.path.split("/")[-1]: f.id for f in files}
    print("container files:", sorted(names))
    if "tree.json" in names:
        body = c.containers.files.content.retrieve(names["tree.json"], container_id=box.id).read()
        print("tree.json:", body[:200])
    c.containers.delete(box.id)


if __name__ == "__main__":
    main()
