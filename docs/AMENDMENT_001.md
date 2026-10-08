# Amendment 001 — before the first live loop

**Date:** 8 October 2026. **Parent:** `545cacd`.
No live generator outcomes or paid model requests preceded this amendment.
Prior smoke traces used authored fake responses and remain software checks.

The two-agent design review found three defects:

1. A seed-only bank could buy four reads in context 0 and leave context 1
   unobserved, despite a large submitted-bank separation score.
2. Replay checked prompts against archived template text without binding that
   text to the frozen source hash. Consistently resealed template injection
   could therefore pass verification.
3. Token counting rejected literal special-token text in valid generated prose.

The corrected design buys exactly one dose-2 read of each coordinate in each
context. This uses the same four extra conditions, eight draws each. It is
independent of the submitted bank and observed outcomes. The upstream maximin
selector remains byte-identical and diagnostic; its result no longer chooses
the purchased conditions. A separate score describes the purchased plan.

Outcome-free qualification checks all 59 catalog classes across 48 public
amplitude/gain/noise/family settings, plus seed-only and context-independent
initial banks. Losing a structural class blocks freezing. Poor numerical or
statistical resolution is reported separately and does not remove cases.

Every archived phase template must match its recorded frozen UTF-8 source hash,
including historical development replay without current-source checking.
Regression tests consistently reseal injected templates and require refusal.
Arbitrary prompt text is tokenized as ordinary text. Token ceilings must be
actual integers. These changes add no provider retry or repair calls.

Case counts, seeds, grammar, noise distribution, primary estimand, statistical
rules, and generation/measurement budgets are unchanged. No mixed-coordinate
interventions or broader mechanism-identification claim were added. The
graph-equivalent alias remains an engineering check rather than a separate
generation challenge.

The new source/input freeze grants no execution release. Model settings and
prices remain pending; the full split-specific freeze and public review follow
once these are specified.
