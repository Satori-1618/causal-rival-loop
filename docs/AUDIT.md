# Engineering review — 8 October 2026

**Status: implementation checks passed; no live experiment released.**

This records the initial engineering review, not the final design review.
The later review found a selector blind spot, an unbound archived template,
and tokenizer fragility. [Amendment 001](AMENDMENT_001.md) records their
corrections and regression checks before the source/input freeze.

## Re-review of Amendment 001

Two agents separately re-reviewed the design and engineering changes; neither
found a remaining blocker within that scope. Both reviews preceded the local
source/input checkpoint and made no model/API requests.

- The old seed-only counterexample now preserves 59/59 catalog classes under
  the purchased measurements; the old maximin diagnostic preserved 9/59.
- All 48 parameter settings preserve 59 classes and pass numerical resolution.
  Of these, 31 are noise-resolved and 17 noise-limited. The latter are retained.
  Both adversarial starting banks also preserve all 59 classes.
- Archived-template injection is refused even without checking current source.
  Special-token prose and noninteger token ceilings have regression tests.
- The source/input snapshot preserves all six copied file hashes, 48 unmeasured
  cases, and private-file permissions. It cannot authorize a live run.
- The complete suite passed independently: **122 tests in 11.87 seconds**.

These reviews are by agents of the same system. They establish local software
behavior, not independent human approval, public preregistration, generation
quality, or an intervention-feedback advantage. The full live freeze is pending
model settings, prices, publication, review, and execution release; see
[FIRST_LOOP.md](FIRST_LOOP.md).

## Initial review record

A separate agent reviewed the runner, inference, privacy boundary, budgets, and
artifact replay, then reran the suite independently:

```text
PYTHONPATH=src .venv/bin/python -m pytest -q
85 passed in 5.75s
```

This is an engineering review by an agent of the same system, not independent
human pre-run approval. It does not replace the public freeze, external evidence
check, and human execution release required for a live experiment.

## Findings resolved before any live generator outcomes

| Finding | Implemented correction |
| --- | --- |
| A sealed rule bank was not initially checked against its raw generation. | Replay reparses raw responses and reconstructs each initial/final bank, including rule origin and lineage. |
| A prompt could have passed basic checks despite extra unpermitted data. | Replay reconstructs the exact public payload for each phase, including incomplete traces, and compares the complete prompt. |
| Graph-specific numerical allowances could encode information about hidden truth. | Selection and compatibility use one public-parameter allowance; actual graph qualification must fit inside it. |
| Partial cases initially omitted already-consumed measurements from totals. | Draws, forwards, attempted calls, and reservations are recorded when consumed and replayed from receipts. |
| Run artifacts did not initially contain the population and authorization records needed to check the freeze. | Live bundles archive the full prepared population/manifest and bound freeze, review, and release; replay checks the exact split and case order. |
| Local reuse of a release was not initially prevented. | Execution claims the freeze directory once, before a provider call. The documented limitation is that copying/deleting local directories can bypass this guard. |
| Distinct templates sampled without replacement did not automatically justify binomial case intervals. | Evaluation draws independent cases with replacement from the held-out catalog; realized class diversity and the conditional sampling scope are reported. |

The verifier also checks phase order and semantic receipt parents, mandatory
decisions and diagnostics, model/settings, API usage and reservations, per-case
costs, failed prefixes, and summary recomputation. The default unconfigured model
and absent review/release refuse live execution before loading a provider.

## Additional independently authored checks

Temporary fake-provider fixtures, deleted after the checks, established:

- Two complete cases: six calls, 384 measurement draws, 48 measurement graph
  forwards, and successful deterministic replay.
- A failure on the second call: incomplete with zero completed cases, but two
  attempted calls and 64 already-consumed draws remained accounted for.
- Editing raw generation and consistently recomputing receipt/manifest hashes
  still failed the rule-bank replay check.
- Adding an unobserved-outcome field to regeneration and updating the prompt and
  hashes still failed the complete evidence-boundary check.

All provider tests used mocks. No external model call or paid request was made
as part of this review. These checks establish software behavior, not generation
quality or a feedback advantage.

## Remaining limits

Artifact hashes and local receipts do not prove public timing, reviewer identity,
or authentic remote-provider behavior. External evidence must be inspected.
Dollar caps use frozen price assumptions rather than guaranteeing an invoice.
Qualification counters cover completed receipted invocations; partial work inside
a qualification that raises is not fully counted and blocks a complete run.

The benchmark contains authored two-coordinate graphs, a bounded grammar, and a
fixed menu. Its outside-grammar gain family is already exposed by anchor
observations. Equivalent menu signatures identify a class, not a unique graph.
The pilot does not validate broad mechanism discovery or model self-inspection.
