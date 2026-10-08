"""Intervention semantics, strict generation boundary, and sealed-world tests."""
import copy
import json
from collections import Counter
from fractions import Fraction

import pytest

from rival_loop import dsl, worlds


def case():
    return {"case_id": "test", "amplitude": "1", "output_gain": "1",
            "family": "linear", "sigma": .03, "menu": list(worlds.MENU)}


def private(ast):
    return {"case_id": "test", "truth_kind": "represented", "truth_ast": ast}


def entry(ast=None):
    return {"id": "candidate", "mechanism": "Read a after intervention.",
            "readout": {"var": "a"} if ast is None else ast}


def test_strict_response_and_entry_schema():
    accepted = dsl.parse_response(json.dumps({"rules": [entry()]}))
    assert accepted == [entry()]
    assert dsl.parse_response('{"rules": []}') == []
    accepted[0]["readout"]["var"] = "b"
    assert entry()["readout"] == {"var": "a"}


@pytest.mark.parametrize("payload", [
    '{"rules": [], "rules": []}',
    '{"rules": [{"id":"x","id":"y","mechanism":"a","readout":{"var":"a"}}]}',
    '{"rules": [{"id":"x","mechanism":"a","readout":{"var":"a","var":"b"}}]}',
    '{"rules": "AAA"}', '{"rules": null}', '{"rules": [], "truth": "a"}',
    '```json\n{"rules": []}\n```', '{"rules": [], "x": NaN}',
])
def test_raw_json_injection_and_duplicate_fields_rejected(payload):
    with pytest.raises(ValueError):
        dsl.parse_response(payload)


@pytest.mark.parametrize("ast", [
    "a", ["a"], {"var": "truth"}, {"var": "a", "offset": 0},
    {"const": 1}, {"const": 0.0}, {"const": False},
    {"op": "eval", "code": "print(1)"},
    {"op": "lookup", "condition": "read_a:c0:d1"},
    {"op": "avg", "left": {"var": "a"}},
    {"op": "select", "zero": {"var": "a"}, "one": {"var": "b"}, "context": 0},
])
def test_unsupported_language_rejected(ast):
    with pytest.raises(ValueError):
        dsl.validate_rule(ast)


def test_depth_and_node_limits_are_separate():
    a = {"var": "a"}
    tree = copy.deepcopy(a)
    for _ in range(4):
        tree = {"op": "avg", "left": tree, "right": copy.deepcopy(a)}
    with pytest.raises(ValueError, match="depth"):
        dsl.validate_rule(tree)  # Nine nodes, but depth four.
    balanced = {"op": "avg", "left": a, "right": a}
    balanced = {"op": "avg", "left": balanced, "right": balanced}
    balanced = {"op": "avg", "left": balanced, "right": balanced}
    with pytest.raises(ValueError, match="nodes"):
        dsl.validate_rule(balanced)  # Depth three, but 15 nodes.


def test_response_caps_duplicate_ids_and_origin_spoof():
    for rules in ([entry()] * 2,
                  [{**entry(), "id": f"x{i}"} for i in range(5)],
                  [{**entry(), "origin": "seed"}],
                  [{**entry(), "mechanism": " "}]):
        with pytest.raises(ValueError):
            dsl.parse_response(json.dumps({"rules": rules}))


def test_actual_coordinate_replacement_and_exact_signature():
    a, b = {"var": "a"}, {"var": "b"}
    assert len(worlds.MENU) == 16
    expected = [0, 1, 0, 1, .5, 1, 2, 0, 0, 0, .5, 1, 2, 0, 0, 0]
    assert dsl.predict(a, case()) == expected
    assert worlds.execute(case(), private(a)) == expected
    assert worlds.execute(case(), private(b), cells=["read_a:c0:d2", "read_b:c0:d2"]) == [0., 2.]
    assert dsl.signature(a, case())[4] == "1/2"
    gain = {**case(), "amplitude": "1/3", "output_gain": "4/5"}
    assert dsl.signature(a, gain)[1] == "4/15"


@pytest.mark.parametrize("ast", [
    {"const": 0}, {"var": "a"}, {"var": "b"},
    {"op": "avg", "left": {"var": "a"}, "right": {"var": "b"}},
    {"op": "min", "left": {"var": "a"}, "right": {"var": "b"}},
    {"op": "max", "left": {"var": "a"}, "right": {"var": "b"}},
    {"op": "select", "zero": {"var": "a"}, "one": {"var": "b"}},
])
@pytest.mark.parametrize("family", worlds.OPEN_FAMILIES)
def test_independent_torch_formula_agreement(ast, family):
    public = {**case(), "family": family, "amplitude": "17/10", "output_gain": "113/100"}
    expected = dsl.predict(ast, public)
    actual = worlds.execute(public, private(ast), dtype="float64")
    assert actual == pytest.approx(expected, abs=1e-14)
    gates = worlds.qualify(public, private(ast))
    assert gates["all_passed"]
    assert gates["identity_patch_exact"]
    assert gates["full_patch_matches_native_donor"]
    assert max(abs(a - b) for a, b in zip(worlds.execute(public, private(ast)), expected)) <= gates["numeric_bound"]


def test_catalog_exact_dedup_and_excluded_classes():
    templates = worlds.catalog()
    assert len(templates) == 59
    sigs = {dsl.signature(template["readout"], case()) for template in templates}
    assert len(sigs) == 59
    for ast in [{"var": "a"}, {"var": "b"},
                {"op": "avg", "left": {"var": "a"}, "right": {"var": "b"}},
                {"op": "min", "left": {"var": "a"}, "right": {"var": "b"}},
                {"op": "select", "zero": {"var": "a"}, "one": {"var": "b"}},
                {"op": "select", "zero": {"var": "b"}, "one": {"var": "a"}}]:
        assert dsl.signature(ast, case()) not in sigs
    for template in templates:
        dsl.validate_rule(template["readout"])
        assert dsl.signature(template["readout"], case())[1] == "1"
        assert dsl.signature(template["readout"], case())[3] == "1"


def test_sampling_manifest_reproducible_disjoint_and_no_truth_in_public():
    public, truths, metadata = worlds.make_cases()
    assert (public, truths, metadata) == worlds.make_cases()
    assert len(public) == len(truths) == 48
    assert Counter((p["split"], p["stratum"]) for p in public) == {
        ("development", "represented"): 12,
        ("evaluation", "represented"): 12,
        ("evaluation", "equivalent"): 12,
        ("evaluation", "outside"): 12,
    }
    assert len({p["case_id"] for p in public}) == 48
    assert all(p["case_id"] == t["case_id"] for p, t in zip(public, truths))
    dev_ids = {t["template_id"] for p, t in zip(public, truths) if p["split"] == "development"}
    eval_ids = {t["template_id"] for p, t in zip(public, truths)
                if p["split"] == "evaluation" and p["stratum"] != "outside"}
    assert len(dev_ids) == 12 and 1 <= len(eval_ids) <= 24 and not dev_ids & eval_ids
    assert metadata["evaluation_distinct_in_grammar_classes"] == len(eval_ids)
    assert "WITH REPLACEMENT" in metadata["evaluation_class_sampling"]
    assert metadata["evaluation_template_pool_classes"] == 47
    assert metadata["independent_cases_are_not_distinct_mechanism_families"]
    for p in public:
        assert not set(p) & {"truth_ast", "truth_kind", "alias_ast", "template_id", "predictions"}
        assert Fraction(1, 10) <= Fraction(p["amplitude"]) <= 3
        assert Fraction(4, 5) <= Fraction(p["output_gain"]) <= Fraction(6, 5)
        assert p["sigma"] in worlds.NOISE_LEVELS
        assert p["family"] in worlds.OPEN_FAMILIES


def test_equivalent_graph_alias_and_outside_grammar_truth():
    public, truths, _ = worlds.make_cases()
    for p, t in zip(public, truths):
        if p["stratum"] == "equivalent":
            assert t["alias_ast"] != t["truth_ast"]
            assert worlds.execute(p, t, alias=True) == worlds.execute(p, t)
            assert worlds.qualify(p, t)["all_passed"]
        if p["stratum"] == "outside":
            truth = [Fraction(x) for x in worlds.reference_signature(p, t)]
            # Every admissible expression is between zero and max(a,b), so
            # no rule can reach the external-gain full endpoint.
            maximum = [Fraction(x) for x in dsl.signature({"op": "max", "left": {"var": "a"}, "right": {"var": "b"}}, p)]
            assert truth[1] > maximum[1]
            assert worlds.execute(p, t, dtype="float64") == pytest.approx([float(x) for x in truth])


@pytest.mark.parametrize("family", ["squared", "saturated_relu", "unknown"])
def test_reserved_transformations_never_available(family):
    with pytest.raises(ValueError):
        worlds.execute({**case(), "family": family}, private({"var": "a"}))
    with pytest.raises(ValueError):
        dsl.predict({"var": "a"}, {**case(), "family": family})


def test_invalid_cases_and_numeric_scope():
    with pytest.raises(ValueError):
        worlds.make_cases(1, 1)
    with pytest.raises(ValueError):
        worlds.execute(case(), {**private({"var": "a"}), "case_id": "wrong"})
    with pytest.raises(ValueError):
        worlds.execute(case(), private({"var": "a"}), cells=["not-a-cell"])
    with pytest.raises(ValueError):
        worlds.execute(case(), private({"var": "a"}), dtype="bfloat16")
    with pytest.raises(ValueError):
        dsl.signature({"var": "a"}, {**case(), "menu": list(worlds.MENU[:4])})
    gates = worlds.qualify(case(), private({"var": "a"}))
    assert gates["eight_epsilon_scale_allowance"] > 0
    assert "not a universal" in gates["scope"]


@pytest.mark.parametrize("field,value", [("amplitude", "0"), ("amplitude", "-1"),
                                         ("output_gain", "NaN"), ("output_gain", "0")])
def test_execution_parameters_fail_closed(field, value):
    with pytest.raises(ValueError):
        worlds.execute({**case(), field: value}, private({"var": "a"}))


def test_execution_rejects_changed_menu_even_for_a_subset():
    with pytest.raises(ValueError):
        worlds.execute({**case(), "menu": list(reversed(worlds.MENU))},
                       private({"var": "a"}), cells=["native:c0"])
