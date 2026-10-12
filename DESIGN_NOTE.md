# Design note

## What It Does

This tool reads both patient records and guidelines, and gives coordinators a checklist of criteria that could drive denials.

As the coordinator reviews the checklist, they are supplied with AI-sourced evidence that supports or weakens truthfulness of each criterion.
Alternatively, they can see criteria directly annotated on the original guidelines while they review.

If they choose - as they often should, especially on new codes or guidelines - they can prune or extend requirements by simply adding or removing annotations as they go. 

Rather than spending hours fishing for references, they arrive on click, and are compiled as issues or packets ready to send out. 

## What owns what:

- Models generate structure and logic as data from messy artifacts
    - constructs logical pathways (as truth trees) from guidelines
    - retrieves evidence from records

- Coordinators own judgement - validity and completeness:
    - all met vs not met decisions are manual, human-in-the-loop gates
    - work includes pruning or extending extracted pathways (sounds boring but honestly pretty natural and engaging)

- Code is the execution layer between them:
    - harnesses, retries
    - operations like expression evaluation (bit math)
    - slicing documents, pruning trees as needed

## Tradeoffs:
I traded: 

- false positives for false negatives : better to review non-issue than miss an issue
    - prioritized carefulness. always ref checked.

- narrow RAG (chunking) for wider harnesses (covering) :
    - less about exclusions and constraints and more about giving the models flexibility and tools
    - opted for whole documents with in-line indices rather than chunking and retrieval.
    - looser prompts, flexible outputs, reasoning/looping allowed measurably improved performance

- cost for evaluations : end-to-end runs for varying charts and guidelines
    - sourcing and simulating data. got creative with it

- agents for pipelines : observable, testable, cheaper
    - tested policy reduction against sandboxed agent (really bad), tools. ended up shipping a lazy call (v1.2-loose with a retry loop) which was actually better for cheaper

- automation for validation
    - code resolves references, nothing resolved truth trees. engagement is labelling
    - high false positive risk -> shouldn't ship something uncertain without the user being resourced to correct it
    - suggestions become fixtures ($$$)

## What breaks: 

- policy reduction on complex logic - shared subtrees, crossing, referential language (if pathway 1000 lines above AND...) (BCBS FL is generally clear, and short)
    - experiment with agents using declarative languages - json, python - to build reusable blocks that are easy to invoke
        * v1.2-form, v1.2-script

- evidence sourcing on really long charts, messy charts - especially if order is shuffled
    - maybe try some kind of event sourcing, walking the record (sliding window + merge/accumulate evidence)

- passive validators (approve approve approve)
    - make the experience engaging, fun, maybe rewarding - this data is quite valuable after all

- scaling to handle volume
    - preprocessed guidelines, async endpoints, job queues

## Next

- deploy, see what users think. engagement = product and data validation
- mine BCBS FL (for client) and other payer guidelines. preprocess common pathways.
