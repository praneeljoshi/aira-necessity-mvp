# Check status: stages, gates, and what resuming would take

Branch `v1.1-ui`. The status feature (app/status.py, the hook in `pipeline.run`, `/api/orders/{id}/status`) exists so
the coordinator sees where a check is from the moment the chart is uploaded, and so that approval gates and error
gates have a place to live. This note records the model as built, what the pipeline would need to pause and resume
at a gate, and what was left for later.

## What exists

**Upload returns at once.** `POST /api/charts` reads the PDF, creates a `Recorder` (which writes
`data/results/<chart_id>/status.json` immediately) and runs `pipeline.run` in a daemon thread. The page polls
`GET /api/orders/{id}` (which answers `{pending: true, status}` until a result exists) and `GET /api/orders/{id}/status`.
`POST /api/orders/{id}/recheck` and `POST /api/orders/{id}/retry` start the same way. `main.BACKGROUND = False`
runs inline (tests, and anyone who wants the old synchronous answer).

**Every run writes a status**, browser or CLI: `pipeline.run` makes a persisting `Recorder` when none is passed.
Only the latest run of a chart is kept (a re-check overwrites status.json, like it overwrites result.json).

### Stages

| id | pipeline step | label on screen | summary example | cached? | log |
|---|---|---|---|---|---|
| chart | A | Reading the chart | 85 lines over 3 pages from linda_park.pdf | | |
| order | B | Finding the order | Linda Park · Endovenous laser ablation… (36478) · Florida Blue | re-check: order kept | detect_order |
| guideline | C | Reading the guideline for this order | Florida Blue: 5 section(s) that grant coverage, 42 code(s) in the table | yes | narrow_guideline |
| section | E-G | Checking the code and choosing the section | Code 36478 is covered; section: Great or Small Saphenous Veins | | |
| checklist | H | Building the requirement checklist | 12 requirement(s) under “Great or Small Saphenous Veins” | yes | criteria_guideline |
| read | I | Reading the chart against it | 9 of 9 requirement(s) answered | | judge_chart |
| verify | J | Checking every quote and date | 18 quote(s) found in the chart, 6 date(s) verified; 1 thing(s) to check by hand | | |
| decide | K-L | Deciding | the result's one sentence | | |

Stage status: `waiting · running · done · needs_person · failed · skipped`. Each stage record holds
`started_at`, `ended_at`, `summary`, `cached`, `logs: [{file, url}]` (the run-log files of its model step, served
by `GET /api/runs/{run_id}/{step}`), `gate`, `error` (+ `traceback` when it raised).

The document: `{chart_id, guideline_id, filename, source, override, run_id, state, started_at, ended_at, current,
error, order{patient_name, procedure_text, cpt, payer} (after B), stages[], resume: null}`. `state` is
`running` until `Recorder.close()` sets `done` or `needs_person` (any stage ended that way), or a stage raised
and set `failed`.

### Gates: where a person may need to act

A gate is a stage that ended `needs_person`, with `gate = {kind, title, needs, options, action, blocking}`.
`needs` is the plain-words sentence; `options` are the choices or the reasons; `action` names what resumes it in
the existing API (`{"recheck": {"field": "target" | "cpt" | "guideline_id"}}`); `blocking` says whether the
pipeline could go on without the answer.

| kind | stage | raised when | options | action | blocking | what the pipeline does today |
|---|---|---|---|---|---|---|
| confirm_code | section | a code gate is `mapped` (the code came from the procedure name, not the chart) | the mapped code | recheck.cpt | no | goes on with the mapped code; the result carries the review reason |
| which_section | section | no pathway chosen, `Selection.candidates` non-empty | candidate section names | recheck.target | yes | stops short by itself: H, I, J are `skipped`, the result is the "which of these?" ask |
| guideline_problems | guideline | `Narrowed.problems` after the retry | the problems | recheck.guideline_id | no | goes on; review reason |
| checklist_problems | checklist | `CriteriaSet.status == needs_review` | the problems | – | no | goes on; review reason |
| review | decide | `Result.queue != ready` (the ask goes to a person) | `review_reasons` | – | no | the end of the run |
| *(error)* | any | a stage raised | – | `POST /retry` | – | stops; later stages stay `waiting`; `state = failed` |

| confirm_pathways | section | the review flow (`pipeline.run(pause_at_pathways=True)`) and every code passed the code gate | the suggested section names ([] when the model chose none) | `{"confirm": {"endpoint": "/api/review/<id>/pathways"}}` | yes | **pauses**: `selection.json` written, `state = paused`, `resume = {stage: checklist, needs: pathways, key, endpoint}`; `pipeline.resume` continues from H with the confirmed picks |

In the `/` flow nothing pauses: a gate is recorded and the pipeline behaves as before (pipeline logic
unchanged). The screen shows the gate inside the stage with the re-check form for its field (a radio list of the
candidate sections for `which_section`, the code box for `confirm_code`, the guideline picker for
`guideline_problems`) and "Run it again" for an error. The queue lists a running check under "Checking now" with
its stage, and a failed one under "Stopped — needs a look".

## Resuming, as built for the review flow

`pipeline.resume(chart_id, picks, by)` (POST `/api/review/{id}/pathways`) implements points 1–4 and 6 below for the
`confirm_pathways` gate: the selection is on disk at the pause (`selection.json`), the recorder is restored from
status.json (`Recorder.from_doc`) and keeps the run_id, the section stage is marked `done` with
`answered_by = {by, at, confirmed, suggested}` and `gate.answered = true`, the stages after it run as in `run`
(the H..K-L body is shared: `_checklist`, `_judge_and_decide`, `_decide`). H is cached by the confirmed sections
(`h_cache_key`: sha16 + sorted pathway ids + a hash of their ranges + the order facts), separately from the order's C/H cache, so a
person's different pick never overwrites the model's. `pathways.json` beside the result is the audit record. A
resume that fails is retried from the stored picks (`POST /api/review/{id}/retry`); `/api/orders/{id}/retry`
answers 409 for a paused check. Point 5 (one run per chart) is still not enforced.

## What resuming from a gate would need (the general design)

The goal is an "approve and continue" that pauses the run at a blocking gate (and, when asked, at non-blocking
ones), lets the coordinator answer, and continues *from that stage* without redoing A–C.

1. **Persist each stage's output as it is produced, not only at the end.** Today A (chart spans), B (order) and
   C/H (the criteria cache) are on disk when their stage ends, but `Selection` (E-G) and the verdicts (I/J) are
   written only by `save_result` at K/L. Resuming after `section` needs `selection.json` written at the end of
   the section stage, and resuming after `read` needs `verdicts.json` then. `store.save_result` would split into
   `save_selection`, `save_verdicts`, `save_result`.
2. **A pause in `pipeline.run`.** `run(..., pause_at: set[str] = ())`: after a stage raises a gate whose kind is
   in `pause_at` (default: every `blocking` gate), the recorder sets `state = "paused"`, `resume = {"stage":
   <next stage id>, "needs": <the gate's field>}` and `run` returns `None` without deciding. The queue shows
   "Waiting for you" (a fourth group) instead of a result. Today the blocking case already produces a
   result (the "which section" ask); with pausing it would not, so `result.py`'s which-section branch becomes
   the message shown *at the gate*, not a stored result.
3. **A resume entry point.** `run(..., resume_from: str)` skips the stages before `resume_from`, loading their
   outputs from disk (chart spans, order + override, criteria cache, selection, verdicts) and marking them
   `done` with `cached = true` and the earlier summaries kept; then continues. The coordinator's answer arrives
   as an override (`cpt`, `target`, `guideline_id`) merged as `recheck` merges today; a changed `target` or
   `guideline_id` invalidates the cache key, so resume falls back to the `guideline` stage automatically (the
   key changed), a confirmed `cpt` that equals the mapped code resumes at `checklist`.
4. **An endpoint.** `POST /api/orders/{id}/continue {approve: true, cpt?, target?, guideline_id?}` →
   `_start(..., resume_from=status.resume.stage)`. `retry` becomes `continue` with `resume_from` = the failed
   stage (its inputs are on disk by rule 1), instead of re-running from A as it does now.
5. **One run per chart at a time.** A per-`chart_id` lock in `main._start` (409 while running; `retry` already
   refuses a running check). Two uploads of the same file are two charts today, which is fine.
6. **Run-log continuity.** A resumed run should keep the original `run_id` so `data/runs/<run_id>/` holds the
   whole story; `llm._log` already numbers repeated steps (`judge_chart-1.json`). Add `resumed_from` and
   `answered_by` (what the person chose, when) to the stage record for the audit trail.
7. **Guideline upload as a stage.** Ingest is code only (`add_guideline` splits lines; no model call) and takes
   under a second, so it has no stage. If structuring moves to upload time again, it becomes stage `ingest`
   before `chart`, with its own cache flag (same sha256 → cached).

## Left for later

- Pausing at the other gates: only `confirm_pathways` (the review flow) pauses. `confirm_code`, `which_section`
  and the problem gates are recorded and the `/` flow does not wait.
- Status history: only the latest run per chart is kept. A `status-<run_id>.json` per run would give the
  coordinator "what happened the first time".
- The CLI writes status.json but prints nothing new; `app.cli.show` could print the stage times.
- `GET /api/orders` reads every status.json on each poll; fine at tens of charts, index it when it is hundreds.
- The tree page (`/patients/{id}/tree`) shows every judged section; when several codes or sections are judged it does
  not single out the one that decided. Its "which section" chooser posts the section name as the `target`.
- The note heading shown beside a quote on the tree page is a display heuristic over the chart's own lines
  (nearest heading-like line, then the dated note heading above it). The page number and the quoted text are
  exact; the heading is a reading aid and says so in "How this was decided".
