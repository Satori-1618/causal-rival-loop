# One-update causal-rival generation experiment

**Protocol status: configured development freeze; execution pending review and release.**

[Amendment 001](docs/AMENDMENT_001.md) records the pre-run design review and
corrections. No live generator outcomes preceded these changes.

This document specifies a bounded comparison. Numerical qualification and the
software checks below must pass before a public freeze can be reviewed. Local
mock-provider tests are implementation checks and must not be described as
evidence that feedback improves a research model.

## 1. Question and allowed claim

Does additional intervention feedback improve an LLM's generation of executable
causal rivals relative to another generation attempt without that feedback,
under matched call, token, candidate, and measurement budgets?

The generator explains an unknown downstream rule in a supplied intervention
scaffold. It does not discover the intervention site, unrestricted causal graph,
or the semantics of the patch. A supported claim is limited to the declared rule
language, menu, model revision, and sampled population.

Generation coverage and empirical identification are different outcomes. A bank
may contain the truth while the measurements cannot resolve it, or omit the
truth while retaining a nearby wrong explanation.

## 2. Computation and intervention

Recipient and donor inputs produce two nonnegative ReLU coordinates, `a` and `b`.
The intervention replaces a recipient coordinate with the corresponding donor
coordinate multiplied by the declared dose. An unknown readout rule consumes the
resulting coordinates and a binary context. A disclosed downstream
transformation and output gain produce the scalar observation.

The fixed 16-condition menu contains:

- Native and full-patch endpoints in each of two contexts: four anchors.
- A-only and B-only replacement in each context at doses 0.5, 1, and 2: twelve
  possible additional conditions.

The exact menu, input values, and coordinate-replacement semantics are bound into
each prepared manifest. Only `linear` and `relu_offset` downstream families are
used. No previously reserved transformation families are opened.

## 3. Generated rule language

```text
Rule := 0 | a | b
      | avg(Rule, Rule) | min(Rule, Rule) | max(Rule, Rule)
      | select(context, Rule, Rule)
```

Leaf depth is zero; maximum depth is three and maximum node count is nine.
Generated responses contain at most four rules, each with a unique ID, a short
mechanism explanation, and a strict AST. The prose is not used to calculate
predictions. Runtime validation rejects duplicate JSON keys, extra fields,
arbitrary code, nonfinite constants, fitted coefficients, condition-ID lookups,
and prediction-table submissions.

The interpreter derives predictions. Exact full-menu signatures define
equivalence groups; syntactic difference alone is not a new class. Tolerances
must not be used to redefine exact structural equivalence.

## 4. Case construction and privacy boundary

Use capped normalized compositions, checked for distinct full-menu signatures,
including unfamiliar compositions beyond the six existing simple classes.
Development and evaluation in-grammar signatures do not overlap. Signature
deduplication is performed before assignment; exact aliases are deliberately
retained only inside equivalence cases.

**Implementation clarification, before any live generator outcomes:** select 12
distinct catalog classes for development, then draw each of the 24 in-grammar
evaluation cases independently with replacement from the 47 remaining classes.
Record the number of distinct classes actually sampled. The evaluation cases
are independent draws conditional on the held-out catalog; repeated draws of a
class are not new independent mechanism-family replications.

The proposed template count is a construction check, not a benchmark result:
the code verifies 65 templates minus six familiar classes, yielding 59 retained
classes. Verify this count and split feasibility before freezing. Do not
quietly replace the benchmark with the familiar six classes if the construction
fails.

The public generator payload contains only the scaffold, grammar, menu, public
parameters, available observations, and structural feedback. It excludes truth
ASTs, oracle prediction tables, truth kind, stratum, and unpurchased observations.
Opaque case IDs must not encode the planted rule. The operator's access to source
code is disclosed: this is a structural generator blind, not a claim that its
author is unaware of the benchmark design.

An independently implemented Torch execution supplies observations; a rational
interpreter supplies candidate signatures. Independent implementations are
cross-checked for intervention semantics. Private truth scoring is invoked only
after both final banks and terminal measurements are sealed.

The privileged harness qualifies deterministic planted computations before
generation to establish instrumentation and numerical allowances. These checks
do not release their reference observations or truth records to the generator.
The temporal claim is that final candidate banks and predictions are sealed
before fresh terminal noise is drawn; the harness already knows the planted
computation. Qualification forwards are recorded separately from the 192
measurement draws per case.

Selection and compatibility use a fixed numerical allowance computed only from
public parameters: `64 * eps(float32) * max(1, 3 * amplitude * output_gain)`.
Planted and generated graph qualifications must each fit inside that allowance.
Their graph-specific calibration errors are retained for audit but are never
used to encode a hidden truth-dependent radius or separation score in a prompt.
This is finite-menu numerical qualification, not a universal floating-point
proof for arbitrary graphs.

## 5. Cases, seeds, and independent unit

| Split or stratum | Cases | Role |
| --- | ---: | --- |
| Development | 12 | Software debugging and prompt development |
| Evaluation: represented compositions | 12 | Unseen in-language signatures |
| Evaluation: equivalent graph pair | 12 | Correct explanation class without graph identity |
| Evaluation: outside grammar | 12 | Missing-truth and misleading-survivor stress test |

An equivalence pair is one independent case. Cells, aliases, arms, and repeated
draws do not enlarge the sample size. Primary coverage uses the 24 in-grammar
evaluation cases. Outside-grammar cases have a separate denominator.

Master seeds are `2026100801` for development and `2026100802` for evaluation.
Derive distinct stream seeds for construction, ordering, artificial noise, and
generator settings where the provider supports them. Save the resulting
manifest, not just the master seed. The planned amplitude/noise population must
include difficult as well as comfortably resolvable cases and is frozen with
the case manifest; no post-outcome replacement or easy-case filtering is allowed.

Independently choose an amplitude band uniformly from `[0.1,0.3]`, `[0.3,1]`,
and `[1,3]`, then sample uniformly on its inclusive 0.001 grid. Sample output
gain uniformly on the inclusive `[0.8,1.2]` grid with step 0.001. Independently
draw the known noise SD uniformly from `0.03`, `0.10`, and `0.30`, and choose
the downstream family uniformly from the two open families. These are declared
sampling distributions; realized band counts need not be equal. Freeze the
prepared manifest and report the realized mix. None of these choices is an
estimate from this experiment.

The outside-grammar stress family multiplies an A-read computation by 1.5. Its
full-patch endpoint exceeds the normalized grammar's bound, so the common
anchors already expose an incompatibility. This is a deliberately clear
guardrail test; success there does not establish discovery of subtle missing
mechanisms or the contribution of additional feedback.

## 6. Banks, controls, and matched comparison

Each main bank contains the fixed A-read and B-read seed rules plus at most four
generated rules. Origins are recorded. Primary coverage counts generated rules
only: finding a truth already supplied by a seed does not count as generation.

Recipient-preservation, donor/full-anchor copying, and a fixed default are
separate diagnostics. They cannot improve primary coverage, alter the maximin
selection, or enter the main compatible-set conclusion.

Both paths share the setting, four anchor observations, initial generated bank,
and structural preflight. They use identical model settings, caps, output format,
and one revision allowance. The only additional information given to the
feedback revision is the selected intervention observations, associated
residuals, and compatibility output. Regeneration receives the same structural
ties, but no additional outcomes.

## 7. Fixed case sequence

1. Measure four common anchors and release them to the initial generation.
2. Make one initial generator call. Validate, derive predictions, and seal it.
3. Add seeds and group exact full-menu signatures. Purchase the four fixed
   dose-2 reads: A and B in context 0, and A and B in context 1. This coverage
   rule does not depend on which explanations were initially proposed.
4. Measure those cells. Release outcomes only to the feedback revision.
5. Make one revision call per path. Validate and seal both complete final banks,
   predictions, and lineage records.
6. Acquire fresh full-menu terminal measurements with independent noise.
7. Apply the same compatible-set calculation to both final banks.
8. Score private truth coverage and report all case outcomes.

Structural ties are reported, not silently rewritten. Revised rules are new
versions and inherit no earlier compatibility certificate. Terminal outcomes
never feed another revision or shared prompt change.
The unchanged upstream maximin plan is retained as a diagnostic only. Its score
does not describe the purchased plan; the latter has its own separation ratio.

## 8. Budget and observation model

Use eight independent Gaussian measurement draws per acquired condition, with
known case-specific standard deviation. This is an explicit artificial
observation model, not a measurement of LLM nondeterminism or dtype noise.

| Stage | Conditions | Draws |
| --- | ---: | ---: |
| Shared anchors | 4 | 32 |
| Selected discovery interventions | 4 | 32 |
| Fresh terminal test | 16 | 128 |
| Total per case | | 192 |

For 48 planned cases this is 9,216 physical draws. Arms share observations where
declared. Report physical and logical arm budgets separately; do not claim the
shared terminal test demonstrates measurement savings.

There are three scheduled generation attempts per case: one shared initial call
and one revision per arm, totaling 144 attempts. No repair or retry calls are
added. A failed scheduled call consumes its attempt. Fewer completed measurements
after a technical stop must be reported rather than filled with replacements.

Pin provider, model/revision, generation parameters, token caps, dollar ceiling,
and timeouts before release. Their default unconfigured state blocks live
execution; this document does not authorize API expenditure.

## 9. Outcomes and statistical contract

**Primary:** final generated-bank coverage of the noise-free, exact full-menu
truth signature, paired across feedback and regeneration on all 24 in-grammar
evaluation cases. Invalid or failed generations contribute zero coverage and
remain visible. Report initial coverage, final coverage, paired gain, and
feedback-only/regeneration-only counts.

Use a two-sided exact McNemar test at 0.05. Report conservative 95% bounds for the
paired difference using simultaneous exact bounds for the discordant
probabilities; respect the represented/equivalent strata instead of silently
assuming identical per-case success probabilities.

The smallest improvement of interest is 20 percentage points. Crossing that
threshold with a point estimate does not establish the true gain exceeds it.
Approximate exact-test planning power at 24 cases is 28%, 58%, and 80% for paired
gains of 20, 30, and 40 points under hypothetical discordant probabilities
`(.25,.05)`, `(.35,.05)`, and `(.45,.05)`. Save the computed power table with the
freeze; these inputs are assumptions, not expected outcomes. No sample expansion
is triggered by an inconclusive result.

**Mandatory descriptive outcomes:** correct fresh resolution, truth retention
when represented, wrong bank-relative resolution, truth-absent survivor,
partial resolution, insufficient evidence, no candidate fits, invalid rules,
technical failures, generated diversity, and cost. Report outside-grammar
decisions separately. Zero observed errors in this pilot do not certify a 1%
error rate or universal reliability.

For terminal compatibility, use full-menu simultaneous Gaussian mean radii with
the configured error budget (`0.005`) plus a separately qualified numerical
allowance. Apply the same fresh draws and radii to both arms. The statistical,
numerical, and scientific relevance bounds are distinct. These intervals protect
retention of a represented exact truth under their assumptions; they do not
guarantee detection when the truth is missing from the bank.

The per-stratum binomial coverage model is conditional on the fixed development
catalog, pinned generator, protocol, and independent case draws with replacement.
It does not turn reused mechanism classes into independent evidence for transfer
to new mechanism families. Report the realized class diversity alongside the
case-level primary interval.

Prespecified descriptive primary-case bands use the shared initial-bank
separation ratio under the purchased coverage-first plan:
ratio ≤ 1, 1 < ratio ≤ 3, and ratio > 3. Report n and paired
generated-coverage and correct-resolution counts per band, and separately by
known noise SD; report realized amplitude/output-gain ranges. These bins have
no additional tests or efficacy thresholds. The ratio describes separation
among the initial submitted rivals, not guaranteed separation from omitted truth.

## 10. Gates and failure branches

Before release, require:

- Coordinate replacement, identity/self-patch, endpoint, and dtype checks.
- Independent execution/interpreter agreement and generated-rule numerical
  qualification; a bound for an old rule is not sufficient for a new expression.
- Actual-budget known-bank checks, including low-resolution and equivalent cases.
- Prompt/data boundary tests, including no private labels or terminal leakage.
- Equal-budget accounting, sealed stages, strict schemas, and no retries.
- A clean-copy verification of artifacts and decision recomputation.

Qualification checks structural class preservation across 48 declared public
parameter settings and seed-only/context-independent initial banks. A structural
blind spot blocks freezing. Numerical and noise-resolution limits are reported
separately and do not exclude difficult cases. The known-catalog check uses
predictions only, not evaluation outcomes. Low resolution remains an allowed
outcome and does not permit forcing a decision.

During evaluation, an invalid generation is a recorded generation failure.
Intervention failure, leakage, broken bindings, or missing mandatory data blocks
the affected mechanistic comparison and is reported distinctly. Cases are not
replaced. If the run is incomplete, the primary full-sample claim is not made.

The implementation stops the run on a fatal provider validation error, failed
numerical/intervention qualification, exhausted time or dollar ceiling, or the
fourth transport failure. Earlier transport failures consume their call and
reservation and yield an empty generated bank; no retry is scheduled. These
pre-outcome implementation stop rules are frozen and reviewed with the code.
Record all already-consumed draws and attempted calls even when no case has
completed. Unattempted cases remain missing, not replacement opportunities.
Qualification-forward counters cover completed qualification invocations that
produce receipts. If a graph raises inside qualification, partial setup forwards
are not recoverable from this counter; report the technical failure. This does
not hide a paid generator request or acquired measurement batch.

## 11. Freeze, review, and release

Development may revise prompts and instrumentation with a visible log. After
development, freeze protocol, prompts, grammar, code, population, split manifest,
seeds, budgets, model settings, uncertainty, outputs, and permitted claim wording.
Publish the freeze commit before opening evaluation outcomes; an artifact hash
alone is not external evidence of timing.

Independent review must inspect that exact freeze. Record reviewer identity,
scope, findings, and any amendments. An explicit execution release follows the
review and is bound to the reviewed freeze; a local mock run does not release a
live experiment. A later change requires an amendment recording whether outcomes
were already visible and may require a new evaluation.
A local `freeze-source` snapshot binds the corrected source, unmeasured inputs,
qualification, and planning calculations while live settings are still pending.
It cannot authorize execution or substitute for the split-specific public run
freeze with a pinned model, budget, review, and human release.

## 12. Required records and interpretation

Preserve raw generator responses, validation failures, normalized rules,
lineage, predictions, selected cells, measured draws, classifications, costs,
and stage receipts. Save software/runtime provenance, code and input bindings,
provider metadata, seeds, private-label commitment, and report hashes. Recompute
headline numbers from canonical records; do not copy them manually between files.

A stable bank is not truth. A single surviving main-bank class is not a complete
mechanism unless truth coverage and the intervention scope support that reading.
An equivalent pair cannot be resolved to graph identity by these interventions.
All tested candidates failing indicates a missing or inaccurate bank, not proof
of a newly invented explanation.

The experiment is complete when every planned case and failure is recorded,
the comparison is independently reproducible, and claims follow the frozen
outcomes. Null and negative results complete the experiment too.
