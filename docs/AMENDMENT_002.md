# Amendment 002 — clean-export source bindings

**Date:** 8 October 2026. **Parent artifact publication:** `5594787`.
No live generator requests or evaluation measurements preceded this amendment.
Development-v1 is withheld and superseded, never retrospectively released.

Independent review downloaded the public development bundle and found that its
source binding includes six generated `src/causal_rival_loop.egg-info` files.
Git ignores those installation files. Their absence in a clean export causes
`prepared_data()` to refuse otherwise matching public source and inputs.
Local tests and local qualification did not establish portability of that freeze.

The correction excludes generated packaging metadata from the bound source
surface. Tests require installation metadata to have no effect on source hashes,
while changes to real source, prompts, configuration, and documentation remain
detectable. Dependency versions remain pinned in `requirements-lock.txt` and
recorded in the runtime provenance.

The new development-v2 bundle must be freshly prepared, qualified, frozen, and
publicly verified in a clean export. The original v1 files and tag stay intact.
Review findings are published under `reviews/development-v1/`.

Model settings, token/call/dollar budgets, deadlines, seeds, sampled population,
rule grammar, measurements, estimands, thresholds, and power assumptions are
unchanged. The new input manifest binds the corrected source; unchanged
population-file hashes must be checked against v1 before release.
