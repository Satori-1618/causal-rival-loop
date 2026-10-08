# Live-run release checklist

There is no live release in this repository by default. The commands below show
the workflow, not authorization to execute it.

1. Complete development review and pin every live generation setting in a new
   configuration: provider, exact model revision, generation options, input and
   output caps, tokenizer encoding, timeouts, prices used for budget accounting,
   and the total dollar ceiling. Counts and intervention semantics are fixed by
   the protocol; descriptive config fields are not a way to change the design.
2. Prepare the inputs and complete development qualification and tests.
3. Commit the clean protocol/code/config surface and create a split-specific
   freeze. Publish the committed source and freeze artifact before the first
   outcome for that split. Preserve publication evidence.
4. Obtain review of that exact freeze, then a human execution release bound to
   both the freeze and review. An agent's approval is not human authorization.
5. Execute once, preserve all failures, verify, and analyze.

Example command sequence after configured development qualification:
Use the executable installed in this source checkout's virtual environment.

```bash
.venv/bin/rival-loop freeze --prepared artifacts/prepared \
  --qualification artifacts/qualification.json \
  --split development --out artifacts/freeze-development

.venv/bin/rival-loop run --prepared artifacts/prepared \
  --freeze artifacts/freeze-development \
  --review records/review-development.json \
  --release records/release-development.json \
  --out artifacts/run-development --split development --execute

.venv/bin/rival-loop verify --run artifacts/run-development
.venv/bin/rival-loop analyze --run artifacts/run-development --out artifacts/development-analysis.json
```

After development amendments, prepare and freeze the final evaluation contract
again. The new preparation must preserve the development population and its
held-out split. An evaluation freeze requires a completed live development run:

```bash
.venv/bin/rival-loop freeze --prepared artifacts/prepared-evaluation \
  --qualification artifacts/qualification-evaluation.json \
  --development-run artifacts/run-development \
  --split evaluation --out artifacts/freeze-evaluation
```

Run evaluation with `--split evaluation` and its own review/release. Development
evidence never substitutes for a final evaluation release. The run bundle copies
the bound freeze, review, release, and complete prepared population (including
its manifest and private labels) so an independent reader can inspect them.
The verifier checks that the run uses exactly the frozen split and case order.
Their public evidence URLs still require external checking.

Execution creates a local, create-only claim in the freeze directory before any
provider call. Reusing that directory refuses another execution. Deleting or
copying the directory can bypass a local claim, so public execution history
remains part of independent review. Do not use a copied directory to retry an
unsuccessful round; record a proposed amendment and obtain review first.

The reviewer supplies a JSON record in this shape:

```json
{
  "status": "PASS",
  "freeze_sha256": "ACTUAL_FREEZE_HASH",
  "reviewer": "IDENTIFIED_REVIEWER",
  "evidence_url": "PUBLIC_REVIEW_EVIDENCE",
  "public_freeze": {
    "commit": "ACTUAL_PUBLIC_COMMIT",
    "url": "PUBLIC_FREEZE_URL",
    "published_at": "ACTUAL_UTC_PUBLICATION_TIME"
  }
}
```

A separate human release supplies:

```json
{
  "authorized": true,
  "freeze_sha256": "ACTUAL_FREEZE_HASH",
  "review_sha256": "ACTUAL_REVIEW_FILE_HASH",
  "authorization": "VERBATIM_HUMAN_EXECUTION_INSTRUCTION",
  "authorized_by": "HUMAN_NAME",
  "authorized_at": "ACTUAL_UTC_AUTHORIZATION_TIME"
}
```

These are shapes for independently supplied records, not completed certificates.
Do not copy placeholders into a released run. Hash checks establish artifact
binding, not honesty of a reviewer name or external publication timestamp. Those
claims need inspectable external evidence. The runner does not publish the repo
or create a review or release on a user's behalf.

The live OpenAI adapter requires the `live` optional dependency and a normal API
credential in the environment. Credentials are neither written into run
artifacts nor considered permission to spend. The budget caps and execution
release remain mandatory. There are no provider repair or retry calls.
The adapter uses the official [Responses API text-generation interface](https://developers.openai.com/api/docs/guides/text):
an explicitly pinned model revision, no tools, no conversation state, and no
server-side response storage. The frozen price assumptions and server-reported
token usage are recorded separately from scientific outcomes.

The dollar limit is checked using the prices explicitly recorded in the freeze,
including a worst-case reservation before each call. Those are budget-accounting
assumptions, not a guarantee that an external provider's invoice uses the same
prices. Verify them before release. Transport failures may still be billable and
retain the reservation rather than counting as free calls.
The run timeout is checked between generation attempts; an attempt already in
progress can finish up to its per-request timeout after that boundary.
