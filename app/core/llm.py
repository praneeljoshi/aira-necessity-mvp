"""The only file that talks to the model.

Every call: JSON mode, pinned model, validated against a pydantic schema, one retry with the
validation error fed back, and the full exchange written to data/runs/<run_id>/.

Models: `pick_models()` returns the ship pins, gpt-6-sol for structure (B, C, H, A2) and gpt-6-luna for the
judge (I, ask), without asking the API. `MODEL_STRUCTURE` and `MODEL_JUDGE` in the environment override them.
`choose_flagship` (strongest GA flagship in a model list) is kept for scripts.

Reasoning models reject some sampling params (`temperature`, `seed`). `call` tries them, and when
the API rejects one it drops that param for the rest of the process and retries. Which params were
used and which were dropped is written to the run log.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional, Type, TypeVar

from openai import BadRequestError, OpenAI
from pydantic import BaseModel, ValidationError

from app.core import log

logger = log.get("llm")

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"
EXPERIMENT_PROMPTS = ROOT / "experiments" / "stepH" / "prompts"   # the experimental step-H modes' own prompts
RUNS = ROOT / "data" / "runs"

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None
_models: tuple[str, str] | None = None
_rejected: dict[str, set[str]] = {}  # model id -> params the API refused for it


def client() -> OpenAI:
    global _client
    if _client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set.")
        _client = OpenAI()
    return _client


# ---------------------------------------------------------------- model selection

# A flagship is a bare `gpt-<major>[.<minor>]` id. Suffixed ids (-pro, -mini, -nano, -codex,
# -chat-latest, codenames) are not flagships and are skipped by the regex itself.
_FLAGSHIP = re.compile(r"^gpt-(\d+)(?:\.(\d+))?$")
# A flagship counts as generally available when a dated snapshot of it is also listed.
_SNAPSHOT = re.compile(r"^gpt-(\d+(?:\.\d+)?)-\d{4}-\d{2}-\d{2}$")


def choose_flagship(ids: list[str]) -> str:
    """Strongest generally available non-pro flagship: highest 5.x, else newest 4.x."""
    snapshots = {m.group(1) for i in ids if (m := _SNAPSHOT.match(i))}
    ga: list[tuple[tuple[int, int], str]] = []
    for i in ids:
        m = _FLAGSHIP.match(i)
        if not m:
            continue
        ver = m.group(1) + ("." + m.group(2) if m.group(2) else "")
        if ver in snapshots:
            ga.append(((int(m.group(1)), int(m.group(2) or 0)), i))
    pool = [c for c in ga if c[0][0] == 5] or [c for c in ga if c[0][0] == 4]
    if not pool:
        raise RuntimeError(f"No generally available gpt-5.x or gpt-4.x flagship in the model list ({len(ids)} ids).")
    return max(pool)[1]


STRUCTURE_MODEL = "gpt-6-sol"     # the ship pin for B, C, H and A2
JUDGE_MODEL = "gpt-6-luna"        # the ship pin for I and ask


def pick_models(ids: Optional[list[str]] = None) -> tuple[str, str]:
    """(structure_model, judge_model): MODEL_STRUCTURE / MODEL_JUDGE when set, else the ship pins. No API call;
    `ids` is accepted for old callers and ignored (choose_flagship stays for scripts that want the list's pick)."""
    s = os.environ.get("MODEL_STRUCTURE") or STRUCTURE_MODEL
    j = os.environ.get("MODEL_JUDGE") or JUDGE_MODEL
    global _models
    if _models != (s, j):
        _models = (s, j)
        logger.info("models: structure=%s judge=%s", s, j)
    return s, j


# ---------------------------------------------------------------- plumbing


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def prompt_path(name: str) -> Path:
    """prompts/<name>.md; a name found only under experiments/stepH/prompts (the experimental step-H modes) is read
    from there, by the same name."""
    p = PROMPTS / f"{name}.md"
    if not p.exists() and (EXPERIMENT_PROMPTS / f"{name}.md").exists():
        return EXPERIMENT_PROMPTS / f"{name}.md"
    return p


def prompt(name: str, **vars: str) -> str:
    t = prompt_path(name).read_text()
    for k, v in vars.items():
        t = t.replace("{{" + k + "}}", v)
    return t


def _log(run_id: str, step: str, payload: dict) -> None:
    d = RUNS / run_id
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob(f"{step}*.json")))
    (d / f"{step}{'' if n == 0 else '-' + str(n)}.json").write_text(json.dumps(payload, indent=2, default=str))


def _rejected_param(e: BadRequestError, candidates: list[str]) -> Optional[str]:
    """Which of our optional params the API complained about, if any."""
    body = getattr(e, "body", None) or {}
    named = body.get("param") if isinstance(body, dict) else None
    if named in candidates:
        return named
    msg = str(e)
    for p in candidates:
        if re.search(rf"\b{re.escape(p)}\b", msg):
            return p
    return None


def _complete(model: str, messages: list[dict], reasoning_effort: Optional[str]) -> tuple[object, dict]:
    """One chat completion. Drops `temperature` / `seed` / `reasoning_effort` if the model rejects them."""
    optional: dict[str, object] = {"temperature": 0, "seed": 7}
    if reasoning_effort:
        optional["reasoning_effort"] = reasoning_effort
    dropped = sorted(_rejected.setdefault(model, set()))
    for _ in range(len(optional) + 1):
        kwargs = {k: v for k, v in optional.items() if k not in _rejected[model]}
        try:
            resp = client().chat.completions.create(
                model=model, response_format={"type": "json_object"}, messages=messages, **kwargs,
            )
            return resp, {"params_used": kwargs, "params_dropped": sorted(_rejected[model])}
        except BadRequestError as e:
            p = _rejected_param(e, list(kwargs))
            if p is None:
                raise
            logger.warning("%s rejects `%s`; retrying without it", model, p)
            _rejected[model].add(p)
            dropped.append(p)
    raise RuntimeError(f"{model}: could not find an accepted parameter set (dropped {dropped})")


def call(run_id: str, step: str, user_prompt: str, schema: Type[T], system: str | None = None,
         model: str | None = None, reasoning_effort: str | None = None, tally: Optional[dict] = None) -> T:
    """JSON-mode completion validated against `schema`. One retry on validation failure. `tally`, if given, adds up
    calls and tokens across calls (llm.dollars prices it)."""
    model = model or pick_models()[0]
    sys_msg = system or "You return only a JSON object. No prose, no markdown fences."
    schema_json = json.dumps(schema.model_json_schema(), indent=0)
    messages = [
        {"role": "system", "content": sys_msg + "\n\nThe JSON must validate against this JSON Schema:\n" + schema_json},
        {"role": "user", "content": user_prompt},
    ]
    last_err = None
    logger.info("-> %s [%s] %s chars%s", step, model, log.n(len(user_prompt)), f", reasoning {reasoning_effort}" if reasoning_effort else "")
    for attempt in range(2):
        t0 = time.time()
        resp, params = _complete(model, messages, reasoning_effort)
        raw = resp.choices[0].message.content or ""
        usage = resp.usage.total_tokens if resp.usage else 0
        if tally is not None and resp.usage:
            det = getattr(resp.usage, "prompt_tokens_details", None)
            tally["model"] = model
            tally["calls"] = tally.get("calls", 0) + 1
            tally["input_tokens"] = tally.get("input_tokens", 0) + (resp.usage.prompt_tokens or 0)
            tally["cached_tokens"] = tally.get("cached_tokens", 0) + ((getattr(det, "cached_tokens", 0) or 0) if det else 0)
            tally["output_tokens"] = tally.get("output_tokens", 0) + (resp.usage.completion_tokens or 0)
        logger.debug("   %s attempt %d params %s", step, attempt, params["params_used"])
        rec = {
            "step": step, "attempt": attempt, "model": model, "seconds": round(time.time() - t0, 2),
            **params,
            "usage": resp.usage.model_dump() if resp.usage else None,
            "dollars": dollars({"input_tokens": resp.usage.prompt_tokens or 0, "output_tokens": resp.usage.completion_tokens or 0,
                                "cached_tokens": (getattr(getattr(resp.usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0)},
                               model) if resp.usage else None,
            "messages": messages, "raw_response": raw,
        }
        try:
            parsed = schema.model_validate_json(raw)
            rec["parsed"] = parsed.model_dump()
            _log(run_id, step, rec)
            logger.info("<- %s ok %.1fs, %s tokens%s -> data/runs/%s/%s.json", step, time.time() - t0, log.n(usage),
                        f" (dropped: {', '.join(params['params_dropped'])})" if params["params_dropped"] else "", run_id, step)
            return parsed
        except (ValidationError, ValueError) as e:
            last_err = e
            rec["validation_error"] = str(e)
            _log(run_id, step, rec)
            logger.warning("<- %s attempt %d failed validation (%s); feeding the error back", step, attempt, str(e).splitlines()[0][:120])
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That JSON failed validation:\n{e}\n\nReturn a corrected JSON object only."},
            ]
    raise RuntimeError(f"{step}: model output failed validation twice: {last_err}")


# List prices per 1M tokens (as of 2026-10-10): input, cached input, output. A dated snapshot id prices as
# its base model. An unknown model prices as gpt-5.5 and is logged once, so a cost figure is never silently zero.
PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.5": (5.00, 0.50, 30.00),
}
_unpriced: set[str] = set()


def price_for(model: Optional[str]) -> tuple[float, float, float]:
    m = (model or "").lower()
    for k in sorted(PRICES, key=len, reverse=True):
        if m == k or m.startswith(k + "-"):
            return PRICES[k]
    if m not in _unpriced:
        _unpriced.add(m)
        logger.warning("no list price for model %r; costing it as gpt-5.5", model)
    return PRICES["gpt-5.5"]


def dollars(u: dict, model: Optional[str] = None) -> float:
    """A usage tally's dollars at the model's list price: input_tokens (cached ones at the cached rate; a tally's
    `cached_tokens` are part of input_tokens) and output_tokens. `model` from the tally when not given."""
    pi, pc, po = price_for(model or u.get("model"))
    inp, cached, out = u.get("input_tokens") or 0, u.get("cached_tokens") or 0, u.get("output_tokens") or 0
    return round(((inp - cached) * pi + cached * pc + out * po) / 1e6, 4)


# ---------------------------------------------------------------- the code sandbox (step H, STEP_H=code)


class CodeSession:
    """The model as a coding agent in a hosted sandbox (Responses API `code_interpreter` on a container we create).

    Files go in at the start; each `turn` is one response that may run many code cells; `fetch` downloads files the
    model wrote. Turns chain with previous_response_id. A container idle for 20 minutes expires: `turn` re-creates it
    and re-uploads the files. Everything (the input, every code cell and its output, usage, the uploaded files'
    hashes, the downloaded files) is written to data/runs/<run_id>/<step>.json, one file per turn."""

    def __init__(self, run_id: str, step: str, files: dict[str, bytes], model: Optional[str] = None,
                 effort: str = "high", memory: str = "1g"):
        import hashlib
        self.run_id, self.step, self.files, self.effort, self.memory = run_id, step, files, effort, memory
        self.model = model or pick_models()[0]
        self.hashes = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
        self.container: Optional[str] = None
        self.previous: Optional[str] = None
        self.usage = {"input_tokens": 0, "output_tokens": 0, "turns": 0, "containers": 0, "cells": 0}

    def _open(self) -> None:
        c = client()
        box = c.containers.create(name=f"aira-{self.run_id}-{self.step}"[:60], memory_limit=self.memory)
        for name, body in self.files.items():
            c.containers.files.create(box.id, file=(name, body))
        self.container = box.id
        self.usage["containers"] += 1
        logger.info("   %s container %s, %d files", self.step, box.id, len(self.files))

    def turn(self, text: str, instructions: Optional[str] = None) -> str:
        if self.container is None:
            self._open()
        t0 = time.time()
        kw = dict(model=self.model, reasoning={"effort": self.effort}, input=text,
                  tools=[{"type": "code_interpreter", "container": self.container}],
                  include=["code_interpreter_call.outputs"])
        if instructions:
            kw["instructions"] = instructions
        if self.previous:
            kw["previous_response_id"] = self.previous
        logger.info("-> %s [%s, code, %s] turn %d, %s chars", self.step, self.model, self.effort, self.usage["turns"] + 1,
                    log.n(len(text)))
        try:
            r = client().responses.create(**kw)
        except BadRequestError as e:          # the container expired between turns: a new one, same files
            if "container" not in str(e).lower():
                raise
            logger.warning("   %s container gone (%s); re-creating", self.step, str(e)[:120])
            self._open()
            kw["tools"] = [{"type": "code_interpreter", "container": self.container}]
            r = client().responses.create(**kw)
        self.previous = r.id
        cells = [o for o in r.output if getattr(o, "type", "") == "code_interpreter_call"]
        u = r.usage.model_dump() if r.usage else {}
        self.usage["input_tokens"] += u.get("input_tokens", 0) or 0
        self.usage["cached_tokens"] = self.usage.get("cached_tokens", 0) + ((u.get("input_tokens_details") or {}).get("cached_tokens") or 0)
        self.usage["output_tokens"] += u.get("output_tokens", 0) or 0
        self.usage["turns"] += 1
        self.usage["cells"] += len(cells)
        _log(self.run_id, self.step, {"step": self.step, "model": self.model, "effort": self.effort,
                                      "container": self.container, "seconds": round(time.time() - t0, 2),
                                      "uploaded": sorted(self.hashes), "uploaded_sha256": self.hashes, "input": text, "instructions": instructions,
                                      "usage": u, "response": json.loads(r.model_dump_json())})
        logger.info("<- %s %.1fs, %d code cells, %s tokens", self.step, time.time() - t0, len(cells),
                    log.n((u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)))
        return r.output_text or ""

    def fetch(self, name: str) -> Optional[bytes]:
        """A file the model wrote in the container (by its base name), or None."""
        if self.container is None:
            return None
        c = client()
        hits = [f for f in c.containers.files.list(self.container) if f.path.rsplit("/", 1)[-1] == name]
        if not hits:
            return None
        newest = max(hits, key=lambda f: getattr(f, "created_at", 0) or 0)
        body = c.containers.files.content.retrieve(newest.id, container_id=self.container).read()
        _log(self.run_id, f"{self.step}-file", {"name": name, "container": self.container,
                                                "content": body.decode("utf-8", "replace")})
        return body

    def close(self) -> None:
        if self.container:
            try:
                client().containers.delete(self.container)
            except Exception as e:   # it may have expired already
                logger.debug("container delete: %s", e)
            self.container = None

    def cost(self) -> float:
        """Dollars at the model's list price (cached input at its rate) plus $0.03 per 1 GB container session."""
        return round(dollars(self.usage, self.model) + 0.03 * self.usage["containers"], 4)


# ---------------------------------------------------------------- function tools on the host (step H, STEP_H=tools)


def call_tools(run_id: str, step: str, instructions: str, text: str, tools: list[dict], handle,
               done=lambda: False, model: Optional[str] = None, effort: str = "high", max_calls: int = 60,
               max_nudges: int = 2) -> dict:
    """One Responses session with function tools the host executes. `handle(name, args) -> dict` runs each call
    against the host's state; the loop ends when `done()` is true, the model stops calling tools (after up to
    `max_nudges` reminders), or `max_calls` tool calls were made. Every turn (input, each call with its arguments
    and result, usage) is written to data/runs/<run_id>/<step>.json, rewritten after each turn.

    Returns {"calls", "turns", "input_tokens", "cached_tokens", "output_tokens", "capped", "stopped", "dollars"}."""
    import hashlib
    model = model or pick_models()[0]
    tools = [{"type": "function", "strict": False, **t} for t in tools]
    rec = {"step": step, "model": model, "effort": effort,
           "given_sha256": {"instructions": hashlib.sha256(instructions.encode()).hexdigest(),
                            "input": hashlib.sha256(text.encode()).hexdigest()},
           "instructions": instructions, "input": text, "turns": []}
    usage = {"calls": 0, "turns": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "capped": False,
             "stopped": False}
    nxt: object = text
    previous = None
    nudges = 0
    t_all = time.time()
    while True:
        t0 = time.time()
        kw = dict(model=model, instructions=instructions, input=nxt, tools=tools, reasoning={"effort": effort})
        if previous:
            kw["previous_response_id"] = previous
        r = client().responses.create(**kw)
        previous = r.id
        u = r.usage.model_dump() if r.usage else {}
        usage["turns"] += 1
        usage["input_tokens"] += u.get("input_tokens") or 0
        usage["output_tokens"] += u.get("output_tokens") or 0
        usage["cached_tokens"] += ((u.get("input_tokens_details") or {}).get("cached_tokens") or 0)
        calls = [o for o in r.output if getattr(o, "type", "") == "function_call"]
        turn = {"seconds": round(time.time() - t0, 2), "usage": u, "said": r.output_text or "", "calls": []}
        outs = []
        for c in calls:
            if usage["calls"] >= max_calls:
                usage["capped"] = True
                break
            usage["calls"] += 1
            try:
                args = json.loads(c.arguments or "{}")
                res = handle(c.name, args)
            except Exception as e:        # a bad call is the model's to fix, not a crash
                args, res = c.arguments, {"ok": False, "problems": [f"{type(e).__name__}: {e}"[:300]]}
            turn["calls"].append({"name": c.name, "args": args, "result": res})
            outs.append({"type": "function_call_output", "call_id": c.call_id, "output": json.dumps(res)})
        rec["turns"].append(turn)
        rec["usage"] = usage
        _write(run_id, step, rec)
        logger.info("<- %s turn %d %.1fs: %s", step, usage["turns"], time.time() - t0,
                    ", ".join(f"{c['name']}{'' if (c['result'] or {}).get('ok') else ' ✗'}" for c in turn["calls"]) or "no tool call")
        if done() or usage["capped"]:
            break
        if not calls:
            if nudges >= max_nudges:
                usage["stopped"] = True
                break
            nudges += 1
            nxt = "Continue with the tools. You are finished only when submit returns ok."
            continue
        nxt = outs
    usage["model"] = model
    usage["dollars"] = dollars(usage, model)
    usage["seconds"] = round(time.time() - t_all, 1)
    rec["usage"] = usage
    _write(run_id, step, rec)
    logger.info("<- %s %d tool calls, %d turns, %.0fs, $%.2f (list price, before cache discount)%s", step,
                usage["calls"], usage["turns"], usage["seconds"], usage["dollars"],
                " CAPPED" if usage["capped"] else (" stopped without submit" if usage["stopped"] else ""))
    return usage


def _write(run_id: str, step: str, payload: dict) -> None:
    d = RUNS / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{step}.json").write_text(json.dumps(payload, indent=1, default=str))
