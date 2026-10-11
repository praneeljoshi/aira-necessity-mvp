"""Step C (model, whole guideline, narrowed by the order) and its code checks.

    in:  g-spans; Order.procedure {cpt[], as_written, target}
    out: Guideline {payer, no_pathways_reason?, always_on}; Code[] (the whole table); Pathway[] (every coverable
         situation: names + ranges); chosen {pathway_ids, mapped_cpt?, why_refs}
    code: refs resolve (ids or line ranges) · ranges ordered · each code appears in the joined text of its cited
          lines · chosen ⊆ Pathway[] · no pathway whose heading is a limitation ("not covered", "not medically
          necessary", "investigational") · one heading per pathway
          -> one retry with the problem list -> problems kept on the result (a review reason, never a block)

Cached by (sha256, cpt[], target) in data/criteria/<key>.json together with step H.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.core import llm, log
from app.core.models import Code, Guideline, Narrowed, Pathway, Payer, Procedure, Range, Span
from app.ingest.spans import expand, render_guideline, resolves, table, text_of

logger = log.get("narrow")

# ---------------------------------------------------------------- the model's schema


class _Payer(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)


class _Range(BaseModel):
    first: str
    last: str


class _Code(BaseModel):
    code: str = Field(validation_alias=AliasChoices("code", "cpt", "hcpcs"))
    tag: str
    refs: list[str] = Field(default_factory=list)


class _Pathway(BaseModel):
    id: str
    spans: list[_Range]
    codes: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)


class _Mapped(BaseModel):
    code: str
    refs: list[str] = Field(default_factory=list)


class _Chosen(BaseModel):
    pathway_ids: list[str] = Field(default_factory=list)
    mapped_cpt: Optional[_Mapped] = None
    why_refs: list[str] = Field(default_factory=list)


class COut(BaseModel):
    payer: _Payer
    no_pathways_reason: Optional[list[str]] = None
    codes: list[_Code] = Field(default_factory=list)
    pathways: list[_Pathway] = Field(default_factory=list)
    chosen: _Chosen = Field(default_factory=_Chosen)

    @field_validator("no_pathways_reason", mode="before")
    @classmethod
    def _ids(cls, v):
        return [v] if isinstance(v, str) else v


TAGS = {"covered", "non_covered", "investigational", "not_addressed"}


# ---------------------------------------------------------------- checks


def code_in(code: str, text: str) -> bool:
    """The code is written in the text (the cited lines joined), or falls inside a range written there
    ("33227–33229")."""
    if re.sub(r"\s", "", code.lower()) in re.sub(r"\s", "", text.lower()):
        return True
    for a, b in re.findall(r"\b([A-Z]?\d{4}[A-Z0-9]?)\s*(?:[-–—]|through|to)\s*([A-Z]?\d{4}[A-Z0-9]?)\b", text):
        if len(a) == len(b) == len(code) and a[0].isdigit() == code[0].isdigit() and a <= code <= b:
            return True
    return False


def check(c: COut, spans: list[Span]) -> list[str]:
    tbl = table(spans)
    pos = {s.id: i for i, s in enumerate(spans)}
    problems: list[str] = []

    def exist(what: str, ids: list[str]):
        """Citations: ids or line ranges; each must resolve to spans of the document."""
        bad = [i for i in ids if not resolves(i, tbl)]
        if bad:
            problems.append(f"{what}: span ids not in the document: {', '.join(bad)}")

    def ordered(what: str, first: str, last: str):
        if first in pos and last in pos and pos[first] > pos[last]:
            problems.append(f"{what}: range {first}..{last} runs backwards")
        bad = [i for i in (first, last) if i not in tbl]
        if bad:
            problems.append(f"{what}: first/last must be single span ids of the document, not: {', '.join(bad)}")

    exist("payer", c.payer.refs)
    if c.no_pathways_reason:
        exist("no_pathways_reason", c.no_pathways_reason)
    seen: set[str] = set()
    for x in c.codes:
        if x.tag not in TAGS:
            problems.append(f"code {x.code}: tag '{x.tag}' is not one of {', '.join(sorted(TAGS))}")
        if x.code in seen:
            problems.append(f"code {x.code}: listed twice")
        seen.add(x.code)
        exist(f"code {x.code}", x.refs)
        ok = [i for i in x.refs if resolves(i, tbl)]
        if not x.refs:
            problems.append(f"code {x.code}: no span cited")
        elif ok and not code_in(x.code, text_of(ok, tbl)):
            problems.append(f"code {x.code}: the code does not appear in its cited span(s) {', '.join(ok)}")
    pids = [p.id for p in c.pathways]
    for p in c.pathways:
        where = f"pathway {p.id}"
        if pids.count(p.id) > 1:
            problems.append(f"{where}: id used twice")
        if not p.spans:
            problems.append(f"{where}: no spans")
        for j, r in enumerate(p.spans):
            ordered(f"{where} spans[{j}]", r.first, r.last)
        unknown = [x for x in p.codes if x not in seen]
        if unknown:
            problems.append(f"{where}: codes not in the code table: {', '.join(unknown)}")
    if not c.pathways and not c.no_pathways_reason:
        problems.append("no pathways and no no_pathways_reason")
    bad = [x for x in c.chosen.pathway_ids if x not in pids]
    if bad:
        problems.append(f"chosen: pathway ids not in pathways: {', '.join(bad)}")
    exist("chosen.why_refs", c.chosen.why_refs)
    m = c.chosen.mapped_cpt
    if m:
        if m.code not in seen:
            problems.append(f"chosen.mapped_cpt {m.code}: not in the code table")
        exist("chosen.mapped_cpt", m.refs)
    return problems


# ---------------------------------------------------------------- resolve


def resolve(c: COut, spans: list[Span], gid: str, sha: str, key: str, problems: list[str]) -> Narrowed:
    tbl = table(spans)
    codes = [Code(code=x.code, tag=x.tag if x.tag in TAGS else "covered", description=text_of(x.refs, tbl),
                  refs=x.refs) for x in c.codes]
    by = {x.code: x for x in codes}
    m = c.chosen.mapped_cpt
    mapped = None
    if m and m.code in by:
        mapped = by[m.code].model_copy(update={"refs": m.refs or by[m.code].refs})
    g = Guideline(id=gid, sha256=sha, payer=Payer(name=c.payer.name, aliases=c.payer.aliases),
                  no_pathways_reason=c.no_pathways_reason or None, refs=c.payer.refs)
    pathways = [Pathway(id=p.id, spans=[Range(first=r.first, last=r.last) for r in p.spans], codes=p.codes,
                        targets=p.targets) for p in c.pathways]
    pids = {p.id for p in pathways}
    return Narrowed(key=key, guideline=g, codes=codes, pathways=pathways,
                    chosen=[x for x in c.chosen.pathway_ids if x in pids], mapped_cpt=mapped,
                    why_refs=c.chosen.why_refs, problems=problems)


# ---------------------------------------------------------------- the call


def procedure_json(p: Procedure) -> str:
    import json
    return json.dumps({"cpt": p.cpt, "as_written": p.as_written, "target": p.target, "diagnosis": p.diagnosis}, indent=1)


def retry_prompt(base: str, previous: BaseModel, problems: list[str]) -> str:
    return (base + "\n\n## Your previous answer\n\n" + previous.model_dump_json(exclude_none=True)
            + "\n\n## Problems the code found in it\n\n" + "\n".join(f"- {p}" for p in problems)
            + "\n\nReturn the complete corrected JSON object, fixing every problem listed.")


def narrow(spans: list[Span], procedure: Procedure, gid: str, sha: str, key: str, run_id: str) -> Narrowed:
    base = llm.prompt("narrow_guideline", guideline_spans=render_guideline(spans), procedure_json=procedure_json(procedure))
    model = llm.pick_models()[0]
    out = llm.call(run_id, "narrow_guideline", base, COut, model=model, reasoning_effort="low")
    problems = check(out, spans)
    if problems:
        logger.warning("narrow: %d problem(s), retrying once: %s", len(problems), " | ".join(problems)[:300])
        out2 = llm.call(run_id, "narrow_guideline", retry_prompt(base, out, problems), COut, model=model,
                        reasoning_effort="low")
        p2 = check(out2, spans)
        if len(p2) <= len(problems):
            out, problems = out2, p2
    n = resolve(out, spans, gid, sha, key, problems)
    n.run_id = run_id
    logger.info("narrow %s: %d codes, %d pathways, chosen %s%s", key, len(n.codes), len(n.pathways), n.chosen,
                f", mapped {n.mapped_cpt.code}" if n.mapped_cpt else "")
    return n
