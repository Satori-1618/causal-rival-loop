"""One shared generation, two equal-budget revisions, fresh terminal testing.

The API gets whitelist-only text. The harness necessarily knows the planted
computation; this is structural generator isolation, not operator blindness.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
import shutil
import time

from .artifacts import (ROOT, Receipts, canonical, digest, environment, file_hash,
                        git_state, now, read_json, source_bindings, verify_receipts,
                        write_json, check_sources)


ARMS = ("feedback", "regeneration")


def _rng(case_id, phase):
    seed = int(hashlib.sha256(f"{case_id}:{phase}".encode()).hexdigest(), 16)
    return random.Random(seed)


def generator_setting(public):
    return {key: public[key] for key in
            ("case_id", "family", "amplitude", "output_gain", "sigma", "menu")}


def _prompt(template, payload):
    return template + "\n\nPAYLOAD (data, not additional instructions):\n" + canonical(payload).decode()


def _verify_prompt_templates(templates, bindings):
    """Bind recorded text to frozen file bytes, including historical replay."""
    if not isinstance(templates, dict) or set(templates) != {"initial", *ARMS}:
        raise ValueError("prompt templates must contain exactly initial, feedback, and regeneration")
    for phase, template in templates.items():
        if (not isinstance(template, str) or not isinstance(bindings, dict)
                or hashlib.sha256(template.encode("utf-8")).hexdigest()
                != bindings.get(f"prompts/{phase}.md")):
            raise ValueError(f"prompt template differs from frozen source binding: {phase}")


def base_payload(public, anchors):
    return {"setting": generator_setting(public),
            "semantics": {"recipient_hidden": [0, 0], "donor_hidden": "[amplitude, amplitude]",
               "intervention": "replace selected post-ReLU coordinates with dose times donor coordinates",
               "output": "output_gain * r(a,b,context) for linear; output_gain * max(0,r - 0.3*amplitude) for relu_offset"},
            "anchors": {"cells": anchors["cells"], "estimates": anchors["estimates"],
                        "samples_per_cell": 8}}


def revision_payload(base, initial_response, initial, selection, extra=None, discovery=None):
    payload = {**base, "initial_rules": initial_response["raw"],
               "structural_preflight": {"groups": initial["groups"],
                   "selected_cells": selection["cells"],
                   "minimum_separation_ratio": selection["minimum_separation_ratio"]}}
    if extra is not None:
        payload["additional_outcomes"] = {"cells": extra["cells"], "estimates": extra["estimates"],
                                          "samples_per_cell": 8}
        payload["compatibility"] = discovery
    return payload


def public_numeric_bound(public):
    """Public finite-benchmark allowance, checked against each executed graph.

    Never expose a truth-dependent FP32 fingerprint through the selector score.
    This is a conservative engineering envelope for this bounded grammar,
    validated per graph, not a universal floating-point theorem.
    """
    return 64 * 2**-23 * max(1.0, 3 * float(Fraction(public["amplitude"]))
                            * float(Fraction(public["output_gain"])))


class Measurements:
    def __init__(self, public, private):
        self.public, self._private = public, private
        self.phase = "anchors"

    def collect(self, phase, indices, final_bank_hashes=None):
        from .worlds import MENU, execute
        if phase != self.phase:
            raise ValueError("measurement phase out of order")
        if (len(set(indices)) != len(indices) or any(type(i) is not int or not 0 <= i < 16 for i in indices)):
            raise ValueError("invalid measurement cells")
        if phase == "anchors" and indices != list(range(4)):
            raise ValueError("four fixed anchors required")
        if phase == "extra" and (len(indices) != 4 or any(i < 4 for i in indices)):
            raise ValueError("exactly four nonanchor conditions required")
        if phase == "terminal" and (indices != list(range(16)) or not final_bank_hashes or set(final_bank_hashes) != set(ARMS)):
            raise ValueError("both final banks must be sealed before terminal observations")
        true_outputs = execute(self.public, self._private, cells=[MENU[i] for i in indices])
        rng = _rng(self.public["case_id"], "measurement:" + phase)
        draws = [[y + rng.gauss(0, self.public["sigma"]) for _ in range(8)] for y in true_outputs]
        self.phase = {"anchors": "extra", "extra": "terminal", "terminal": "closed"}[phase]
        return {"phase": phase, "cells": indices, "samples_per_cell": 8,
                "draws": draws, "estimates": [sum(row) / 8 for row in draws],
                "artificial_noise": "independent Gaussian, disclosed known sigma",
                "measurement_graph_forwards": len(indices),
                "physical_draws": len(indices) * 8}


def _bank(response, public, stage):
    from .dsl import parse_response, seed_rules, predict, signature
    from .worlds import qualify
    generated, error = [], None
    if response["status"] == "ok":
        try:
            generated = parse_response(response["raw"])
        except ValueError as exception:
            error = str(exception)
    else:
        error = response["status"]
    rules = {"seed:" + rule["id"]: {**rule, "origin": "seed", "introduced_at": stage}
             for rule in seed_rules()}
    for rule in generated:
        # Generated IDs can never override a mandatory seed or another stage.
        rules[f"generated:{stage}:{rule['id']}"] = {
            **rule, "origin": "generated", "introduced_at": stage,
            "rule_sha256": digest(rule["readout"])}
    predictions, exact, checks = {}, {}, {}
    for name, rule in rules.items():
        gate = qualify(public, {"case_id": public["case_id"], "truth_kind": "represented",
                                "truth_ast": rule["readout"]})
        if not gate["all_passed"]:
            raise ValueError("candidate numerical qualification failed")
        if gate["numeric_bound"] > public_numeric_bound(public):
            raise ValueError("candidate exceeds declared public numerical allowance")
        checks[name] = gate
        exact[name] = list(signature(rule["readout"], public))
        predictions[name] = predict(rule["readout"], public)
    grouped = {}
    for name in sorted(rules):
        grouped.setdefault(tuple(exact[name]), []).append(name)
    return {"stage": stage, "rules": rules, "predictions": predictions,
            "exact_signatures": exact, "groups": sorted(grouped.values()),
            "numeric_bound": max(check["numeric_bound"] for check in checks.values()),
            "qualification_graph_forwards": sum(check["qualification_graph_forward_count"] for check in checks.values()),
            "qualification": checks, "generation_failure": error,
            "valid_generated_count": len(generated)}


def _classify(bank, cells, estimates, radius):
    from .inference import classify_bank
    result = classify_bank({name: [row[i] for i in cells] for name, row in bank["predictions"].items()},
                           bank["groups"], estimates, [radius[i] for i in cells])
    return json.loads(canonical(result))  # JSON boundary: tuple residuals become lists.


def score_case(public, private, initial, banks, decisions):
    from .worlds import reference_signature
    truth = list(reference_signature(public, private))
    def covered(bank):
        return any(bank["exact_signatures"][name] == truth for name, rule in bank["rules"].items()
                   if rule["origin"] == "generated")
    arms = {}
    for arm in ARMS:
        bank, decision = banks[arm], decisions[arm]
        true_names = {name for name, row in bank["exact_signatures"].items() if row == truth}
        retained = set(decision["retained"])
        correct = decision["outcome"] == "resolved" and bool(true_names) and retained == true_names
        generated_errors = [sum(abs(float(Fraction(v)) - float(Fraction(t))) for v, t in zip(row, truth)) / 16
                            for name, row in bank["exact_signatures"].items()
                            if bank["rules"][name]["origin"] == "generated"]
        arms[arm] = {"generated_coverage": covered(bank), "outcome": decision["outcome"],
                     "correct_resolution": correct,
                     "false_resolution": decision["outcome"] == "resolved" and not correct,
                     "truth_excluded_when_covered": covered(bank) and not bool(true_names & retained),
                     "truth_absent_bank_relative_survivor": not true_names and bool(retained),
                     "valid_generated_count": bank["valid_generated_count"],
                     "generated_class_count": len({tuple(row) for name, row in bank["exact_signatures"].items()
                                                   if bank["rules"][name]["origin"] == "generated"}),
                     "retained": sorted(retained), "no_fit": decision["outcome"] == "no_candidate_fits",
                     "call_status": "valid" if bank["generation_failure"] is None else "failed",
                     "prediction_error": min(generated_errors) if generated_errors else None}
    return {"case_id": public["case_id"], "independent_unit": public["independent_unit"],
            "split": public["split"], "stratum": public["stratum"],
            "truth_class_id": private.get("template_id", "external_gain_a"),
            "setting": {key: public[key] for key in ("amplitude", "output_gain", "sigma", "family")},
            "initial_coverage": covered(initial), "arms": arms}


def run_cases(publics, privates, out, provider, settings, *, engineering_only,
              split, config, prepared_path=None, release_bindings=None, authorization_files=None):
    from .inference import radii, select_cells, verify_upstream
    from .worlds import qualify
    verify_upstream()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    if authorization_files:
        (out / "provenance").mkdir()
        for name, original in authorization_files.items():
            shutil.copyfile(original, out / "provenance" / f"{name}.json")
    if not engineering_only:
        if not prepared_path or not authorization_files:
            raise ValueError("live runs must archive the complete frozen population and authorization")
        archived = out / "provenance" / "prepared"
        archived.mkdir()
        for name in ("manifest.json", "config.json", "public.json", "private.json", "population.json"):
            shutil.copyfile(Path(prepared_path) / name, archived / name)
        (archived / "private.json").chmod(0o600)
    templates = {name: (ROOT / "prompts" / f"{name}.md").read_bytes().decode("utf-8")
                 for name in ("initial", *ARMS)}
    inputs = {"public": publics, "private": privates}
    labels = {record["case_id"]: record for record in privates}
    if len(labels) != len(privates) or set(labels) != {case["case_id"] for case in publics}:
        raise ValueError("case manifest must contain matching unique IDs")
    header = {"created_at": now(), "engineering_only": engineering_only, "split": split,
              "case_order": [case["case_id"] for case in publics],
              "source_bindings": source_bindings(), "environment": environment(),
              "git": git_state(), "templates": templates, "config": config,
              "release_bindings": release_bindings, "provider": provider.model}
    _verify_prompt_templates(header["templates"], header["source_bindings"])
    write_json(out / "header.json", header)
    write_json(out / "inputs.json", inputs)
    (out / "inputs.json").chmod(0o600)
    records, call_count, transport_failures, reserved, recorded_cost = [], 0, 0, 0.0, 0.0
    all_draws, all_forwards, setup_forwards = 0, 0, 0
    started = time.monotonic()
    status, failure = "completed", None
    prior_cost = float((release_bindings or {}).get("prior_reserved_cost_usd", 0))
    def call(receipts, phase, payload, parents):
        nonlocal call_count, transport_failures, reserved, recorded_cost
        from .providers import call_reservation
        if call_count >= 3 * len(publics):
            raise ValueError("generation call budget exhausted")
        if not engineering_only and time.monotonic() - started > settings["run_timeout_seconds"]:
            raise ValueError("run time ceiling reached")
        reserve = 0.0 if engineering_only else call_reservation(settings)
        if not engineering_only and prior_cost + reserved + reserve > settings["max_cost_usd"]:
            raise ValueError("reserved dollar ceiling reached")
        prompt = _prompt(templates[phase], payload)
        call_count += 1
        reserved += reserve
        attempt = receipts.add("call_attempt", {"phase": phase, "prompt": prompt, "payload": payload,
            "prompt_sha256": digest(prompt), "call_index": call_count,
            "model": provider.model, "cost_reserved_usd": reserve,
            "settings": settings}, parents)
        try:
            response = provider.generate(prompt, settings)
        except Exception as error:
            receipts.add("call_fatal", {"phase": phase, "reason": type(error).__name__,
                         "message": str(error), "api_response": getattr(error, "response", None),
                         "cost_reserved_usd": reserve}, [attempt])
            raise
        if response["cost_usd"] is not None:
            recorded_cost += response["cost_usd"]
        result = receipts.add("call_result", {"phase": phase, "response": response}, [attempt])
        if response["status"] == "transport_failure":
            transport_failures += 1
            if transport_failures > 3:
                raise ValueError("more than three transport failures; run incomplete")
        return response, result
    active = None
    try:
        for public in publics:
            private = labels[public["case_id"]]
            active = Receipts(out / "cases" / public["case_id"])
            truth_gate = qualify(public, private)
            setup_forwards += truth_gate["qualification_graph_forward_count"]
            gate_hash = active.add("truth_qualification", truth_gate)
            if not truth_gate["all_passed"]:
                raise ValueError("truth graph qualification failed")
            if truth_gate["numeric_bound"] > public_numeric_bound(public):
                raise ValueError("truth exceeds declared public numerical allowance")
            measurements = Measurements(public, private)
            anchors = measurements.collect("anchors", list(range(4)))
            all_draws += anchors["physical_draws"]
            all_forwards += anchors["measurement_graph_forwards"]
            anchor_hash = active.add("anchors", anchors, [gate_hash])
            base = base_payload(public, anchors)
            response, response_hash = call(active, "initial", base, [anchor_hash])
            initial = _bank(response, public, "initial")
            initial_hash = active.add("initial_bank", initial, [response_hash])
            setup_forwards += initial["qualification_graph_forwards"]
            bound = public_numeric_bound(public)
            selection = select_cells(initial["predictions"], initial["groups"], public, bound)
            if selection["status"] != "selected":
                raise ValueError("seed bank lacks discriminating rivals")
            plan_hash = active.add("selection", selection, [initial_hash])
            extra = measurements.collect("extra", selection["extras"])
            all_draws += extra["physical_draws"]
            all_forwards += extra["measurement_graph_forwards"]
            extra_hash = active.add("extra", extra, [plan_hash])
            discovery = _classify(initial, selection["cells"], anchors["estimates"] + extra["estimates"],
                                  radii(public, bound))
            discovery_hash = active.add("discovery_decision", discovery, [extra_hash, initial_hash])
            order = list(ARMS)
            _rng(public["case_id"], "revision-order").shuffle(order)
            active.add("revision_schedule", {"order": order}, [plan_hash])
            banks, bank_hashes = {}, {}
            for arm in order:
                payload = revision_payload(base, response, initial, selection)
                parents = [initial_hash, plan_hash]
                if arm == "feedback":
                    payload = revision_payload(base, response, initial, selection, extra, discovery)
                    parents.append(discovery_hash)
                revised, revised_hash = call(active, arm, payload, parents)
                bank = _bank(revised, public, arm)
                # Parentage survives even when descriptions/IDs are reused.
                bank["parent_bank_sha256"] = initial_hash
                banks[arm] = bank
                setup_forwards += bank["qualification_graph_forwards"]
                bank_hashes[arm] = active.add("final_bank", {"arm": arm, "bank": bank}, [revised_hash, initial_hash])
            terminal = measurements.collect("terminal", list(range(16)), bank_hashes)
            all_draws += terminal["physical_draws"]
            all_forwards += terminal["measurement_graph_forwards"]
            terminal_hash = active.add("terminal", terminal, list(bank_hashes.values()))
            bound = public_numeric_bound(public)
            radius = radii(public, bound)
            decisions = {}
            for arm in ARMS:
                decisions[arm] = _classify(banks[arm], list(range(16)), terminal["estimates"], radius)
                active.add("terminal_decision", {"arm": arm, "decision": decisions[arm],
                           "common_radius": radius}, [terminal_hash, bank_hashes[arm]])
            diagnostics = diagnostic_controls(public, anchors, terminal, radius)
            active.add("diagnostics", diagnostics, [terminal_hash, anchor_hash])
            record = score_case(public, private, initial, banks, decisions)
            record["preflight_minimum_separation_ratio"] = selection["minimum_separation_ratio"]
            record["cost"] = _record_cost(truth_gate, initial, banks)
            active.add("score", record, [terminal_hash, *bank_hashes.values()])
            active.seal()
            active = None
            records.append(record)
    except Exception as error:
        status, failure = "incomplete", {"type": type(error).__name__, "message": str(error)}
        if active is not None:
            active.add("technical_failure", failure)
            active.seal()
    from .inference import analyze
    summary = ({"status": "engineering_smoke_no_empirical_claim", "completed_cases": len(records)}
               if engineering_only else analyze(records, split=split))
    record_hash = write_json(out / "records.json", records)
    summary_hash = write_json(out / "summary.json", summary)
    seal_files = {str(path.relative_to(out)): file_hash(path) for path in out.rglob("*.json")}
    manifest = {"status": status, "failure": failure, "split": split,
                "engineering_only": engineering_only, "created_at": now(),
                "source_bindings": header["source_bindings"], "files": seal_files,
                "records_sha256": record_hash, "summary_sha256": summary_hash,
                "cost": {"calls": call_count, "recorded_cost_usd": recorded_cost,
                         "reserved_cost_usd": reserved, "prior_reserved_cost_usd": prior_cost,
                         "physical_draws": all_draws, "measurement_graph_forwards": all_forwards,
                         "qualification_graph_forwards": setup_forwards},
                "planned_cases": len(publics), "completed_cases": len(records)}
    write_json(out / "run.json", manifest)
    return manifest


def diagnostic_controls(public, anchors, terminal, radius):
    # Anchor predictions use independent earlier observations, never the tested
    # terminal observation itself. Account conservatively for anchor uncertainty.
    from .inference import radii
    anchor_radius = radii(public, 0.0)
    rows = {}
    for name, anchor_offset in (("preserve_recipient_output", 0), ("copy_full_donor_output", 1)):
        predictions, residuals, fits = [], [], []
        for cell, estimate, width in zip(public["menu"], terminal["estimates"], radius):
            context = int(cell.split(":")[1][1:])
            index = 2 * context + anchor_offset
            predicted = anchors["estimates"][index]
            predictions.append(predicted)
            residuals.append(estimate - predicted)
            fits.append(abs(estimate - predicted) <= width + anchor_radius[index])
        rows[name] = {"prediction": predictions, "residual": residuals,
                      "fits_all_cells": all(fits), "source": "independent discovery anchor"}
    rows["fixed_zero_default"] = {"prediction": [0.0] * 16,
        "fits_all_cells": all(abs(y) <= r for y, r in zip(terminal["estimates"], radius)),
        "source": "fixed reference, not an internal no-effect claim"}
    return {"reference_functions": rows, "affects_main_bank": False,
            "scope": "Descriptive diagnostics; anchor and terminal intervals each have alpha=.005"}


def smoke(out, cases=4):
    from .governance import load_config
    from .providers import FakeProvider
    from .worlds import make_cases
    if not 1 <= cases <= 12:
        raise ValueError("smoke accepts 1..12 fixture cases")
    public, private, _ = make_cases(990001, 990002)
    public = [row for row in public if row["split"] == "development"][:cases]
    chosen = {row["case_id"] for row in public}
    private = [row for row in private if row["case_id"] in chosen]
    config = load_config()
    return run_cases(public, private, out, FakeProvider(), {}, engineering_only=True,
                     split="smoke", config=config)


def execute_live(prepared, freeze_dir, review, release, split, out, execute):
    from .governance import authorize, prepared_data
    from .providers import OpenAIProvider
    frozen = authorize(prepared, freeze_dir, review, release, split, execute)
    config, publics, privates, _ = prepared_data(prepared)
    selected = [row for row in publics if row["split"] == split]
    ids = {row["case_id"] for row in selected}
    private = [row for row in privates if row["case_id"] in ids]
    bindings = {"freeze_sha256": file_hash(Path(freeze_dir) / "freeze.json"),
                "review_sha256": file_hash(review), "release_sha256": file_hash(release),
                "prior_reserved_cost_usd": float((frozen.get("prior_development") or {}).get("reserved_cost_usd", 0))}
    if Path(out).exists():
        raise ValueError("output directory already exists")
    provider = OpenAIProvider(config["generation"])
    # Local create-only protection: copying/deleting the checkout can bypass it;
    # public execution history remains an independent-review responsibility.
    write_json(Path(freeze_dir) / "execution-claim.json", {
        "freeze_sha256": bindings["freeze_sha256"], "release_sha256": bindings["release_sha256"],
        "claimed_at": now(), "output": str(Path(out).resolve())})
    return run_cases(selected, private, out, provider, config["generation"],
                     engineering_only=False, split=split, config=config,
                     prepared_path=prepared, release_bindings=bindings,
                     authorization_files={"freeze": Path(freeze_dir) / "freeze.json",
                                          "review": review, "release": release})


def _record_cost(gate, initial, banks):
    return {"calls": 3, "physical_draws": 192, "logical_draws_per_arm": 192,
            "measurement_graph_forwards": 24,
            "qualification_graph_forwards": gate["qualification_graph_forward_count"]
               + initial["qualification_graph_forwards"]
               + sum(bank["qualification_graph_forwards"] for bank in banks.values())}


def _verify_event_order(events, case_dir, public):
    """A failed trace must be a prefix of the same schedule, never a new path."""
    order = list(ARMS)
    _rng(public["case_id"], "revision-order").shuffle(order)
    initial = [("truth_qualification", None, []), ("anchors", None, [0]),
        ("call_attempt", "initial", [1]), ("call_result", "initial", [2]),
        ("initial_bank", None, [3]), ("selection", None, [4]),
        ("extra", None, [5]), ("discovery_decision", None, [6, 4]),
        ("revision_schedule", None, [5])]
    expected = list(initial)
    final_indices = {}
    for arm in order:
        index = len(expected)
        expected += [("call_attempt", arm, [4, 5] + ([7] if arm == "feedback" else [])),
                     ("call_result", arm, [index]), ("final_bank", arm, [index + 1, 4])]
        final_indices[arm] = index + 2
    terminal = len(expected)
    expected += [("terminal", None, [final_indices[a] for a in order]),
        ("terminal_decision", "feedback", [terminal, final_indices["feedback"]]),
        ("terminal_decision", "regeneration", [terminal, final_indices["regeneration"]]),
        ("diagnostics", None, [terminal, 1]),
        ("score", None, [terminal, *[final_indices[a] for a in order]])]
    hashes = [file_hash(case_dir / f"{e['sequence']:04d}-{e['kind']}.json") for e in events]
    failure = False
    for index, event in enumerate(events):
        kind = event["kind"]
        if kind == "technical_failure":
            if index != len(events) - 1 or event["parents"]:
                raise ValueError("technical failure must terminate the case")
            failure = True
            break
        if index >= len(expected):
            raise ValueError("unexpected extra event")
        expected_kind, phase, parents = expected[index]
        if kind == "call_fatal":
            if expected_kind != "call_result" or index != len(events) - 2:
                raise ValueError("fatal call is outside its attempt")
        elif kind != expected_kind:
            raise ValueError("case schedule changed")
        actual_phase = event["payload"].get("phase", event["payload"].get("arm"))
        if phase is not None and actual_phase != phase:
            raise ValueError("generation/arm schedule changed")
        if event["parents"] != [hashes[p] for p in parents]:
            raise ValueError("semantic receipt parentage changed")
    if not failure and len(events) != len(expected):
        raise ValueError("case trace is incomplete without a failure record")
    return failure


def verify_run(path, *, check_source=True):
    """Recompute candidate predictions, selected design, decisions, and scoring."""
    from .dsl import predict, signature
    from .inference import analyze, radii, select_cells, verify_upstream
    from .worlds import qualify
    verify_upstream()
    path = Path(path)
    manifest = read_json(path / "run.json")
    if check_source:
        check_sources(manifest["source_bindings"])
    expected = {"run.json", *manifest["files"]}
    actual = {str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()}
    if actual != expected:
        raise ValueError("unsealed or missing run artifacts")
    for name, sha in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts or file_hash(path / name) != sha:
            raise ValueError(f"artifact changed: {name}")
    header, inputs = read_json(path / "header.json"), read_json(path / "inputs.json")
    if header["source_bindings"] != manifest["source_bindings"] or header["engineering_only"] != manifest["engineering_only"] or header["split"] != manifest["split"]:
        raise ValueError("run header and manifest disagree")
    _verify_prompt_templates(header["templates"], header["source_bindings"])
    if header["case_order"] != [p["case_id"] for p in inputs["public"]]:
        raise ValueError("case order changed")
    if not header["engineering_only"]:
        frozen, review, release = (read_json(path / "provenance" / f"{name}.json")
                                  for name in ("freeze", "review", "release"))
        bindings = header["release_bindings"]
        for name in ("freeze", "review", "release"):
            if file_hash(path / "provenance" / f"{name}.json") != bindings[name + "_sha256"]:
                raise ValueError("authorization binding changed")
        if (frozen["source_bindings"] != header["source_bindings"] or frozen["config"] != header["config"]
                or frozen["split"] != header["split"] or review.get("status") != "PASS"
                or review.get("freeze_sha256") != bindings["freeze_sha256"]
                or release.get("authorized") is not True or release.get("freeze_sha256") != bindings["freeze_sha256"]
                or release.get("review_sha256") != bindings["review_sha256"]):
            raise ValueError("run was not bound to a passing review/release")
        from .governance import prepared_data, load_config
        from .providers import validate_live_settings
        archive = path / "provenance" / "prepared"
        if file_hash(archive / "manifest.json") != frozen["prepared_manifest_sha256"]:
            raise ValueError("archived population is not bound to the public freeze")
        prepared_config, prepared_public, prepared_private, prepared_manifest = prepared_data(archive, check_source=False)
        load_config(archive / "config.json")
        validate_live_settings(prepared_config["generation"])
        selected = [row for row in prepared_public if row["split"] == header["split"]]
        chosen = {row["case_id"] for row in selected}
        selected_private = [row for row in prepared_private if row["case_id"] in chosen]
        if (prepared_config != header["config"] or inputs != {"public": selected, "private": selected_private}
                or prepared_manifest["source_bindings"] != frozen["source_bindings"]
                or header["provider"] != prepared_config["generation"]["model_revision"]):
            raise ValueError("run inputs/configuration differ from the frozen population")
    from .providers import call_reservation
    labels = {row["case_id"]: row for row in inputs["private"]}
    ids = [row["case_id"] for row in inputs["public"]]
    if len(labels) != len(inputs["private"]) or len(set(ids)) != len(ids) or set(labels) != set(ids):
        raise ValueError("invalid case/input population")
    if manifest["planned_cases"] != len(ids):
        raise ValueError("planned case count changed")
    if manifest["status"] not in ("completed", "incomplete") or ((manifest["failure"] is None) != (manifest["status"] == "completed")):
        raise ValueError("inconsistent run status/failure")
    if (path / "cases").exists() and {p.name for p in (path / "cases").iterdir()} - set(ids):
        raise ValueError("undeclared case artifacts")
    settings = {} if header["engineering_only"] else header["config"]["generation"]
    expected_prior = (0.0 if header["engineering_only"] else float(
        (frozen.get("prior_development") or {}).get("reserved_cost_usd", 0)))
    if manifest["cost"]["prior_reserved_cost_usd"] != expected_prior:
        raise ValueError("prior cost binding changed")
    verified_records, complete_ids, calls = [], set(), 0
    consumed_draws, consumed_forwards, setup_forwards = 0, 0, 0
    reserved_cost, actual_cost = 0.0, 0.0
    ended = False
    for public in inputs["public"]:
        case_dir = path / "cases" / public["case_id"]
        if not case_dir.exists():
            ended = True
            continue
        if ended:
            raise ValueError("case execution resumed after a stop")
        events = verify_receipts(case_dir)
        failed = _verify_event_order(events, case_dir, public)
        ended = failed
        def optional(kind):
            rows = [e for e in events if e["kind"] == kind]
            if len(rows) > 1:
                raise ValueError(f"duplicate {kind}")
            return rows[0]["payload"] if rows else None
        def one(kind):
            value = optional(kind)
            if value is None:
                raise ValueError(f"missing {kind}")
            return value
        for event in events:
            payload = event["payload"]
            if event["kind"] in ("anchors", "extra", "terminal"):
                consumed_draws += payload["physical_draws"]
                consumed_forwards += payload["measurement_graph_forwards"]
            elif event["kind"] == "truth_qualification":
                setup_forwards += payload["qualification_graph_forward_count"]
            elif event["kind"] == "initial_bank":
                setup_forwards += payload["qualification_graph_forwards"]
            elif event["kind"] == "final_bank":
                setup_forwards += payload["bank"]["qualification_graph_forwards"]
            elif event["kind"] == "call_attempt":
                calls += 1
                reserve = 0.0 if header["engineering_only"] else call_reservation(settings)
                if (payload["call_index"] != calls or payload["model"] != header["provider"]
                        or payload["settings"] != settings or payload["cost_reserved_usd"] != reserve):
                    raise ValueError("generation settings/model/reservation changed")
                reserved_cost += reserve
            elif event["kind"] == "call_result":
                response = payload["response"]
                if response["model"] != header["provider"] or not isinstance(response["raw"], str):
                    raise ValueError("raw response model/type changed")
                if not header["engineering_only"]:
                    if response["provider"] != "openai_responses":
                        raise ValueError("provider changed")
                    usage = response["usage"]
                    if usage is not None:
                        if any(type(usage.get(k)) is not int or not 0 <= usage[k] <= settings["max_" + k]
                               for k in ("input_tokens", "output_tokens")):
                            raise ValueError("response usage exceeded frozen ceilings")
                        expected_cost = (usage["input_tokens"] * settings["input_usd_per_million"]
                            + usage["output_tokens"] * settings["output_usd_per_million"]) / 1_000_000
                        if response["cost_usd"] != expected_cost:
                            raise ValueError("recorded API cost does not reproduce")
                    elif response["status"] not in ("input_limit", "transport_failure"):
                        raise ValueError("API response missing usage")
                if response["cost_usd"] is not None:
                    actual_cost += response["cost_usd"]
        if failed and manifest["failure"] != one("technical_failure"):
            raise ValueError("technical failure does not match run manifest")
        gate = optional("truth_qualification")
        if gate is None:
            if not failed:
                raise ValueError("missing truth qualification")
            continue  # Qualification raised before it could produce a receipt.
        if gate != qualify(public, labels[public["case_id"]]):
            raise ValueError("truth qualification does not reproduce")
        measurement = Measurements(public, labels[public["case_id"]])
        anchors = optional("anchors")
        if anchors is not None and anchors != measurement.collect("anchors", list(range(4))):
            raise ValueError("anchor batch does not reproduce")
        responses = {e["payload"]["phase"]: e["payload"]["response"]
                     for e in events if e["kind"] == "call_result"}
        initial = optional("initial_bank")
        initial_hash, selection, extra, discovery = None, None, None, None
        if initial is not None:
            if initial != _bank(responses["initial"], public, "initial"):
                raise ValueError("initial bank was not produced by its raw generation")
            initial_event = next(e for e in events if e["kind"] == "initial_bank")
            initial_hash = file_hash(case_dir / f"{initial_event['sequence']:04d}-initial_bank.json")
        if optional("selection") is not None:
            selection = select_cells(initial["predictions"], initial["groups"], public, public_numeric_bound(public))
            if selection != one("selection"):
                raise ValueError("selection does not reproduce")
        if optional("extra") is not None:
            extra = measurement.collect("extra", selection["extras"])
            if extra != one("extra"):
                raise ValueError("extra batch does not reproduce")
        if optional("discovery_decision") is not None:
            discovery = _classify(initial, selection["cells"], anchors["estimates"] + extra["estimates"],
                                  radii(public, public_numeric_bound(public)))
            if discovery != one("discovery_decision"):
                raise ValueError("discovery decision does not reproduce")
        attempts = [e for e in events if e["kind"] == "call_attempt"]
        if attempts:
            base = base_payload(public, anchors)
            for attempt in attempts:
                payload = attempt["payload"]
                phase = payload["phase"]
                expected_payload = (base if phase == "initial" else revision_payload(base, responses["initial"],
                    initial, selection, extra if phase == "feedback" else None,
                    discovery if phase == "feedback" else None))
                if payload["payload"] != expected_payload:
                    raise ValueError("generator received unpermitted or changed evidence")
                if (payload["prompt"] != _prompt(header["templates"][phase], expected_payload)
                        or payload["prompt_sha256"] != digest(payload["prompt"])):
                    raise ValueError("prompt does not match recorded payload/template")
        expected_order = list(ARMS)
        _rng(public["case_id"], "revision-order").shuffle(expected_order)
        if optional("revision_schedule") is not None and one("revision_schedule")["order"] != expected_order:
            raise ValueError("revision-call order changed")
        banks = {}
        for event in events:
            if event["kind"] == "final_bank":
                arm, bank = event["payload"]["arm"], event["payload"]["bank"]
                rebuilt = _bank(responses[arm], public, arm)
                rebuilt["parent_bank_sha256"] = initial_hash
                if bank != rebuilt:
                    raise ValueError("final bank was not produced by its raw generation")
                banks[arm] = bank
        terminal = optional("terminal")
        decisions = {}
        common = radii(public, public_numeric_bound(public))
        if terminal is not None:
            if set(banks) != set(ARMS) or terminal != measurement.collect("terminal", list(range(16)), dict.fromkeys(ARMS, "verified")):
                raise ValueError("terminal batch does not reproduce")
            for arm in ARMS:
                decisions[arm] = _classify(banks[arm], list(range(16)), terminal["estimates"], common)
        for event in events:
            if event["kind"] == "terminal_decision":
                payload = event["payload"]
                if payload["decision"] != decisions[payload["arm"]] or payload["common_radius"] != common:
                    raise ValueError("terminal decision does not reproduce")
        if optional("diagnostics") is not None and one("diagnostics") != diagnostic_controls(public, anchors, terminal, common):
            raise ValueError("diagnostic controls do not reproduce")
        if failed:
            continue
        record = score_case(public, labels[public["case_id"]], initial, banks, decisions)
        record["preflight_minimum_separation_ratio"] = selection["minimum_separation_ratio"]
        record["cost"] = _record_cost(gate, initial, banks)
        saved = one("score")
        if record != saved:
            raise ValueError("truth score or case cost does not reproduce")
        verified_records.append(saved)
        complete_ids.add(public["case_id"])
    if verified_records != read_json(path / "records.json") or calls != manifest["cost"]["calls"]:
        raise ValueError("run accounting does not reproduce")
    cost = manifest["cost"]
    if (consumed_draws != cost["physical_draws"] or consumed_forwards != cost["measurement_graph_forwards"]
            or setup_forwards != cost["qualification_graph_forwards"]
            or reserved_cost != cost["reserved_cost_usd"] or actual_cost != cost["recorded_cost_usd"]):
        raise ValueError("consumed resources do not reproduce")
    if manifest["completed_cases"] != len(complete_ids):
        raise ValueError("completed-case accounting changed")
    expected_summary = ({"status": "engineering_smoke_no_empirical_claim", "completed_cases": len(verified_records)}
                        if manifest["engineering_only"] else analyze(verified_records, split=manifest["split"]))
    if expected_summary != read_json(path / "summary.json"):
        raise ValueError("summary does not reproduce")
    if manifest["status"] == "completed" and len(complete_ids) != len(inputs["public"]):
        raise ValueError("completed run is missing cases")
    return {"status": "verified", "engineering_only": manifest["engineering_only"],
            "completed_cases": len(complete_ids), "calls": calls,
            "scope": "Artifact integrity and deterministic replay; not proof of public timing"}
