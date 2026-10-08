# Development freeze — 8 October 2026

This prepares the first live generator round. It does not authorize execution.
The earlier local source/input checkpoint remains historical. No live generator
outcomes preceded this configuration. Development-v1 was withheld by review for
binding ignored installation metadata; [Amendment 002](AMENDMENT_002.md) requires
a corrected, publicly verified development-v2 bundle before release.

## Fixed question and scope

Use the existing one-update comparison: a shared initial bank, one revision with
intervention feedback, and one revision without those additional outcomes.
Both revisions have the same generation settings and limits. Development has
12 cases, at most 36 generator attempts, and 2,304 artificial measurement draws.
Its results are descriptive. The 36-case evaluation requires a separate freeze
and review after development; its primary denominator remains 24 in-grammar cases.
No cases, seeds, grammar, intervention cells, thresholds, or statistical rules
were changed to prepare this run.

## Generator settings

The configured file is [configs/development.json](../configs/development.json).
The unconfigured `configs/pilot.json` remains the reusable template.

| Setting | Value |
| --- | --- |
| API/model identifier | `openai_responses` / `gpt-6-sol` |
| Response model required | exactly `gpt-6-sol` |
| Reasoning | `medium`; temperature omitted |
| Input/output token ceilings | 16,384 / 8,192 per call |
| Local token counter | `o200k_base`, plus the existing framing allowance |
| Per-request / per-split deadline | 120 seconds / 7,200 seconds |
| Retries | zero |
| Combined accounting ceiling | USD 20 |
| Frozen input/output rates | USD 2.50 / 10.00 per million tokens |

Official [model documentation](https://developers.openai.com/api/docs/models/gpt-6-sol)
lists `gpt-6-sol` as its snapshot identifier and supports medium reasoning and
Responses. It supplies no dated snapshot identifier. The exact returned model
ID is checked, but that does not attest to immutable provider weights.

Official [pricing](https://developers.openai.com/api/docs/pricing) was checked on
8 October 2026: short-context Standard input is USD 2.00 and output USD 10.00
per million tokens; cache writes cost 1.25 times the uncached input rate. The
frozen input rate uses USD 2.50 conservatively; cached-input discounts are not
credited. These are accounting assumptions, not an invoice guarantee for every
account configuration. Token caps stay far below the long-context price threshold.
The output cap includes non-visible tokens as described in the official
[token-counting guide](https://developers.openai.com/api/docs/guides/token-counting#understand-output-token-counts).
Its sufficiency is untested before development. An incomplete or invalid
generation remains a failure; there are no paid calibration or repair calls.

| Reservation | Maximum at the frozen token caps and rates |
| --- | ---: |
| One call | USD 0.12288 |
| Development, 36 calls | USD 4.42368 |
| Evaluation, 108 calls | USD 13.27104 |
| Combined pilot, 144 calls | USD 17.69472 |

An evaluation freeze must include development reservations in the USD 20 check.
There is no paid smoke call. The API credential is supplied through the
environment at execution and is never part of this bundle.

## Publication and review

Commit the configured source before preparation. Then prepare, qualify and
freeze using `configs/development.json`. Publish a complete immutable bundle:
`freeze.json`, all five prepared files, and `qualification.json`. The manifest
binds the config/public/private/population files; the freeze binds the manifest,
qualification, and source. The public prepared population contains authored
reference labels, but no evaluation observations. The generator has no tools
and receives only the allowed payload; operator blindness is not claimed.

The artifact publication commit follows the frozen source commit. Review must
record both IDs and verify public file bytes, rather than equating those commits.
Because `artifacts/` and `freezes/` are ignored, explicitly publish only the
selected bundle files. Keep runtime claim files, credentials, and API traces out
of that pre-run commit.

Place local review and human-release records in ignored `releases/`. Writing
untracked records elsewhere makes the checkout dirty and blocks the live run.
Publish review evidence separately without editing bound source. A passing agent
review establishes that agent's review scope; it is not human run authorization.

Before execution: verify the exact public bundle, complete review, record a
verbatim human release bound to its hashes, and supply the API credential.
Keep the original freeze directory for the create-only execution claim.
