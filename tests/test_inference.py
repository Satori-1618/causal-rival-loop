"""Tests the delivered inference path, not a parallel classifier."""
from pathlib import Path
import shutil

import numpy as np
import pytest

from rival_loop import dsl, inference, worlds
from rival_loop.vendor import design, compatible_set


MENU = [f"{kind}:c{context}" for context in (0, 1) for kind in ("native", "full")]
MENU += [f"read_{channel}:c{context}:d{dose}" for channel in ("a", "b")
         for context in (0, 1) for dose in ("0.5", "1", "2")]


def public(sigma=0.03):
    return {"menu": MENU, "sigma": sigma}


def world_public(sigma=0.03, family="linear", amplitude="1", gain="1"):
    return {"menu": list(worlds.MENU), "sigma": sigma, "family": family,
            "amplitude": amplitude, "output_gain": gain}


def records(win=0, loss=0):
    result = []
    for stratum in ("represented", "equivalent", "outside"):
        for index in range(12):
            a = index < win and stratum != "outside"
            b = win <= index < win + loss and stratum != "outside"
            result.append({"case_id": f"{stratum}-{index}", "independent_unit": f"{stratum}-{index}",
                           "split": "evaluation", "stratum": stratum, "initial_coverage": False,
                           "arms": {name: {"generated_coverage": covered, "outcome": "insufficient_evidence",
                                           "call_status": "ok", "valid_generated_count": 2}
                                    for name, covered in (("feedback", a), ("regeneration", b))},
                           "cost": {"measurement_draws": 192, "generator_calls": 3}})
    return result


def test_vendored_code_provenance_and_tamper(tmp_path):
    assert inference.verify_upstream()["passed"]
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "src/rival_loop/vendor", tmp_path / "src/rival_loop/vendor")
    shutil.copytree(root / "docs", tmp_path / "docs")
    target = tmp_path / "src/rival_loop/vendor/design.py"
    target.write_text(target.read_text() + "\n# changed\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        inference.verify_upstream(tmp_path)


def test_full_menu_known_sigma_intervals_and_validation():
    radii = inference.radii(public(), 1e-7)
    expected = inference.selection.radii([0.03] * 16, [8] * 16, 0.005, 1e-7)
    assert np.array_equal(radii, expected)
    assert len(radii) == 16
    assert radii[0] > 0.03 / np.sqrt(8)
    for sigma in (0, -1, float("nan"), True, [0.03] * 15):
        with pytest.raises(ValueError):
            inference.radii(public(sigma), 0)
    with pytest.raises(ValueError):
        inference.radii(public(), -1)
    with pytest.raises(ValueError):
        inference.radii(public(), 0, n=True)


def test_selector_actual_budget_no_outcomes_and_aliases():
    a = [0.0] * 16
    b = [0.0] * 4 + [1.0] * 12
    predictions = {"a": a, "a_alias": a, "b": b}
    groups = design.signatures(predictions)
    result = inference.select_cells(predictions, groups, public(), 0)
    assert result["policy"] == "coverage_first"
    assert result["cells"][:4] == [0, 1, 2, 3]
    assert len(result["cells"]) == 8
    assert result["plans"]["coverage_first"] == {"cells": result["cells"],
                                                "counts": [8] * 8, "cost": 64}
    assert {MENU[index] for index in result["extras"]} == {
        "read_a:c0:d2", "read_b:c0:d2", "read_a:c1:d2", "read_b:c1:d2"}
    assert result["plans"]["maximin"]["cost"] == 64
    assert result["subsets_examined"] == 495
    direct = inference.selection.select(predictions, groups, MENU, [0.03] * 16, 0,
                                        mandatory_count=4, extras=4, samples=8, alpha=0.005)
    assert result["plans"]["maximin"] == direct["plans"]["maximin"]
    assert result["maximin_score"] == direct["maximin_score"]
    assert result["maximin_score_scope"] == "upstream unconstrained maximin diagnostic plan"
    check = inference.known_bank_preflight(predictions, groups, public(), 0)
    assert check["all_pairs_above_one"]
    assert check["minimum_ratio"] == result["minimum_separation_ratio"]
    assert check["structural_classes_preserved"]
    assert check["purchased_cell_class_count"] == 2
    assert check["physical_draws"] == 64


@pytest.mark.parametrize("include_generated", [False, True], ids=["seeds_only", "context_independent"])
def test_context_independent_submitted_bank_cannot_omit_either_context(include_generated):
    setting = world_public()
    rules = [rule["readout"] for rule in dsl.seed_rules()]
    if include_generated:
        rules += [{"op": op, "left": {"var": "a"}, "right": {"var": "b"}}
                  for op in ("avg", "min", "max")]
    predictions = {str(index): dsl.predict(rule, setting) for index, rule in enumerate(rules)}
    result = inference.select_cells(predictions, design.signatures(predictions), setting, 0)
    assert {setting["menu"][index] for index in result["extras"]} == {
        "read_a:c0:d2", "read_b:c0:d2", "read_a:c1:d2", "read_b:c1:d2"}
    # This bank gives no submitted-rival reason to buy the second context.
    # The old selector's stable tie-break spends all four extras in c0.
    assert all(":c0:" in setting["menu"][index]
               for index in result["plans"]["maximin"]["cells"][4:])


@pytest.mark.parametrize("family", worlds.OPEN_FAMILIES)
def test_seed_selected_plan_preserves_all_59_catalog_classes(family):
    setting = world_public(family=family)
    seeds = {rule["id"]: dsl.predict(rule["readout"], setting) for rule in dsl.seed_rules()}
    selected = inference.select_cells(seeds, design.signatures(seeds), setting, 0)
    catalog = {entry["template_id"]: dsl.predict(entry["readout"], setting)
               for entry in worlds.catalog()}
    assert len(design.signatures(catalog)) == 59
    assert len(design.signatures(design.restrict(catalog, selected["cells"]))) == 59
    # The submitted seed bank's old optimal plan collapses omitted catalog
    # classes that differ only in the second context.
    assert len(design.signatures(design.restrict(catalog, selected["plans"]["maximin"]["cells"]))) < 59


def test_selected_plan_score_is_distinct_from_unconstrained_maximin_score():
    a = [0.0] * 16
    b = [0.0] * 16
    b[MENU.index("read_a:c0:d0.5")] = 1.0
    result = inference.select_cells({"a": a, "b": b}, [["a"], ["b"]], public(), 0)
    assert result["minimum_separation_ratio"] == 0
    assert result["maximin_score"] > 1
    assert result["cells"] != result["plans"]["maximin"]["cells"]


def test_preflight_separates_noise_limit_from_structural_blindspot():
    setting = world_public(amplitude="1/2")
    predictions = {entry["template_id"]: dsl.predict(entry["readout"], setting)
                   for entry in worlds.catalog()}
    groups = design.signatures(predictions)
    low = inference.known_bank_preflight(predictions, groups, setting, 0)
    high = inference.known_bank_preflight(predictions, groups, {**setting, "sigma": 0.30}, 0)
    for check in (low, high):
        assert check["structural_classes_preserved"]
        assert check["purchased_cell_class_count"] == check["class_count"] == 59
        assert check["collapsed_full_menu_class_pairs"] == 0
        assert check["numerically_resolved"]
    assert low["minimum_structural_gap"] == high["minimum_structural_gap"]
    assert low["resolution_status"] == "resolved"
    assert low["minimum_ratio"] > 1
    assert high["resolution_status"] == "noise_limit"
    assert high["minimum_ratio"] < 1
    assert low["minimum_ratio"] == pytest.approx(10 * high["minimum_ratio"])

    a = [0.0] * 16
    b = [0.0] * 16
    b[MENU.index("read_a:c1:d0.5")] = 1.0
    for sigma in (1e-8, 0.30):
        blind = inference.known_bank_preflight({"a": a, "b": b}, [["a"], ["b"]], public(sigma), 0)
        assert not blind["structural_classes_preserved"]
        assert blind["purchased_cell_class_count"] == 1
        assert blind["collapsed_full_menu_class_pairs"] == 1
        assert blind["resolution_status"] == "structural_blindspot"
        assert blind["minimum_ratio"] == blind["minimum_structural_gap"] == 0


def test_preflight_separates_numerical_limit_and_aliases_do_not_add_class_pairs():
    a = [0.0] * 16
    b = [0.0] * 4 + [0.01] * 12
    predictions = {"a": a, "b": b}
    direct = inference.known_bank_preflight(predictions, [["a"], ["b"]], public(1e-8), 0.01)
    assert direct["structural_classes_preserved"]
    assert not direct["numerically_resolved"]
    assert direct["resolution_status"] == "numerical_limit"
    aliased = {**predictions, "a_alias": a, "b_alias": b}
    check = inference.known_bank_preflight(aliased, design.signatures(aliased), public(1e-8), 0.01)
    assert check == direct
    assert len(check["pair_ratios"]) == 1
    with pytest.raises(ValueError, match="aliases disagree"):
        inference.known_bank_preflight(aliased, [["a", "b_alias"], ["b", "a_alias"]], public(), 0)


def test_budget_preflight_flags_hard_pair_instead_of_claiming_resolution():
    a = [0.0] * 16
    b = [0.0] * 4 + [0.001] * 12
    check = inference.known_bank_preflight({"a": a, "b": b}, [["a"], ["b"]], public(), 0)
    assert not check["all_pairs_above_one"]
    assert check["minimum_ratio"] < 1


def test_classifier_preserves_full_menu_classes_on_selected_ties():
    full = {"a": [0, 0, 1], "alias": [0, 0, 1], "b": [0, 0, 2]}
    groups = design.signatures(full)
    partial = {name: row[:2] for name, row in full.items()}
    classified = inference.classify_bank(partial, groups, [0, 0], [0.1, 0.1])
    assert classified["outcome"] == "insufficient_evidence"
    assert len(classified["retained_groups"]) == 2
    assert classified == compatible_set.compatible_set(partial, [0, 0], [0.1, 0.1], groups)
    terminal = inference.classify_bank(full, groups, [0, 0, 1], [0.1] * 3)
    assert terminal["outcome"] == "resolved"
    assert terminal["retained"] == ["a", "alias"]


def test_single_group_is_not_identification():
    result = inference.select_cells({"a": [0] * 16}, [["a"]], public(), 0)
    assert result["status"] == "no_discriminating_rivals"
    single = inference.classify_bank({"a": [0]}, [["a"]], [0], 0.1)
    assert single["outcome"] == "insufficient_evidence"


def test_clopper_pearson_ties_do_not_collapse():
    lower, upper = inference.clopper_pearson(0, 12, 0.9875)
    assert lower == 0 and upper > 0.3
    report = inference.analyze(records())
    bounds = report["primary"]["difference_interval"]["bounds"]
    assert bounds[0] < 0 < bounds[1]
    assert report["primary"]["mcnemar_pvalue"] == 1
    assert report["status"] == "completed"
    assert report["planned_primary_units"] == 24


def test_stratified_counts_gain_and_meaningful_threshold():
    report = inference.analyze(records(win=8, loss=1))
    primary = report["primary"]
    assert primary["paired_counts"] == {"both": 0, "feedback_only": 16,
                                         "regeneration_only": 2, "neither": 6}
    assert primary["meaningful_gain"] == 0.20
    assert primary["point_difference_on_planned"] == pytest.approx(14 / 24)
    assert primary["mcnemar_pvalue"] == pytest.approx(inference.exact_mcnemar(16, 2))
    assert primary["difference_interval"]["confidence_at_least"] == 0.95
    assert set(primary["difference_interval"]["strata"]) == {"represented", "equivalent"}
    assert report["cost"]["totals"]["measurement_draws"] == 36 * 192


def test_partial_run_never_gets_completed_inference_and_missing_counts_remain():
    report = inference.analyze(records(win=1)[:12])
    assert report["status"] == "incomplete"
    assert report["planned_primary_units"] == 24
    assert report["recorded_primary_units"] == 12
    assert report["primary"]["mcnemar_pvalue"] is None
    assert report["primary"]["difference_interval"] is None
    assert report["primary"]["arms"]["feedback"]["missing"] == 12
    assert report["primary"]["arms"]["feedback"]["generated_coverage_rate_on_planned"] == 1 / 24


def test_duplicate_units_refused():
    sample = records()
    sample[1]["independent_unit"] = sample[0]["independent_unit"]
    with pytest.raises(ValueError, match="independent unit"):
        inference.analyze(sample)


def test_invalid_counts_and_nonfinite_cost_refused():
    for args in ((-1, 2), (0, 0), (3, 2), (True, 2)):
        with pytest.raises(ValueError):
            inference.clopper_pearson(*args)
    sample = records()
    sample[0]["cost"]["generator_calls"] = float("nan")
    with pytest.raises(ValueError, match="costs"):
        inference.analyze(sample)


def test_power_matches_prespecified_iid_planning_calculation():
    assert [row["paired_gain"] for row in inference.power_table()] == pytest.approx([0.2, 0.3, 0.4])
    powers = [row["power"] for row in inference.power_table()]
    assert powers == pytest.approx([0.2835, 0.5758, 0.7994], abs=0.0001)


def test_development_descriptive_has_no_held_out_test_even_when_complete():
    sample = records(win=2)[:12]
    for row in sample:
        row["split"] = "development"
    report = inference.analyze(sample)
    assert report["status"] == "development_complete_descriptive"
    assert report["mcnemar_pvalue"] is None
    assert report["difference_interval"] is None
    assert inference.analyze([], split="development")["status"] == "development_incomplete"
    with pytest.raises(ValueError, match="evaluation records"):
        inference.analyze(records(), split="development")


def test_truth_absent_survivor_and_class_diversity_reported():
    sample = records()
    for row in sample:
        row["truth_class_id"] = "template-one" if row["stratum"] != "outside" else "external"
        for arm in row["arms"].values():
            arm["generated_class_count"] = 2
            arm["truth_absent_bank_relative_survivor"] = True
    report = inference.analyze(sample)
    assert report["realized_truth_diversity"]["primary"]["distinct_mechanism_classes"] == 1
    assert report["realized_truth_diversity"]["primary"]["recorded_class_ids"] == 24
    assert report["primary"]["arms"]["feedback"]["truth_absent_bank_relative_survivor"] == 24
    assert report["primary"]["arms"]["feedback"]["generated_diversity"]["mean_per_recorded_bank"] == 2
    assert report["outside_grammar"]["arms"]["feedback"]["truth_absent_bank_relative_survivor"] == 12


def test_prespecified_resolution_bins_are_descriptive_and_use_primary_cases_only():
    sample = records(win=2, loss=1)
    for index, row in enumerate(sample):
        row["preflight_minimum_separation_ratio"] = (1.0, 3.0, 3.1)[index % 3]
        row["setting"] = {"amplitude": "1/5" if index % 2 else "2", "output_gain": "4/5",
                          "sigma": 0.03 if index % 2 else 0.3, "family": "linear"}
    report = inference.analyze(sample)["descriptive_primary_resolution"]
    assert [band["n"] for band in report["ratio_bands"].values()] == [8, 8, 8]
    assert [band["n"] for band in report["by_known_noise_sd"].values()] == [12, 12]
    assert report["realized_parameter_ranges"]["amplitude"] == {"n": 24, "minimum": 0.2, "maximum": 2.0}
    assert report["records_without_ratio"] == report["records_without_setting"] == 0
    assert report["ratio_bands"]["ratio_le_1"]["generated_coverage_paired_counts"]["feedback_only"] == 2
    assert "pvalue" not in str(report)
    sample[0]["preflight_minimum_separation_ratio"] = float("nan")
    with pytest.raises(ValueError, match="separation ratio"):
        inference.analyze(sample)
