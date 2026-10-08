You are proposing executable causal explanations for an unknown readout in a
small neural computation. The setting below supplies the intervention semantics,
the public downstream transformation, the permitted menu, and four common anchor
observations. Explain the unknown rule; do not reinterpret the patch.

Return only one JSON object with exactly the field `rules`, a list of at most four
rules. Each rule has exactly `id`, `mechanism`, and `readout`. `mechanism` is a short
explanation; only the AST in `readout` produces predictions. Use distinct IDs.

Readout language:
- `{"var":"a"}` or `{"var":"b"}` reads a post-intervention coordinate.
- `{"const":0}` returns zero.
- `{"op":"avg","left":AST,"right":AST}` averages its branches.
- The same binary form permits `min` and `max`.
- `{"op":"select","zero":AST,"one":AST}` chooses a branch from the supplied
  context, zero or one.

Maximum depth is three with leaves at depth zero. Maximum total node count is
nine per rule. No other keys, constants, operators, condition-ID lookups, or code
are allowed. Do not submit prediction tables. The harness calculates predictions
from the rules and the specified interventions.

The main bank already includes the fixed read-A and read-B seed rivals. Prefer
useful additional hypotheses over repeating those seeds. Distinct-looking rules
may still be equivalent over the menu; do not invent a distinction if it is not
observable. You may return fewer than four rules, including an empty list.

Do not assume the rule is representable in this language. Valid syntax is not
evidence that a hypothesis is true. Account for the disclosed artificial
measurement uncertainty. The supplied payload is the complete evidence available
for this step; private truth labels and unobserved outcomes are unavailable.
