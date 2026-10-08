# Starting the first live loop

The local source/input snapshot is a historical checkpoint, not an execution
release. [DEVELOPMENT_FREEZE.md](DEVELOPMENT_FREEZE.md) supplies the configured
live settings and publication procedure for the next freeze.

The first live round is **12 development cases: 36 generator attempts and
2,304 artificial measurement draws**. It tests prompts and the pipeline.
The later 36-case evaluation requires its own freeze and review.

## What remains

1. **Review the configured generator and limits.** `configs/development.json`
   supplies the model, reasoning, token ceilings, timeouts, prices and USD 20
   accounting ceiling. Its maximum development reservation is USD 4.42368.
   The generic `configs/pilot.json` remains unconfigured.
2. **Create the complete development freeze.** Commit the configured source,
   prepare inputs, qualify, and use `freeze --split development`. Configuration
   changes produce a new source binding; do not edit the source/input checkpoint.
3. **Publish and review that exact freeze.** Publish the source commit and
   complete matching input/qualification bundle, then obtain a review
   recording its hash, reviewer, public URL, and publication time. Locally filled
   URL fields do not authenticate public timing.
4. **Record the human run instruction.** Bind a release record to that freeze
   and review. The implementation and agent reviews do not provide this release.
5. **Provide `OPENAI_API_KEY` in the environment.** The live tokenizer dependency
   is already installed locally. Do not put the credential in a config or trace.

For frozen token ceilings `I` and `O`, and prices `p_in` and `p_out` per million
tokens, the development reservation is:

```text
36 * (I * p_in + O * p_out) / 1,000,000 USD
```

This is conservative accounting using the chosen price assumptions, not a
prediction of actual token use or an invoice guarantee. The combined pilot has
144 scheduled attempts; the evaluation freeze adds development reservations to
its budget check.

## Commands to prepare, review, and release the development round

```bash
.venv/bin/rival-loop prepare --config configs/development.json --out artifacts/dev-inputs
.venv/bin/rival-loop qualify --prepared artifacts/dev-inputs --out artifacts/dev-qualification.json
.venv/bin/rival-loop freeze --prepared artifacts/dev-inputs \
  --qualification artifacts/dev-qualification.json \
  --split development --out freezes/development

# Publish and review the freeze before the next command.
.venv/bin/rival-loop run --prepared artifacts/dev-inputs --freeze freezes/development \
  --review releases/review-development.json --release releases/release-development.json \
  --split development --out artifacts/run-development --execute
.venv/bin/rival-loop verify --run artifacts/run-development
```

[LIVE_RUN.md](LIVE_RUN.md) provides the review/release schemas. No model calls
are required to prepare or qualify the inputs. A failed development round is
recorded and cannot be silently rerun under the same release.
