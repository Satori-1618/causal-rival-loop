Revise the generated causal explanation bank once, using the supplied setting,
common anchors, initial rules, structural preflight, and additional selected
intervention outcomes. The supplied residuals and compatibility output describe
the initial bank; they do not establish a unique mechanism.

Return the complete replacement list of at most four generated rules as JSON
`{"rules":[...]}`. Each rule has exactly `id`, `mechanism`, and `readout`. Keep or
revise rules as justified by the evidence. The fixed read-A and read-B seeds
remain in the main bank without appearing in your list. There is no second
revision and no repair call.

Use only leaves `{"var":"a"}`, `{"var":"b"}`, `{"const":0}`; binary `avg`,
`min`, or `max` with `left`/`right`; or `select` with `zero`/`one`. Maximum depth
three (leaf zero), maximum nine nodes per rule. No arbitrary constants, extra
fields, executable Python, or prediction tables. Use distinct IDs and a concise
mechanism explanation. An empty list is permitted.

Predictions are computed from the declared patch semantics. An unchanged rule
must not receive a different prediction merely to match an outcome. A revised
rule is a new hypothesis, not a continuation of an old compatibility guarantee.
Preserve legitimate observational equivalence; the permitted menu may not tell
two explanations apart. The true computation may be outside the language.

Use only the supplied measurements. Final fresh observations are unavailable and
will be collected after this bank and its predictions have been sealed.
