"""Adapters to the frozen inference code and prespecified pilot accounting.

Measurement radii assume independent, known-variance Gaussian draws, as supplied
by this synthetic benchmark. They are not a default uncertainty model for LLM
patching. Full-menu equivalence classes are established *before* restriction to
purchased cells. Fresh terminal data must never return to the generator.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import beta, binom, binomtest

from .vendor import compatible_set, selection

MEASUREMENT_ALPHA = 0.005
SAMPLES_PER_CELL = 8
ANCHORS = 4
EXTRAS = 4
MENU_WIDTH = 16
PLANNED_STRATA = {"represented": 12, "equivalent": 12, "outside": 12}
PRIMARY_STRATA = ("represented", "equivalent")
MEANINGFUL_GAIN = 0.20
_UPSTREAM_FILES = {
    "src/rival_loop/vendor/design.py": ("src/causal_decidability/design.py", "3d55a1885e1457cad8251d8e9d69b5ff8967eb25319bb377cfe42ca1122c3e0a"),
    "src/rival_loop/vendor/compatible_set.py": ("src/causal_decidability/compatible_set.py", "a83a1c8ff140385b61ad52e36d4e13698efd647bd9c20e03ef10cbe4e4e8eb3f"),
    "src/rival_loop/vendor/selection.py": ("applications/design-comparison/selection.py", "9fed3ec9327e9086b841b8e3a6525c9ffa9ed88990ff4c765abcffcaa60d8f8b"),
    "src/rival_loop/vendor/LICENSE": ("LICENSE", "3e565f97ddb39ba9dd07a1e18ed1d21989bd32b0142f9606989ba735d74d7e63"),
}


def verify_upstream(repository_root: str | Path | None = None) -> dict[str, Any]:
    """Verify byte-identical vendored files against the pinned public manifest."""
    root = Path(repository_root) if repository_root else Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "docs" / "UPSTREAM.json").read_text())
    expected = set(_UPSTREAM_FILES)
    entries = manifest.get("files", [])
    if (manifest.get("repository") != "https://github.com/Satori-1618/causal-decidability-method-case.git"
            or manifest.get("commit") != "24f3e2639db276c72414385a398c5b9d135e4059"
            or manifest.get("license") != "MIT"
            or {e.get("target") for e in entries} != expected
            or len(entries) != len(expected)):
        raise ValueError("invalid upstream binding manifest")
    checked = {}
    for entry in entries:
        if (entry.get("source"), entry.get("sha256")) != _UPSTREAM_FILES[entry["target"]]:
            raise ValueError(f"invalid upstream source/hash binding: {entry['target']}")
        path = root / entry["target"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"vendored upstream hash mismatch: {entry['target']}")
        checked[entry["target"]] = digest
    return {"passed": True, "commit": manifest["commit"], "checked": checked}


def _sigmas(public: dict[str, Any]) -> list[float]:
    value = public["sigma"]
    if isinstance(value, bool):
        raise ValueError("sigma must be a known positive standard deviation")
    values = [float(value)] * MENU_WIDTH if np.isscalar(value) else [float(v) for v in value]
    if len(values) != MENU_WIDTH or any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("sigma must be positive and finite in all 16 cells")
    return values


def radii(public: dict[str, Any], numeric_bound: float, n: int = SAMPLES_PER_CELL) -> list[float]:
    """Full-menu simultaneous radii; reuse these radii when restricting cells.

    Bonferroni allocates alpha=.005 over all 16 two-sided cell intervals. Adding
    the qualified deterministic numerical allowance does not average it away.
    """
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer")
    return selection.radii(_sigmas(public), [n] * MENU_WIDTH,
                           MEASUREMENT_ALPHA, numeric_bound).tolist()


def select_cells(predictions: dict[str, list[float]], groups: list[list[str]],
                 public: dict[str, Any], numeric_bound: float) -> dict[str, Any]:
    """Use the unchanged upstream maximin selector, with actual 4+4/8 budget."""
    menu = public["menu"]
    if len(menu) != MENU_WIDTH:
        raise ValueError("the pilot requires the frozen 16-cell menu")
    # The upstream selector requires at least two full-menu classes. Do not turn
    # a single declared class into an identification claim.
    if len(groups) < 2:
        names = [name for group in groups for name in group]
        if not groups or set(names) != set(predictions) or len(names) != len(set(names)):
            raise ValueError("groups must partition the bank")
        return {"status": "no_discriminating_rivals", "cells": list(range(ANCHORS)),
                "extras": [], "plans": {}, "radius": radii(public, numeric_bound)}
    result = selection.select(predictions, groups, menu, _sigmas(public), numeric_bound,
                              mandatory_count=ANCHORS, extras=EXTRAS,
                              samples=SAMPLES_PER_CELL, alpha=MEASUREMENT_ALPHA,
                              seed=0)
    result.update(status="selected", cells=result["plans"]["maximin"]["cells"],
                  extras=result["plans"]["maximin"]["cells"][ANCHORS:])
    return result


def classify_bank(predictions: dict[str, list[float]], groups: list[list[str]],
                  estimates: list[float], radius: list[float] | float) -> dict[str, Any]:
    """Retain entire declared full-menu groups using unchanged upstream code."""
    flat = [name for group in groups for name in group]
    if set(flat) != set(predictions) or len(flat) != len(set(flat)) or any(not g for g in groups):
        raise ValueError("full-menu groups must partition the bank")
    return compatible_set.compatible_set(predictions, estimates, radius, groups)


def known_bank_preflight(predictions: dict[str, list[float]], groups: list[list[str]],
                         public: dict[str, Any], numeric_bound: float) -> dict[str, Any]:
    """Outcome-free resolution check for the actual four-extra-cell budget.

    A ratio above one means at least one selected cell has disjoint simultaneous
    prediction intervals for a given class pair. This is a design diagnostic,
    not observed success or a universal identification guarantee.
    """
    selected = select_cells(predictions, groups, public, numeric_bound)
    if selected["status"] != "selected":
        return {"status": selected["status"], "class_count": len(groups),
                "cells": selected["cells"], "all_pairs_above_one": False}
    gap = selection.pair_gaps(predictions, groups)
    radius = np.asarray(selected["radius"])
    ratios = (gap / (2 * radius[None, :]))[:, selected["cells"]].max(axis=1)
    return {"status": "qualified", "class_count": len(groups),
            "cells": selected["cells"], "all_pairs_above_one": bool(np.all(ratios > 1)),
            "minimum_ratio": float(ratios.min()), "pair_ratios": ratios.tolist(),
            "physical_draws": SAMPLES_PER_CELL * (ANCHORS + EXTRAS),
            "interpretation": "conditional design diagnostic, not outcome evidence"}


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Exact two-sided binomial bounds, including nondegenerate boundary cases."""
    if (isinstance(k, bool) or isinstance(n, bool) or not isinstance(k, int)
            or not isinstance(n, int) or n < 1 or not 0 <= k <= n
            or not 0 < confidence < 1):
        raise ValueError("invalid binomial count/confidence")
    tail = (1 - confidence) / 2
    lower = 0.0 if k == 0 else float(beta.ppf(tail, k, n - k + 1))
    upper = 1.0 if k == n else float(beta.ppf(1 - tail, k + 1, n - k))
    return lower, upper


def exact_mcnemar(feedback_only: int, regeneration_only: int) -> float:
    """Two-sided exact conditional test on the discordant pairs."""
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0
           for v in (feedback_only, regeneration_only)):
        raise ValueError("discordant counts must be nonnegative integers")
    n = feedback_only + regeneration_only
    return 1.0 if n == 0 else float(binomtest(feedback_only, n, 0.5).pvalue)


def _paired(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = {"both": 0, "feedback_only": 0, "regeneration_only": 0, "neither": 0}
    for row in rows:
        a = bool(row.get("arms", {}).get("feedback", {}).get(field, False))
        b = bool(row.get("arms", {}).get("regeneration", {}).get(field, False))
        counts["both" if a and b else "feedback_only" if a else "regeneration_only" if b else "neither"] += 1
    return counts


def stratified_difference_ci(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Conservative >=95% interval under declared stratified case sampling.

    Four two-sided 98.75% CP intervals (win/loss in each of two strata) have
    joint coverage >=95% by a union bound. Average the two difference intervals
    with their prespecified equal weights. No pooling of unequal strata and no
    bootstrap that collapses to [0,0] on observed ties.
    """
    intervals = {}
    for stratum in PRIMARY_STRATA:
        members = [r for r in rows if r["stratum"] == stratum]
        if len(members) != PLANNED_STRATA[stratum]:
            raise ValueError("stratified inference requires all 12 units per primary stratum")
        counts = _paired(members, "generated_coverage")
        win = clopper_pearson(counts["feedback_only"], len(members), 0.9875)
        loss = clopper_pearson(counts["regeneration_only"], len(members), 0.9875)
        intervals[stratum] = {"n": len(members), "counts": counts,
                              "win_interval": list(win), "loss_interval": list(loss),
                              "difference_interval": [win[0] - loss[1], win[1] - loss[0]]}
    overall = [sum(intervals[s]["difference_interval"][i] for s in PRIMARY_STRATA) / 2
               for i in (0, 1)]
    return {"confidence_at_least": 0.95, "bounds": overall, "strata": intervals,
            "assumptions": "independent sampled cases within each declared stratum; binary win/loss marginals follow their stratum binomial sampling model"}


def _arm_summary(rows: list[dict[str, Any]], arm: str, planned: int) -> dict[str, Any]:
    arms = [r.get("arms", {}).get(arm, {}) for r in rows]
    booleans = ("generated_coverage", "correct_resolution", "false_resolution",
                "truth_excluded_when_covered", "truth_absent_bank_relative_survivor", "no_fit")
    summary = {field: sum(bool(a.get(field, False)) for a in arms) for field in booleans}
    summary.update(planned_denominator=planned, recorded=len(rows),
                   missing=planned - len(rows),
                   generated_coverage_rate_on_planned=summary["generated_coverage"] / planned,
                   outcomes=dict(sorted(Counter(a.get("outcome", "missing_arm") for a in arms).items())),
                   call_status=dict(sorted(Counter(a.get("call_status", "missing") for a in arms).items())),
                   valid_generated_rules=sum(int(a.get("valid_generated_count", 0)) for a in arms))
    diversity = [a["generated_class_count"] for a in arms if "generated_class_count" in a]
    summary["generated_diversity"] = {"records_with_class_count": len(diversity),
                                      "total_distinct_classes_within_banks": sum(diversity),
                                      "mean_per_recorded_bank": sum(diversity) / len(diversity) if diversity else None,
                                      "scope": "aliases collapsed within each bank; classes are not pooled across settings"}
    return summary


def _truth_diversity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [r["truth_class_id"] for r in rows if "truth_class_id" in r]
    return {"recorded_class_ids": len(labels), "distinct_mechanism_classes": len(set(labels)),
            "scope": "normalized planted template classes, not amplitude-scaled output signatures"}


def _descriptive_resolution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fixed descriptive bins; no inferential tests or post-outcome thresholds."""
    ratio_groups = {"ratio_le_1": [], "ratio_gt_1_le_3": [], "ratio_gt_3": []}
    noise_groups: dict[float, list[dict[str, Any]]] = {}
    parameters: dict[str, list[float]] = {"amplitude": [], "output_gain": []}
    for row in rows:
        ratio = row.get("preflight_minimum_separation_ratio")
        if ratio is not None:
            if isinstance(ratio, bool) or not math.isfinite(float(ratio)) or float(ratio) < 0:
                raise ValueError("preflight separation ratio must be finite and nonnegative")
            ratio = float(ratio)
            key = "ratio_le_1" if ratio <= 1 else "ratio_gt_1_le_3" if ratio <= 3 else "ratio_gt_3"
            ratio_groups[key].append(row)
        setting = row.get("setting")
        if setting is not None:
            for name in ("sigma", "amplitude", "output_gain"):
                value = float(Fraction(str(setting[name])))
                if isinstance(setting[name], bool) or not math.isfinite(value) or value <= 0:
                    raise ValueError("reported public parameters must be finite and positive")
                if name == "sigma":
                    noise_groups.setdefault(value, []).append(row)
                else:
                    parameters[name].append(value)

    def describe(members):
        return {"n": len(members), "generated_coverage_paired_counts": _paired(members, "generated_coverage"),
                "correct_resolution_paired_counts": _paired(members, "correct_resolution")}

    return {"scope": "descriptive recorded-case counts only; no additional tests or generic efficacy claims",
            "ratio_definition": "shared initial submitted-bank maximin score; does not establish separation from an omitted truth",
            "ratio_bands": {key: describe(members) for key, members in ratio_groups.items()},
            "records_without_ratio": len(rows) - sum(len(members) for members in ratio_groups.values()),
            "by_known_noise_sd": {str(sigma): describe(members) for sigma, members in sorted(noise_groups.items())},
            "records_without_setting": sum("setting" not in row for row in rows),
            "realized_parameter_ranges": {name: {"n": len(values), "minimum": min(values) if values else None,
                                                  "maximum": max(values) if values else None}
                                          for name, values in parameters.items()}}


def analyze(records: list[dict[str, Any]], *, split: str | None = None) -> dict[str, Any]:
    """Account for the entire frozen 36-case evaluation, including failures.

    Partial results receive planned denominators and cannot claim a completed
    evaluation or provide the primary test. Coverage in this function must have
    been scored from *generated* rules against private exact truth signatures.
    """
    if split not in (None, "development", "evaluation"):
        raise ValueError("invalid analysis split")
    if any(r.get("split") not in ("development", "evaluation") for r in records):
        raise ValueError("records contain an unknown split")
    if split == "development" or (split is None and records and all(r["split"] == "development" for r in records)):
        if any(r["split"] != "development" for r in records):
            raise ValueError("evaluation records cannot enter a development-only analysis")
        if len(records) > 12 or len({r["independent_unit"] for r in records}) != len(records):
            raise ValueError("invalid development independent-unit count")
        return {"status": "development_complete_descriptive" if len(records) == 12 else "development_incomplete",
                "inference_status": "development_only_no_evaluation_inference",
                "planned_development_units": 12, "recorded_development_units": len(records),
                "initial_coverage": sum(bool(r.get("initial_coverage", False)) for r in records),
                "paired_counts": _paired(records, "generated_coverage"),
                "arms": {a: _arm_summary(records, a, 12) for a in ("feedback", "regeneration")},
                "truth_diversity": _truth_diversity(records),
                "descriptive_resolution": _descriptive_resolution(records),
                "mcnemar_pvalue": None, "difference_interval": None,
                "scope": "development diagnostics; no held-out comparison claim"}
    evaluation = [r for r in records if r.get("split") == "evaluation"]
    identifiers = [r["case_id"] for r in evaluation]
    units = [r["independent_unit"] for r in evaluation]
    if len(set(identifiers)) != len(identifiers) or len(set(units)) != len(units):
        raise ValueError("duplicate case or independent unit cannot increase n")
    unknown = {r["stratum"] for r in evaluation} - set(PLANNED_STRATA)
    if unknown:
        raise ValueError(f"unknown evaluation strata: {sorted(unknown)}")
    counts = Counter(r["stratum"] for r in evaluation)
    if any(counts[s] > n for s, n in PLANNED_STRATA.items()):
        raise ValueError("records exceed frozen stratum sample size")
    primary = [r for r in evaluation if r["stratum"] in PRIMARY_STRATA]
    outside = [r for r in evaluation if r["stratum"] == "outside"]
    complete = all(counts[s] == n for s, n in PLANNED_STRATA.items())
    paired = _paired(primary, "generated_coverage")
    initial = sum(bool(r.get("initial_coverage", False)) for r in primary)
    summary: dict[str, Any] = {
        "status": "completed" if complete else "incomplete",
        "scientific_scope": "generated interventional-equivalence-class coverage within the frozen grammar and full menu",
        "planned_evaluation_units": 36, "recorded_evaluation_units": len(evaluation),
        "planned_primary_units": 24, "recorded_primary_units": len(primary),
        "planned_outside_units": 12, "recorded_outside_units": len(outside),
        "stratum_counts": {s: counts[s] for s in PLANNED_STRATA},
        "realized_truth_diversity": {"primary": _truth_diversity(primary),
                                     "outside": _truth_diversity(outside)},
        "descriptive_primary_resolution": _descriptive_resolution(primary),
        "primary": {"paired_counts": paired, "initial_coverage": initial,
                    "initial_paired_counts": {"both": initial, "feedback_only": 0,
                                               "regeneration_only": 0,
                                               "neither": len(primary) - initial},
                    "initial_coverage_rate_on_planned": initial / 24,
                    "meaningful_gain": MEANINGFUL_GAIN,
                    "point_difference_on_planned": (paired["feedback_only"] - paired["regeneration_only"]) / 24,
                    "arms": {a: _arm_summary(primary, a, 24) for a in ("feedback", "regeneration")},
                    "mcnemar_pvalue": None, "difference_interval": None,
                    "inference_status": "withheld_incomplete"},
        "outside_grammar": {"arms": {a: _arm_summary(outside, a, 12)
                                      for a in ("feedback", "regeneration")},
                            "interpretation": "descriptive separate denominator; compatibility does not imply truth was included"},
        "cost": {"records": len(records), "totals": {},
                 "scope": "completed record costs only; run.json additionally records consumed resources of an aborted case"},
        "secondary_paired_counts": {field: _paired(primary, field)
                                    for field in ("correct_resolution", "false_resolution",
                                                  "truth_excluded_when_covered", "truth_absent_bank_relative_survivor", "no_fit")},
        "limits": ["Cases, not cells or measurement draws, are independent units.",
                   "Exact McNemar assumes independent case pairs and conditionally exchangeable discordant direction under its sharp null; a weak pooled zero-gain null with heterogeneous directional probabilities is not sufficient.",
                   "Stratified intervals concern the declared case-sampling populations, conditional on the fixed model and protocol.",
                   "A bank-relative resolution cannot rule out an omitted true mechanism."],
    }
    totals: dict[str, float] = {}
    for row in records:
        for name, value in row.get("cost", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not math.isfinite(value) or value < 0:
                    raise ValueError("costs must be finite and nonnegative")
                totals[name] = totals.get(name, 0) + value
    summary["cost"]["totals"] = totals
    if complete:
        primary_report = summary["primary"]
        ci = stratified_difference_ci(primary)
        pvalue = exact_mcnemar(paired["feedback_only"], paired["regeneration_only"])
        primary_report.update(mcnemar_pvalue=pvalue, difference_interval=ci,
                              inference_status="complete_described_assumptions_required",
                              positive_paired_test=(pvalue < 0.05 and paired["feedback_only"] > paired["regeneration_only"]),
                              point_gain_at_least_meaningful=(primary_report["point_difference_on_planned"] >= MEANINGFUL_GAIN),
                              lower_bound_exceeds_meaningful=(ci["bounds"][0] > MEANINGFUL_GAIN))
        for arm in ("feedback", "regeneration"):
            final = primary_report["arms"][arm]["generated_coverage"]
            primary_report["arms"][arm]["change_from_shared_initial"] = (final - initial) / 24
    return summary


def mcnemar_power(n: int, p_win: float, p_loss: float, alpha: float = 0.05) -> float:
    """Unconditional iid planning power for the exact two-sided paired test."""
    if (not isinstance(n, int) or isinstance(n, bool) or n < 1 or p_win < 0
            or p_loss < 0 or p_win + p_loss > 1 or not 0 < alpha < 1):
        raise ValueError("invalid planning parameters")
    discordance = p_win + p_loss
    if discordance == 0:
        return 0.0
    answer = 0.0
    for d in range(1, n + 1):
        conditional = p_win / discordance
        reject = sum(float(binom.pmf(w, d, conditional)) for w in range(d + 1)
                     if exact_mcnemar(w, d - w) <= alpha)
        answer += float(binom.pmf(d, n, discordance)) * reject
    return answer


def power_table() -> list[dict[str, Any]]:
    return [{"n": 24, "p_feedback_only": win, "p_regeneration_only": loss,
             "paired_gain": win - loss, "power": mcnemar_power(24, win, loss),
             "assumption": "hypothetical iid case pairs, not an expected empirical effect"}
            for win, loss in ((0.25, 0.05), (0.35, 0.05), (0.45, 0.05))]
