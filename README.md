# Causal Rival Loop

**Does intervention feedback help an LLM propose better causal explanations?**

This repository implements a bounded comparison: the same initial explanation
bank is revised once with measured intervention outcomes, and once without those
additional outcomes. Both paths have the same generation budget. Fresh
measurements then test their sealed predictions.

The explanations are small executable rules, rather than freely invented
prediction tables. Known neural computations provide a reference answer.

**Status: corrected implementation; source/input freeze.** No live generator experiment
has been released. Mock-provider outputs test the software; they are not research
results. A live evaluation requires a public freeze, independent review, and an
explicit execution release.

## The experiment in one picture

```text
Public setting + common anchor observations
                 |
        Shared initial generation
                 |
        Structural preflight
                 |
    Four reads covering both contexts
                 |
         +-------+--------+
         |                |
     Feedback         Regeneration
  gets outcomes     gets no extra outcomes
         |                |
    One revision     One revision
         |                |
         +-------+--------+
                 |
    Seal rules and complete predictions
                 |
     Fresh full-menu measurements
                 |
 Compatible sets + private truth scoring
```

For example, `select(context, a, avg(a,b))` is an executable explanation:
read coordinate `a` in one context and average the two coordinates in the other.
The interpreter applies the actual coordinate-replacement intervention before
calculating a prediction. The generator does not choose a hook, invent an
intervention, or inspect private reference labels.

## What success would establish

The primary comparison is whether the final **generated** bank contains the
correct full-menu explanation class on 24 in-grammar evaluation cases. Separate
fresh measurements test whether a bank supports a correct conclusion.

A positive result would support feedback-assisted hypothesis generation in this
declared testbed. It would not show general mechanism discovery, superiority over
human researchers, or that a model can introspect its own computation.

Different programs with identical predictions under the entire permitted menu
belong to one explanation class. An unresolved case is kept; a single surviving
candidate is not automatically proof that the true mechanism was proposed.

## Read or reuse

- [PROTOCOL.md](PROTOCOL.md): cases, comparison, scoring, uncertainty, stops, and
  release requirements.
- [configs/pilot.json](configs/pilot.json): declared budgets and currently
  unconfigured live-model settings.
- [schema.json](schema.json): strict generated-rule response format. Runtime
  validation also enforces depth, node count, IDs, and duplicate-key rejection.
- [prompts/initial.md](prompts/initial.md),
  [prompts/feedback.md](prompts/feedback.md), and
  [prompts/regeneration.md](prompts/regeneration.md): the three generation steps.
- [docs/AUDIT.md](docs/AUDIT.md): independent engineering review, verified
  software behavior, and remaining limits; this is not a live-run release.

The package vendors a small, pinned part of the existing causal-decidability
implementation. The original frozen experiments are not changed. This experiment
adds a generator and a bounded feedback step; it does not present causal
experiment design or compatible-set inference as new ideas.

## Run the software checks

Python 3.11 or newer is required. Install the package and its test dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest
```

For the versions used in the local review (Python 3.12), install
`requirements-lock.txt` before installing the editable package. Work from this
source checkout: prompts, configuration, and source bindings are part of the
experiment, rather than data downloaded by an installed wheel.

Prepare the manifests, qualify the development computations, and exercise the
loop with a fake provider:

```bash
.venv/bin/rival-loop prepare --out artifacts/prepared --config configs/pilot.json
.venv/bin/rival-loop qualify --prepared artifacts/prepared --out artifacts/qualification.json
.venv/bin/rival-loop smoke --out artifacts/smoke --cases 4
.venv/bin/rival-loop verify --run artifacts/smoke
.venv/bin/rival-loop freeze-source --prepared artifacts/prepared \
  --qualification artifacts/qualification.json --out freezes/source-input-v1
```

The source-freeze command requires a committed, clean checkout and grants no
live execution release. [Start the first loop](docs/FIRST_LOOP.md) lists the
remaining model, budget, publication, and review requirements.

The smoke command uses separate fixture seeds and a fake provider. It does not
open evaluation outcomes or contact an API. Its scores are not evidence for the
scientific question. `qualify` checks development computations and outcome-free
prediction coverage; it does not measure evaluation outcomes.

Live commands are described in [docs/LIVE_RUN.md](docs/LIVE_RUN.md). They refuse
to run with the default unconfigured generation settings or without separate
review and authorization records bound to the frozen artifact. Do not treat a
successful local freeze as a public timestamp.

## Size and limits

There are 12 development cases and 36 evaluation cases: 12 represented
compositions, 12 cases with a graph-equivalent alias, and 12 outside-grammar stress
cases. One pair of equivalent graphs is one case. The primary denominator is the
24 in-grammar evaluation cases; outside-grammar outcomes are reported separately.
Evaluation cases are independent draws with replacement from classes held out
from development; case independence does not imply 24 distinct mechanism
families. Realized class diversity is reported.

The ceiling is 144 generation attempts and 9,216 physical measurement draws.
The observation noise is disclosed artificial Gaussian noise, not native LLM
rounding or unexplained model variability. The 24-case primary comparison is a
pilot and has limited power for modest improvements.

The planted computations are authored two-coordinate Torch graphs, not internal
mechanisms recovered from a trained LLM. The generator is an external LLM.
Transfer to trained models, unrestricted mechanism families, or self-examination
requires another experiment.

Invalid generations, technical failures, and insufficient evidence remain in
the record. Neither cases nor calls are replaced to improve an outcome. No live
provider is configured by default.
