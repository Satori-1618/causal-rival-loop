"""A deliberately small, non-executable-Python causal readout language.

The AST denotes a downstream rule on the *post-intervention* coordinates.
Predictions are computed with Fraction arithmetic, never supplied by the LLM.
"""
from __future__ import annotations

import copy
import json
import math
import re
from fractions import Fraction

MAX_NODES = 9
MAX_DEPTH = 3  # A leaf has depth zero.
MAX_RULES = 4
MAX_RESPONSE_BYTES = 65536
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


def validate_rule(rule: dict) -> dict:
    """Return a copy of a strict AST; reject unsupported or excessive trees."""
    count = 0

    def visit(node, depth):
        nonlocal count
        if not isinstance(node, dict):
            raise ValueError("Every AST node must be an object")
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("Rule exceeds nine nodes or depth three")
        keys = set(node)
        if keys == {"var"}:
            if node["var"] not in ("a", "b"):
                raise ValueError("Only post-intervention variables a and b are allowed")
            return
        if keys == {"const"}:
            if type(node["const"]) is not int or node["const"] != 0:
                raise ValueError("The only literal constant is integer zero")
            return
        operation = node.get("op")
        if operation in ("avg", "min", "max") and keys == {"op", "left", "right"}:
            visit(node["left"], depth + 1)
            visit(node["right"], depth + 1)
            return
        if operation == "select" and keys == {"op", "zero", "one"}:
            visit(node["zero"], depth + 1)
            visit(node["one"], depth + 1)
            return
        raise ValueError("Unsupported operation or extra/missing AST fields")

    try:
        visit(rule, 0)
    except RecursionError as exc:
        raise ValueError("Rule exceeds permitted depth") from exc
    return copy.deepcopy(rule)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_response(raw: str) -> list[dict]:
    """Parse exactly {rules: [{id, mechanism, readout}, ...]}.

    Empty banks are valid generation failures, not implicit hypotheses.
    Unknown fields, duplicate keys/IDs, Markdown fences, and code are rejected.
    """
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("Response must be a bounded JSON string")
    try:
        obj = json.loads(raw, object_pairs_hook=_unique_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(
                             ValueError(f"Non-finite JSON literal: {value}")))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Response must be strict JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {"rules"}:
        raise ValueError("Response must contain exactly the rules field")
    entries = obj["rules"]
    if not isinstance(entries, list) or len(entries) > MAX_RULES:
        raise ValueError("Rules must be a list of at most four entries")
    result, ids = [], set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "mechanism", "readout"}:
            raise ValueError("Each entry must have exactly id, mechanism, readout")
        identifier, description = entry["id"], entry["mechanism"]
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise ValueError("Rule ID must be a short, plain identifier")
        if identifier in ids:
            raise ValueError("Duplicate rule ID")
        if not isinstance(description, str) or not description.strip() or len(description) > 2000:
            raise ValueError("Mechanism must be a non-empty explanation of at most 2000 characters")
        ids.add(identifier)
        result.append({"id": identifier, "mechanism": description,
                       "readout": validate_rule(entry["readout"])})
    return result


def fraction(value) -> Fraction:
    """Parse disclosed finite rational parameters, avoiding binary float math."""
    if isinstance(value, bool):
        raise ValueError("Boolean is not a rational parameter")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Parameter must be finite")
    try:
        return Fraction(str(value))
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError("Invalid rational parameter") from exc


def _evaluate(node: dict, a: Fraction, b: Fraction, context: int) -> Fraction:
    """Internal evaluator; public entry points validate the tree first."""
    if "var" in node:
        return a if node["var"] == "a" else b
    if "const" in node:
        return Fraction(0)
    operation = node["op"]
    if operation == "select":
        return _evaluate(node["zero"] if context == 0 else node["one"], a, b, context)
    left = _evaluate(node["left"], a, b, context)
    right = _evaluate(node["right"], a, b, context)
    if operation == "avg":
        return (left + right) / 2
    if operation == "min":
        return min(left, right)
    if operation == "max":
        return max(left, right)
    raise ValueError("Unsupported internal graph operation")


def _cell_coordinates(cell: str, amplitude: Fraction):
    # Kept independent of the Torch intervention implementation.
    from .worlds import MENU
    if cell not in MENU:
        raise ValueError(f"Unknown intervention cell: {cell}")
    operation, raw_context, *dose = cell.split(":")
    context = int(raw_context[1:])
    dose_value = Fraction(dose[0][1:]) if dose else Fraction(1)
    a = amplitude if operation == "full" else amplitude * dose_value if operation == "read_a" else Fraction(0)
    b = amplitude if operation == "full" else amplitude * dose_value if operation == "read_b" else Fraction(0)
    return a, b, context


def _output(value: Fraction, public: dict) -> Fraction:
    amplitude = fraction(public["amplitude"])
    if public["family"] == "relu_offset":
        value = max(Fraction(0), value - Fraction(3, 10) * amplitude)
    elif public["family"] != "linear":
        raise ValueError("Only open linear and relu_offset families are permitted")
    return fraction(public["output_gain"]) * value


def signature(rule: dict, public_case: dict) -> tuple[str, ...]:
    """Exact complete-menu signature, with canonical rational strings."""
    ast = validate_rule(rule)
    amplitude = fraction(public_case["amplitude"])
    gain = fraction(public_case["output_gain"])
    if amplitude <= 0 or gain <= 0:
        raise ValueError("Amplitude and output gain must be positive")
    from .worlds import MENU
    if tuple(public_case.get("menu", MENU)) != MENU:
        raise ValueError("Predictions require the complete frozen 16-cell menu")
    return tuple(str(_output(_evaluate(ast, *_cell_coordinates(cell, amplitude)), public_case))
                 for cell in MENU)


def predict(rule: dict, public_case: dict) -> list[float]:
    return [float(Fraction(value)) for value in signature(rule, public_case)]


def seed_rules() -> list[dict]:
    return [
        {"id": "seed_a", "mechanism": "Read post-intervention coordinate a.",
         "readout": {"var": "a"}},
        {"id": "seed_b", "mechanism": "Read post-intervention coordinate b.",
         "readout": {"var": "b"}},
    ]
