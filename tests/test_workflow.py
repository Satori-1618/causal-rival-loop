import copy
import json
from pathlib import Path

import pytest

from rival_loop import artifacts, governance, runner
from rival_loop.providers import FakeProvider, FatalProviderError, validate_live_settings
from rival_loop.worlds import make_cases, reference_signature


@pytest.fixture
def fixture_case():
    public, private, _ = make_cases(990001, 990002)
    return public[0], private[0]


def test_smoke_roundtrip_and_visibility(tmp_path):
    out = tmp_path / "smoke"
    result = runner.smoke(out, 2)
    assert result["status"] == "completed"
    assert result["engineering_only"] is True
    assert result["cost"]["calls"] == 6
    assert result["cost"]["physical_draws"] == 384
    assert runner.verify_run(out)["completed_cases"] == 2
    for case in (out / "cases").iterdir():
        events = artifacts.verify_receipts(case)
        attempts = [e["payload"] for e in events if e["kind"] == "call_attempt"]
        assert len(attempts) == 3
        for attempt in attempts:
            payload = attempt["payload"]
            assert set(payload["setting"]) == {"case_id", "family", "amplitude", "output_gain", "sigma", "menu"}
            assert ("additional_outcomes" in payload) == (attempt["phase"] == "feedback")
        assert attempts[0]["phase"] == "initial"
        assert {a["phase"] for a in attempts[1:]} == {"feedback", "regeneration"}
        assert [e["kind"] for e in events].index("terminal") > max(i for i,e in enumerate(events) if e["kind"] == "final_bank")


def test_pending_run_refused_before_provider_or_graph(tmp_path, monkeypatch):
    import rival_loop.providers
    monkeypatch.setattr(rival_loop.providers, "OpenAIProvider", lambda *_: pytest.fail("provider loaded before release"))
    with pytest.raises(ValueError, match="review"):
        runner.execute_live(tmp_path, None, None, None, "evaluation", tmp_path / "run", True)
    assert not (tmp_path / "run").exists()


def test_prepare_has_no_observations_and_tamper_is_refused(tmp_path, monkeypatch):
    import rival_loop.worlds
    monkeypatch.setattr(rival_loop.worlds, "execute", lambda *_args, **_kwargs: pytest.fail("prepare executed a graph"))
    out = tmp_path / "prepared"
    assert governance.prepare(out)["measurements_generated"] is False
    _, public, private, _ = governance.prepared_data(out)
    assert len(public) == len(private) == 48
    assert all("predictions" not in case for case in public)
    with pytest.raises(FileExistsError):
        governance.prepare(out)
    (out / "private.json").write_text("[]")
    with pytest.raises(ValueError, match="changed"):
        governance.prepared_data(out)


def test_unconfigured_model_cannot_freeze(tmp_path):
    out = tmp_path / "prepared"
    governance.prepare(out)
    with pytest.raises(ValueError, match="provider"):
        governance.freeze(out, tmp_path / "not-read.json", "development", tmp_path / "freeze")


def test_generated_seed_id_cannot_override_seed(fixture_case):
    public, _ = fixture_case
    raw = json.dumps({"rules": [{"id": "seed_a", "mechanism": "An alias name is data.", "readout": {"const": 0}}]})
    bank = runner._bank({"status": "ok", "raw": raw}, public, "initial")
    assert bank["rules"]["seed:seed_a"]["readout"] == {"var": "a"}
    assert bank["rules"]["generated:initial:seed_a"]["readout"] == {"const": 0}


def test_invalid_generation_uses_no_repair_call(tmp_path, fixture_case):
    public, private = fixture_case
    class Invalid(FakeProvider):
        def generate(self, prompt, settings):
            response = super().generate(prompt, settings)
            response["raw"] = '{"rules":"AAA"}'
            return response
    result = runner.run_cases([public], [private], tmp_path / "run", Invalid(), {},
                              engineering_only=True, split="smoke", config=governance.load_config())
    assert result["status"] == "completed" and result["cost"]["calls"] == 3
    record = artifacts.read_json(tmp_path / "run/records.json")[0]
    assert all(not a["generated_coverage"] and a["valid_generated_count"] == 0
               for a in record["arms"].values())
    assert runner.verify_run(tmp_path / "run")["status"] == "verified"


def test_fatal_call_preserves_consumed_cost_and_measurements(tmp_path, fixture_case):
    public, private = fixture_case
    class FatalSecond(FakeProvider):
        count = 0
        def generate(self, prompt, settings):
            self.count += 1
            if self.count == 2:
                raise FatalProviderError("fixture mismatch", {"model": "wrong", "usage": None})
            return super().generate(prompt, settings)
    out = tmp_path / "run"
    result = runner.run_cases([public], [private], out, FatalSecond(), {},
                              engineering_only=True, split="smoke", config=governance.load_config())
    assert result["status"] == "incomplete"
    assert result["cost"]["calls"] == 2
    assert result["cost"]["physical_draws"] == 64
    assert result["cost"]["measurement_graph_forwards"] == 8
    events = artifacts.verify_receipts(out / "cases" / public["case_id"])
    fatal = next(e for e in events if e["kind"] == "call_fatal")
    assert fatal["payload"]["api_response"]["model"] == "wrong"
    assert runner.verify_run(out)["status"] == "verified"


def test_broker_blocks_future_or_unpurchased_measurements(fixture_case):
    public, private = fixture_case
    broker = runner.Measurements(public, private)
    with pytest.raises(ValueError, match="out of order"):
        broker.collect("terminal", list(range(16)), dict.fromkeys(runner.ARMS, "not-sealed"))
    broker.collect("anchors", list(range(4)))
    with pytest.raises(ValueError, match="nonanchor"):
        broker.collect("extra", [0, 4, 5, 6])
    broker.collect("extra", [4, 7, 10, 13])
    with pytest.raises(ValueError, match="both final"):
        broker.collect("terminal", list(range(16)), {"feedback": "only-one"})


def reseal_after_mutation(run, transform):
    """Adversarial fixture: consistent hashes must not substitute for replay."""
    case = next((run / "cases").iterdir())
    seal = artifacts.read_json(case / "seal.json")
    mapping = {}
    for entry in seal["events"]:
        path = case / entry["file"]
        event = artifacts.read_json(path)
        old = entry["sha256"]
        event["parents"] = [mapping.get(parent, parent) for parent in event["parents"]]
        transform(event)
        path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n")
        entry["sha256"] = artifacts.file_hash(path)
        mapping[old] = entry["sha256"]
    (case / "seal.json").write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n")
    manifest = artifacts.read_json(run / "run.json")
    manifest["files"] = {str(p.relative_to(run)): artifacts.file_hash(p)
                         for p in run.rglob("*.json") if p.name != "run.json"}
    (run / "run.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def test_rehashed_bank_not_from_raw_response_is_refused(tmp_path):
    out = tmp_path / "run"
    runner.smoke(out, 1)
    def mutate(event):
        if event["kind"] == "final_bank":
            for rule in event["payload"]["bank"]["rules"].values():
                if rule["origin"] == "generated":
                    rule["mechanism"] = "Fabricated after generation."
    reseal_after_mutation(out, mutate)
    with pytest.raises(ValueError, match="raw generation"):
        runner.verify_run(out)


def test_rehashed_hidden_truth_in_prompt_is_refused(tmp_path):
    out = tmp_path / "run"
    runner.smoke(out, 1)
    def mutate(event):
        if event["kind"] == "call_attempt" and event["payload"]["phase"] == "regeneration":
            payload = event["payload"]
            payload["payload"]["hidden_truth"] = {"var": "a"}
            template = artifacts.read_json(out / "header.json")["templates"]["regeneration"]
            payload["prompt"] = runner._prompt(template, payload["payload"])
            payload["prompt_sha256"] = artifacts.digest(payload["prompt"])
    reseal_after_mutation(out, mutate)
    with pytest.raises(ValueError, match="unpermitted"):
        runner.verify_run(out)


def test_no_fit_or_resolution_does_not_earn_truth_coverage(fixture_case):
    public, private = fixture_case
    bank = runner._bank(FakeProvider().generate("", {}), public, "initial")
    assert not any(sig == list(reference_signature(public, private))
                   for sig in bank["exact_signatures"].values())
    name = next(n for n in bank["rules"] if n.startswith("generated:"))
    decisions = dict.fromkeys(runner.ARMS, {"outcome": "resolved", "retained": [name]})
    record = runner.score_case(public, private, bank, dict.fromkeys(runner.ARMS, bank), decisions)
    assert all(not a["generated_coverage"] and a["false_resolution"] for a in record["arms"].values())


def test_secret_settings_refused():
    with pytest.raises(ValueError, match="credentials"):
        validate_live_settings({"api_key": "never-store-this"})


def test_failure_before_qualification_has_a_verifiable_empty_trace(tmp_path, fixture_case, monkeypatch):
    import rival_loop.worlds
    public, private = fixture_case
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("fixture graph unavailable")
    monkeypatch.setattr(rival_loop.worlds, "qualify", unavailable)
    out = tmp_path / "run"
    result = runner.run_cases([public], [private], out, FakeProvider(), {},
                             engineering_only=True, split="smoke", config=governance.load_config())
    assert result["status"] == "incomplete" and result["cost"]["calls"] == 0
    assert runner.verify_run(out)["completed_cases"] == 0
