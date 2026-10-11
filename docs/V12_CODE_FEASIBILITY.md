# v1.2-code, Phase 0: can step H run as a sandboxed coding agent on OpenAI?

Answer: **yes, on paper, with the model we already use.** The live probe (`scripts/probe_code_tool.py`, about $0.05) has
not run yet: it needs the API key. Run it once before the build is trusted.

Read 2026-10-10 from the vendor docs (links at the end). Nothing here is from memory.

## What exists

| Question | Answer | Source |
|---|---|---|
| Hosted code tool in the Responses API | Yes: tool `{"type": "code_interpreter", "container": ...}`, a sandboxed Python the model runs code in, many times within one response. A separate `hosted_shell` tool also exists. | tools guide |
| Works with our model | `gpt-5.5` (what `llm.pick_models()` picks today) lists Responses, `code_interpreter` and `hosted_shell` among its tools. | gpt-5.5 model page |
| At high reasoning | gpt-5.5 takes `reasoning.effort` none / low / medium / high / xhigh. The docs set no limit on combining it with the tool. | gpt-5.5 model page |
| Files in | Create a container (`POST /v1/containers`, memory 1g / 4g / 16g / 64g), then upload files to it (multipart or `file_id`). Or pass `file_ids` with `container: {type: "auto"}`. The SDK in `.venv` (openai 3.28.0) has `containers.create` and `containers.files.create / list / content`. | tools guide |
| Files out | List container files, then retrieve the content: we download `tree.json` ourselves. Files the model creates are also cited in `container_file_citation` annotations. | tools guide |
| Transcript | Each code run comes back as a `code_interpreter_call` item in `response.output`. `include=["code_interpreter_call.outputs"]` adds the execution outputs (logs). We store the whole response JSON. | responses create reference |
| Lifetime | A container expires after **20 minutes idle** and cannot be revived; its files are discarded. We re-verify on the host and keep our own copies, so this is fine. | tools guide |
| Rate limit | 100 RPM per org for containers. | tools guide |
| Max tool calls per response | Not documented on the pages read. The probe will show how many cells one response runs. | — |
| Determinism | gpt-5.5 rejects `temperature`; runs will vary, the same as today. | model behaviour |
| Data handling | The guideline text and the order go to a vendor container (no chart, no PHI: orders are synthetic in the harness). Containers are ephemeral, and on expiry their data is discarded. ZDR / residency apply per the account. | tools guide |

## Pricing

- **Tokens, gpt-5.5:** $5 / 1M input, $30 / 1M output (Batch and Flex half price).
- **Container:** 1 GB at $0.03 per 20-minute session per container, billed by the minute with a 5-minute minimum.
- **Known billing bug:** a community thread reports that `container: auto` charged $0.03 per response even when no code ran. We create the container explicitly, so we only pay when we use it.

**Estimate per order** (one session, about 5k-token guideline, 5–10 cells, tree.py about 300 lines, high reasoning):
- about 60–150k input tokens, re-read across turns, which is $0.30–0.75;
- about 15–30k output tokens including reasoning, which is $0.45–0.90;
- plus $0.03 for the container.

That makes **about $0.8–1.7 per order, or $120–260 for the 156.** Sessions per guideline (23 sessions; the swarm's shape, with shared blocks written once) should cut this by about 3–5×. Spec 3.6 allows it; I would start per order on the 3 smoke rows, read the real usage, then decide.

## Chosen route (pending the probe)

`llm.call_code(run_id, step, files, instructions, model, effort)` in `app/llm.py`:
1. create the container;
2. upload `guideline.txt` (g-ids as an index), `order.json`, `codes.json`, `helpers.py`, `BRIEF.md`;
3. one Responses call with `code_interpreter` on that container, `tool_choice=required`, `include=[outputs]`, high effort;
4. download `tree.json`;
5. log the whole response, the uploaded files' hashes, the downloaded files and the usage to `data/runs/<run>/criteria_code.json`;
6. delete the container.

The host then re-verifies with the same checks as v1.2-loose: quotes found, ids, logic. Failures go back to the same container if it is still alive, else a new one. That runs up to 3 rounds, then `needs_review`. The audit runs as a second turn in the same container: "patients who satisfy tree.json but the text denies; add and re-run", merged add-only on the host.

## Risks

- **Unprobed:** whether gpt-5.5 at `high` keeps iterating (write, run, fix) inside one response or stops after one cell. If it stops, the host loop does the iteration across calls, which costs a few more calls.
- **Cost:** see above; batch per guideline if the smoke rows show more than $1 per order.
- **Container expiry mid-loop:** handled by re-upload.
- **The docs don't state a max cell count per response:** the probe measures it.

## If OpenAI fails the probe (the vendor choice is a separate decision)

- Anthropic Messages API code-execution tool, or Managed Agents.
- OpenAI Agents SDK with a locally hosted Python sandbox.
- Spec section 5, no sandbox: the model returns the JSON form (conditions, named blocks, logic). Host code runs the `helpers` checks and sends the failures back for 2–3 rounds, then the add-only audit. This is also the cheapest.

## Policies, flags default ON (spec 3.2)

- **A:** prune routes only on facts the order fixes.
- **C:** an ambiguous and/or takes the stricter reading, with the alternative in `notes`.
- **D:** a condition from another section only when the text links it.
- **E:** an impossible literal condition is left out of its route and explained in `notes`.
- **B (always):** an unanswerable condition, wherever it sits (including under `not`), becomes a review reason, never MET or NOT_MET.

## Sources

- Code interpreter guide: https://developers.openai.com/api/docs/guides/tools-code-interpreter
- gpt-5.5 model page: https://developers.openai.com/api/docs/models/gpt-5.5
- Pricing: https://developers.openai.com/api/docs/pricing
- Responses create (`include`): https://developers.openai.com/api/reference/resources/responses/methods/create
- Container auto-billing thread: https://community.openai.com/t/responses-api-excessive-charges-due-to-repetitive-container-creation-when-using-code-interpreter/1364328
