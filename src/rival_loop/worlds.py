"""Known-truth CPU computations and sealed case generation.

Only the two upstream *open* transformations are used. Observations execute a
Torch graph with real coordinate replacement. Candidate predictions use the
independent Fraction interpreter in dsl.py. Generator payload construction must
omit private records and public split/stratum metadata.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from fractions import Fraction

from . import dsl

MENU = (
    "native:c0", "full:c0", "native:c1", "full:c1",
    *(f"{read}:c{context}:d{dose}" for context in (0, 1)
      for read in ("read_a", "read_b") for dose in ("0.5", "1", "2")),
)
OPEN_FAMILIES = ("linear", "relu_offset")
AMPLITUDE_INTERVALS = ((100, 300), (300, 1000), (1000, 3000))
NOISE_LEVELS = (0.03, 0.10, 0.30)


def _binary(op, left, right):
    return {"op": op, "left": copy.deepcopy(left), "right": copy.deepcopy(right)}


def _select(zero, one):
    return {"op": "select", "zero": copy.deepcopy(zero), "one": copy.deepcopy(one)}


def catalog() -> list[dict]:
    """65 templates minus the six upstream classes = 59 exact classes.

    S has five branches; C has four composed branches. Only S×S, S×C, and
    C×S are allowed here. A full-menu exact signature defines the class, not
    syntactic identity. These templates are benchmark truths, not the full DSL.
    """
    a, b = {"var": "a"}, {"var": "b"}
    minimum, maximum = _binary("min", a, b), _binary("max", a, b)
    simple = [a, b, _binary("avg", a, b), minimum, maximum]
    composed = [_binary("avg", a, minimum), _binary("avg", a, maximum),
                _binary("avg", b, minimum), _binary("avg", b, maximum)]
    probe = {"amplitude": "1", "output_gain": "1", "family": "linear", "menu": list(MENU)}
    excluded = {dsl.signature(ast, probe) for ast in
                (a, b, simple[2], minimum, _select(a, b), _select(b, a))}
    seen, result = set(), []
    for lefts, rights in ((simple, simple), (simple, composed), (composed, simple)):
        for zero in lefts:
            for one in rights:
                ast = dsl.validate_rule(_select(zero, one))
                sig = dsl.signature(ast, probe)
                if sig in seen or sig in excluded:
                    continue
                seen.add(sig)
                code = json.dumps(ast, sort_keys=True, separators=(",", ":"))
                result.append({"template_id": hashlib.sha256(code.encode()).hexdigest()[:20],
                               "readout": ast, "unit_signature": list(sig)})
    if len(result) != 59:
        raise AssertionError("Declared 65-template construction did not yield 59 retained classes")
    return result


def _parameters(rng):
    # IID conditional on the declared stratum and reserved development pool.
    # Fixed outcome-free quotas concern strata, not realized parameter bands.
    band = rng.randrange(3)
    low, high = AMPLITUDE_INTERVALS[band]
    amplitude = Fraction(rng.randint(low, high), 1000)
    gain = Fraction(rng.randint(800, 1200), 1000)
    return str(amplitude), str(gain), rng.choice(NOISE_LEVELS), rng.choice(OPEN_FAMILIES)


def make_cases(dev_seed=2026100801, eval_seed=2026100802):
    """Build a reserved development pool and IID evaluation cases.

    Evaluation templates are drawn with replacement from the 47 classes outside
    development. Repeated classes are independent cases, not replications of
    distinct mechanism families. This supports within-stratum binomial sampling
    inference conditional on the reserved development pool.
    """
    if type(dev_seed) is not int or type(eval_seed) is not int or dev_seed == eval_seed:
        raise ValueError("Development and evaluation require distinct integer seeds")
    templates = catalog()
    dev_rng, eval_rng = random.Random(dev_seed), random.Random(eval_seed)
    dev_rng.shuffle(templates)
    dev_templates, remaining = templates[:12], templates[12:]
    eval_templates = [eval_rng.choice(remaining) for _ in range(24)]
    public_cases, private_cases = [], []

    def append_case(split, stratum, index, template, rng, seed):
        identifier = hashlib.sha256(f"rival-loop-v1:{seed}:{split}:{stratum}:{index}".encode()).hexdigest()[:24]
        amplitude, gain, sigma, family = _parameters(rng)
        public = {"case_id": identifier, "independent_unit": identifier,
                  "split": split, "stratum": stratum, "family": family,
                  "amplitude": amplitude, "output_gain": gain, "sigma": sigma,
                  "menu": list(MENU)}
        truth = {"var": "a"} if stratum == "outside" else template["readout"]
        private = {"case_id": identifier, "truth_kind": "external_gain" if stratum == "outside" else "represented",
                   "truth_ast": copy.deepcopy(truth)}
        if stratum == "equivalent":
            # Duplicate computation followed by averaging is a different graph
            # with a constructive all-input equality proof. It may exceed the
            # generator node cap; it is not a second independent case.
            private["alias_ast"] = _binary("avg", truth, truth)
            private["alias_proof"] = "(r+r)/2 = r for every real input and context"
        if template is not None:
            private["template_id"] = template["template_id"]
        public_cases.append(public)
        private_cases.append(private)

    for index, template in enumerate(dev_templates):
        append_case("development", "represented", index, template, dev_rng, dev_seed)
    for index, template in enumerate(eval_templates[:12]):
        append_case("evaluation", "represented", index, template, eval_rng, eval_seed)
    for index, template in enumerate(eval_templates[12:]):
        append_case("evaluation", "equivalent", index, template, eval_rng, eval_seed)
    for index in range(12):
        append_case("evaluation", "outside", index, None, eval_rng, eval_seed)
    metadata = {
        "version": 1, "development_seed": dev_seed, "evaluation_seed": eval_seed,
        "development_cases": 12, "evaluation_cases": 36,
        "evaluation_strata": {"represented": 12, "equivalent": 12, "outside": 12},
        "catalog_classes": 59, "development_evaluation_classes_disjoint": True,
        "development_reserved_classes": 12, "evaluation_template_pool_classes": 47,
        "evaluation_class_sampling": "Independent uniform draws WITH REPLACEMENT from the 47-class non-development pool",
        "evaluation_distinct_in_grammar_classes": len({item["template_id"] for item in eval_templates}),
        "independent_cases_are_not_distinct_mechanism_families": True,
        "amplitude_sampling": "Uniform integer grid, step 0.001, within assigned [0.1,0.3], [0.3,1], [1,3] inclusive",
        "output_gain_sampling": "Uniform integer grid [0.8,1.2], step 0.001 inclusive",
        "noise_sd": list(NOISE_LEVELS), "noise_assignment": "Independent uniform draw from the three declared noise levels",
        "family": list(OPEN_FAMILIES), "family_assignment": "Independent uniform draw from the two open families",
        "amplitude_assignment": "Independent uniform draw from the three amplitude intervals, followed by a uniform grid draw within the interval",
        "equivalent_pair_is_one_unit": True,
    }
    return public_cases, private_cases, metadata


def reference_signature(public, private):
    """Independent, exact truth; never include this in a generator payload."""
    if public["case_id"] != private["case_id"]:
        raise ValueError("Case ID mismatch")
    sig = dsl.signature(private["truth_ast"], public)
    if private["truth_kind"] == "external_gain":
        return tuple(str(Fraction(value) * Fraction(3, 2)) for value in sig)
    if private["truth_kind"] != "represented":
        raise ValueError("Unknown private truth kind")
    return sig


def _torch_readout(node, hidden, context):
    """Torch graph implementation; does not call the rational interpreter."""
    import torch
    if "var" in node:
        return hidden[0 if node["var"] == "a" else 1]
    if "const" in node:
        return hidden.new_zeros(())
    operation = node["op"]
    if operation == "select":
        zero = _torch_readout(node["zero"], hidden, context)
        one = _torch_readout(node["one"], hidden, context)
        return (1.0 - context) * zero + context * one
    left = _torch_readout(node["left"], hidden, context)
    right = _torch_readout(node["right"], hidden, context)
    if operation == "avg":
        return (left + right) * 0.5
    if operation == "min":
        return left - torch.relu(left - right)
    if operation == "max":
        return right + torch.relu(left - right)
    raise ValueError("Unsupported Torch graph operation")


def _torch_forward(public, private, inputs, context, patch=None, alias=False):
    import torch
    hidden = torch.relu(inputs)
    if patch is not None:
        hidden = hidden.clone()
        for coordinate, value in patch.items():
            hidden[coordinate] = value
    ast = private["alias_ast"] if alias else private["truth_ast"]
    value = _torch_readout(ast, hidden, context)
    if public["family"] == "relu_offset":
        value = torch.relu(value - hidden.new_tensor(float(dsl.fraction(public["amplitude"]) * Fraction(3, 10))))
    elif public["family"] != "linear":
        raise ValueError("Reserved or unknown transformation is unavailable")
    value = value * hidden.new_tensor(float(dsl.fraction(public["output_gain"])))
    if private["truth_kind"] == "external_gain":
        value = value * 1.5
    elif private["truth_kind"] != "represented":
        raise ValueError("Unknown private truth kind")
    return value


def _validate_case_parameters(public):
    if tuple(public.get("menu", MENU)) != MENU:
        raise ValueError("Execution requires the complete frozen 16-cell menu")
    if public["family"] not in OPEN_FAMILIES:
        raise ValueError("Reserved or unknown transformation is unavailable")
    for name in ("amplitude", "output_gain"):
        value = dsl.fraction(public[name])
        if value <= 0 or not math.isfinite(float(value)):
            raise ValueError(f"{name} must be positive and finite")


def execute(public, private, *, dtype="float32", cells=None, alias=False):
    """Execute genuine coordinate replacement at the two-unit hidden layer."""
    import torch
    if public["case_id"] != private["case_id"]:
        raise ValueError("Case ID mismatch")
    _validate_case_parameters(public)
    if dtype not in ("float32", "float64"):
        raise ValueError("Only float32 and float64 execution is qualified")
    if alias and "alias_ast" not in private:
        raise ValueError("No constructive alias supplied")
    dsl.validate_rule(private["truth_ast"])
    selected = list(MENU if cells is None else cells)
    if any(cell not in MENU for cell in selected):
        raise ValueError("Unknown intervention")
    tensor_dtype = getattr(torch, dtype)
    amplitude = float(dsl.fraction(public["amplitude"]))
    recipient = torch.zeros(2, dtype=tensor_dtype)
    donor = torch.relu(torch.full((2,), amplitude, dtype=tensor_dtype))
    outputs = []
    with torch.no_grad():
        for cell in selected:
            # Independent parser and actual replacement, not scalar formulas.
            pieces = cell.split(":")
            operation, context = pieces[0], int(pieces[1][1:])
            dose = float(pieces[2][1:]) if len(pieces) == 3 else 1.0
            indices = (0, 1) if operation == "full" else (0,) if operation == "read_a" else (1,) if operation == "read_b" else ()
            patch = {coordinate: donor[coordinate] * dose for coordinate in indices}
            outputs.append(float(_torch_forward(public, private, recipient, context, patch, alias)))
    return outputs


def qualify(public, private):
    """Calibrate this actual graph at this menu; no universal dtype guarantee.

    A failed gate is an instrumentation failure. It must never be translated
    into a rejected candidate. Generated ASTs need their own call to this gate.
    """
    import torch
    low = execute(public, private, dtype="float32")
    high = execute(public, private, dtype="float64")
    exact = [float(Fraction(value)) for value in reference_signature(public, private)]
    scale = max(1.0, *(abs(value) for value in high), *(abs(value) for value in exact))
    max_numeric = max(abs(a - b) for a, b in zip(low, high))
    max_reference = max(abs(a - b) for a, b in zip(high, exact))
    allowance = 8.0 * torch.finfo(torch.float32).eps * scale
    reference_tolerance = 64.0 * torch.finfo(torch.float64).eps * scale
    identity_errors, endpoint_errors, native_errors = [], [], []
    forward_count = 32
    with torch.no_grad():
        for dtype in (torch.float32, torch.float64):
            recipient = torch.zeros(2, dtype=dtype)
            donor = torch.full((2,), float(dsl.fraction(public["amplitude"])), dtype=dtype)
            for context in (0, 1):
                native = float(_torch_forward(public, private, recipient, context))
                self_patch = float(_torch_forward(public, private, recipient, context,
                                                  {0: recipient[0], 1: recipient[1]}))
                donor_native = float(_torch_forward(public, private, donor, context))
                full = float(_torch_forward(public, private, recipient, context,
                                            {0: donor[0], 1: donor[1]}))
                identity_errors.append(abs(native - self_patch))
                endpoint_errors.append(abs(full - donor_native))
                measured = low if dtype == torch.float32 else high
                native_errors.append(abs(native - measured[context * 2]))
                forward_count += 4
    alias_error = 0.0
    if "alias_ast" in private:
        # Prove exact equality on the full menu as well as executed agreement.
        for cell, original in zip(MENU, reference_signature(public, private)):
            coords = dsl._cell_coordinates(cell, dsl.fraction(public["amplitude"]))
            alias_exact = dsl._output(dsl._evaluate(private["alias_ast"], *coords), public)
            if str(alias_exact) != original:
                raise ValueError("Constructive alias is not menu-equivalent")
        for dtype, original in (("float32", low), ("float64", high)):
            alias_values = execute(public, private, dtype=dtype, alias=True)
            alias_error = max(alias_error, *(abs(a - b) for a, b in zip(original, alias_values)))
            forward_count += 16
    bound = max_numeric + max_reference + allowance
    all_passed = (all(math.isfinite(value) for value in low + high + exact)
                  and max_reference <= reference_tolerance
                  and max(identity_errors + endpoint_errors + native_errors) == 0.0
                  and alias_error <= bound)
    return {
        "numeric_bound": bound, "all_passed": all_passed,
        "maximum_fp32_fp64_difference": max_numeric,
        "maximum_fp64_reference_difference": max_reference,
        "reference_tolerance": reference_tolerance,
        "eight_epsilon_scale_allowance": allowance,
        "identity_patch_exact": max(identity_errors) == 0.0,
        "full_patch_matches_native_donor": max(endpoint_errors) == 0.0,
        "native_menu_matches_unpatched": max(native_errors) == 0.0,
        "alias_maximum_difference": alias_error,
        "qualification_graph_forward_count": forward_count,
        "scope": "Finite-menu calibration for this graph and parameters; not a universal floating-point error bound",
    }
