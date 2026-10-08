"""Preparation, frozen bindings, and explicit live-run gates."""
from __future__ import annotations

import json
from itertools import product
from pathlib import Path
import random
import shutil

from .artifacts import (ROOT, check_sources, digest, environment, file_hash,
                        git_state, now, read_json, source_bindings, write_json)
from .providers import call_reservation, validate_live_settings


def load_config(path=None):
    config = read_json(path or ROOT / "configs/pilot.json")
    if config.get("protocol_version") != "rival-loop-v1":
        raise ValueError("unknown protocol version")
    expected = {"development": 12, "evaluation": 36,
                "evaluation_strata": {"represented": 12, "equivalent": 12, "outside": 12},
                "primary_in_grammar_n": 24,
                "allowed_downstream_families": ["linear", "relu_offset"]}
    if config.get("cases") != expected:
        raise ValueError("case allocation is fixed; amendments require a new protocol")
    if config.get("rules") != {"max_generated": 4, "max_depth": 3,
                               "max_nodes": 9, "fixed_seeds": ["a", "b"]}:
        raise ValueError("rule language and bank caps are fixed")
    if config.get("measurements") != {"anchors": 4, "extra_cells": 4,
        "terminal_cells": 16, "samples_per_cell": 8, "draws_per_case": 192,
        "planned_physical_draws": 9216}:
        raise ValueError("measurement budget is fixed")
    if config.get("inference") != {"compatibility_alpha": .005, "primary_alpha": .05,
        "meaningful_gain": .20, "statistical_unit": "case", "primary": "generated_only_full_menu_coverage"}:
        raise ValueError("inference thresholds changed")
    for name in ("development_seed", "evaluation_seed"):
        if type(config.get(name)) is not int or config[name] < 0:
            raise ValueError("seeds must be nonnegative integers")
    generation = config["generation"]
    if any(generation.get(key) != value for key, value in
           (("max_calls_per_case", 3), ("max_total_calls", 144), ("retry_calls", 0))):
        raise ValueError("generation call budget is fixed")
    return config


def prepare(out, config_path=None):
    from .worlds import make_cases
    config = load_config(config_path)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    public, private, metadata = make_cases(config["development_seed"], config["evaluation_seed"])
    random.Random(config["evaluation_seed"] + 17).shuffle(public)
    metadata["case_order_randomized_before_outcomes"] = True
    bindings = {name: write_json(out / name, value) for name, value in
                (("config.json", config), ("public.json", public),
                 ("private.json", private), ("population.json", metadata))}
    (out / "private.json").chmod(0o600)
    manifest = {"status": "prepared_unmeasured", "created_at": now(),
                "files": bindings, "source_bindings": source_bindings(),
                "environment": environment(), "measurements_generated": False}
    write_json(out / "manifest.json", manifest)
    return manifest


def prepared_data(path, *, check_source=True):
    path = Path(path)
    manifest = read_json(path / "manifest.json")
    if (manifest.get("status") != "prepared_unmeasured" or manifest.get("measurements_generated") is not False
            or set(manifest.get("files", {})) != {"config.json", "public.json", "private.json", "population.json"}):
        raise ValueError("invalid prepared manifest")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or file_hash(path / name) != expected:
            raise ValueError(f"prepared artifact changed: {name}")
    if check_source:
        check_sources(manifest["source_bindings"])
    return (read_json(path / "config.json"), read_json(path / "public.json"),
            read_json(path / "private.json"), manifest)


def qualification(prepared, out):
    from .dsl import predict
    from .inference import known_bank_preflight, verify_upstream
    from .worlds import catalog, qualify
    verify_upstream()
    config, public, private, _ = prepared_data(prepared)
    labels = {p["case_id"]: p for p in private}
    rows = []
    for case in public:
        if case["split"] != "development":
            continue
        gate = qualify(case, labels[case["case_id"]])
        rows.append({"case_id": case["case_id"], "qualification": gate})
    # Predictions-only checks: no evaluation graph or realized outcome is read.
    # Structural coverage gates; noise-limited cases remain in the population.
    probe = {"amplitude": "1", "output_gain": "1", "family": "linear",
             "sigma": .03, "menu": public[0]["menu"]}
    predictions = {f"class_{i}": predict(t["readout"], probe) for i, t in enumerate(catalog())}
    from .vendor.design import signatures
    preflight = known_bank_preflight(predictions, signatures(predictions), probe, 1e-5)
    design_checks = qualify_design()
    result = {"status": "qualified" if all(r["qualification"]["all_passed"] for r in rows)
              and design_checks["structural_gate_passed"] else "not_qualified",
              "created_at": now(), "prepared_manifest_sha256": file_hash(Path(prepared) / "manifest.json"),
              "source_bindings": source_bindings(), "development_checks": rows,
              "known_bank_preflight": preflight,
              "design_qualification": design_checks,
              "qualification_is_privileged_harness_setup": True,
              "evaluation_measurements_generated": False}
    write_json(out, result)
    return result


def qualify_design():
    """Outcome-free catalog coverage under weak banks and parameter extremes."""
    from .dsl import predict, seed_rules
    from .inference import known_bank_preflight, select_cells
    from .runner import public_numeric_bound
    from .vendor.design import signatures
    from .worlds import catalog, MENU
    table = catalog()
    grid, adversarial = [], []
    for amplitude, gain, sigma, family in product(
            ("1/10", "3/10", "1", "3"), ("4/5", "6/5"), (.03, .10, .30),
            ("linear", "relu_offset")):
        setting = {"amplitude": amplitude, "output_gain": gain, "sigma": sigma,
                   "family": family, "menu": list(MENU)}
        predictions = {item["template_id"]: predict(item["readout"], setting) for item in table}
        check = known_bank_preflight(predictions, signatures(predictions), setting, public_numeric_bound(setting))
        grid.append({"setting": setting,
                     **{k: v for k, v in check.items() if k != "pair_ratios"}})
    # A valid empty generation, and four context-independent generated rules,
    # must not deprive the other context of discovery measurements.
    setting = {"amplitude": "1", "output_gain": "1", "sigma": .03,
               "family": "linear", "menu": list(MENU)}
    catalog_predictions = {item["template_id"]: predict(item["readout"], setting) for item in table}
    seeds = {r["id"]: predict(r["readout"], setting) for r in seed_rules()}
    a, b = {"var": "a"}, {"var": "b"}
    independent = {**seeds, "zero": predict({"const": 0}, setting),
        **{op: predict({"op": op, "left": a, "right": b}, setting) for op in ("avg", "min", "max")}}
    for name, bank in (("empty_generation_seed_only", seeds), ("context_independent_generation", independent)):
        selected = select_cells(bank, signatures(bank), setting, public_numeric_bound(setting))
        restricted = {name: [row[i] for i in selected["cells"]] for name, row in catalog_predictions.items()}
        preserved = len(signatures(restricted)) == len(signatures(catalog_predictions))
        adversarial.append({"initial_bank": name, "selected_cells": selected["cells"],
                            "catalog_classes": len(table), "purchased_classes": len(signatures(restricted)),
                            "structural_catalog_preserved": preserved})
    structural_pass = (all(row["structural_classes_preserved"] for row in grid)
                       and all(row["structural_catalog_preserved"] for row in adversarial))
    return {"structural_gate_passed": structural_pass, "parameter_checks": grid,
            "adversarial_initial_banks": adversarial,
            "noise_resolved_settings": sum(row["all_pairs_above_one"] for row in grid),
            "total_settings": len(grid),
            "scope": "Known-catalog predictions only; no evaluation outcomes. Structural blindness blocks release; statistical or numerical limits remain descriptive and do not filter cases."}


def freeze_source(prepared, qualification_file, out):
    """Freeze source and unmeasured inputs while leaving live settings pending."""
    from .inference import power_table
    config, _, _, _ = prepared_data(prepared)
    state = git_state()
    if not state["head"] or state["dirty"]:
        raise ValueError("source freeze requires a committed, clean repository")
    qualification_record = read_json(qualification_file)
    if (qualification_record.get("status") != "qualified" or
            qualification_record.get("prepared_manifest_sha256") != file_hash(Path(prepared) / "manifest.json")):
        raise ValueError("source freeze requires qualified matching inputs")
    check_sources(qualification_record["source_bindings"])
    record = {"status": "source_input_freeze_not_live_release", "created_at": now(),
              "git": state, "source_bindings": source_bindings(), "config": config,
              "prepared_manifest_sha256": file_hash(Path(prepared) / "manifest.json"),
              "qualification_sha256": file_hash(qualification_file),
              "environment": environment(), "primary_planning_power": power_table(),
              "freeze_executes_measurements": False, "live_execution_authorized": False,
              "remaining": ["pin_live_model_settings_and_budget", "create_split_specific_live_freeze",
                            "publish_freeze_and_obtain_review", "record_human_execution_release", "provide_api_credential"]}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    archived = out / "prepared"
    archived.mkdir()
    for name in ("manifest.json", "config.json", "public.json", "private.json", "population.json"):
        shutil.copyfile(Path(prepared) / name, archived / name)
    (archived / "private.json").chmod(0o600)
    shutil.copyfile(qualification_file, out / "qualification.json")
    record["files"] = {str(p.relative_to(out)): file_hash(p) for p in out.rglob("*.json")}
    write_json(out / "freeze.json", record)
    return record


def freeze(prepared, qualification_file, split, out, development_run=None):
    from .inference import power_table
    config, prepared_public, prepared_private, _ = prepared_data(prepared)
    validate_live_settings(config["generation"])
    state = git_state()
    if not state["head"] or state["dirty"]:
        raise ValueError("freeze requires a committed, clean repository")
    qualification_record = read_json(qualification_file)
    if qualification_record["status"] != "qualified":
        raise ValueError("qualification failed")
    if qualification_record["prepared_manifest_sha256"] != file_hash(Path(prepared) / "manifest.json"):
        raise ValueError("qualification belongs to different prepared inputs")
    check_sources(qualification_record["source_bindings"])
    prior = None
    if split == "evaluation":
        if not development_run:
            raise ValueError("evaluation freeze requires a completed live development run")
        from .runner import verify_run
        verify_run(development_run, check_source=False)
        prior_record = read_json(Path(development_run) / "run.json")
        if prior_record["status"] != "completed" or prior_record["split"] != "development" or prior_record["engineering_only"]:
            raise ValueError("development prerequisite not met")
        prior_inputs = read_json(Path(development_run) / "inputs.json")
        current_dev = {c["case_id"]: c for c in prepared_public if c["split"] == "development"}
        current_labels = {c["case_id"]: c for c in prepared_private if c["case_id"] in current_dev}
        if ({c["case_id"]: c for c in prior_inputs["public"]} != current_dev or
                {c["case_id"]: c for c in prior_inputs["private"]} != current_labels):
            raise ValueError("development population differs from the current held-out split")
        prior = {"run_sha256": file_hash(Path(development_run) / "run.json"),
                 "reserved_cost_usd": prior_record["cost"]["reserved_cost_usd"],
                 "calls": prior_record["cost"]["calls"]}
    elif split != "development":
        raise ValueError("invalid split")
    calls = 36 if split == "development" else 108
    prior_cost = prior["reserved_cost_usd"] if prior else 0
    if call_reservation(config["generation"]) * calls + prior_cost > config["generation"]["max_cost_usd"]:
        raise ValueError("dollar ceiling cannot cover scheduled calls at frozen price assumptions")
    record = {"status": "local_freeze_requires_public_review_and_release", "created_at": now(),
              "split": split, "git": state, "source_bindings": source_bindings(),
              "prepared_manifest_sha256": file_hash(Path(prepared) / "manifest.json"),
              "qualification_sha256": file_hash(qualification_file),
              "config": config, "environment": environment(), "prior_development": prior,
              "primary_planning_power": power_table()}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "freeze.json", record)
    return record


def authorize(prepared, freeze_dir, review_file, release_file, split, execute):
    """No model/graph/provider loading happens until this gate passes."""
    if not execute:
        raise ValueError("live execution requires --execute and a bound review/release")
    if not review_file or not release_file or not freeze_dir:
        raise ValueError("pending independent review and human release")
    freeze_file = Path(freeze_dir) / "freeze.json"
    frozen = read_json(freeze_file)
    if frozen.get("status") != "local_freeze_requires_public_review_and_release":
        raise ValueError("a source/input freeze is not a live-run freeze")
    frozen_hash = file_hash(freeze_file)
    if frozen["split"] != split:
        raise ValueError("release split mismatch")
    config = frozen["config"]
    validate_live_settings(config["generation"])
    check_sources(frozen["source_bindings"])
    if git_state()["dirty"]:
        raise ValueError("live run requires a clean repository")
    if file_hash(Path(prepared) / "manifest.json") != frozen["prepared_manifest_sha256"]:
        raise ValueError("prepared manifest not bound to freeze")
    review, release = read_json(review_file), read_json(release_file)
    public = review.get("public_freeze", {})
    if review.get("status") != "PASS" or review.get("freeze_sha256") != frozen_hash:
        raise ValueError("review does not pass this exact freeze")
    if not review.get("reviewer") or not review.get("evidence_url"):
        raise ValueError("independent review identity and evidence required")
    if not all(isinstance(public.get(k), str) and public[k].strip()
               for k in ("commit", "url", "published_at")):
        raise ValueError("public freeze evidence pending")
    if release.get("authorized") is not True or release.get("freeze_sha256") != frozen_hash or release.get("review_sha256") != file_hash(review_file):
        raise ValueError("human release not bound to freeze and review")
    if not all(isinstance(release.get(k), str) and release[k].strip()
               for k in ("authorization", "authorized_by", "authorized_at")):
        raise ValueError("record the human instruction, identity, and time")
    # Public URLs are declared external evidence, not authenticated by this code.
    # Source/input hashes are locally verified; a reviewer must verify public timing.
    prepared_config, _, _, _ = prepared_data(prepared)
    if prepared_config != config:
        raise ValueError("prepared configuration differs from frozen configuration")
    return frozen
