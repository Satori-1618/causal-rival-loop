"""No network calls: exercise API payloads and the real local release path."""
import io
import json
import sys
from types import SimpleNamespace
import urllib.error

import pytest

from rival_loop import artifacts, governance, providers, runner


def configured_settings():
    settings = governance.load_config()["generation"].copy()
    settings.update(provider="openai_responses", model="fixture", model_revision="fixture-snapshot",
                    tokenizer_encoding="cl100k_base", max_input_tokens=10000, max_output_tokens=1024,
                    timeout_seconds=30, run_timeout_seconds=120, max_cost_usd=10,
                    input_usd_per_million=1, output_usd_per_million=2)
    return settings


@pytest.fixture
def mocked_provider(monkeypatch):
    encoding = SimpleNamespace(encode=lambda value: list(range(len(value))))
    monkeypatch.setitem(sys.modules, "tiktoken", SimpleNamespace(get_encoding=lambda _: encoding))
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key-never-recorded")
    return providers.OpenAIProvider(configured_settings())


def api_response(**changes):
    value = {"status": "completed", "model": "fixture-snapshot", "id": "response-fixture",
             "usage": {"input_tokens": 100, "output_tokens": 50},
             "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"rules":[]}' }]}]}
    return {**value, **changes}


def test_live_adapter_is_tool_free_stateless_and_never_sends_truth_or_key(mocked_provider, monkeypatch):
    requests = []
    def request(req, timeout):
        requests.append(json.loads(req.data))
        assert timeout == 30
        return io.BytesIO(json.dumps(api_response()).encode())
    monkeypatch.setattr(providers.urllib.request, "urlopen", request)
    for prompt in ("initial payload", "independent revision payload"):
        result = mocked_provider.generate(prompt, configured_settings())
        assert result["status"] == "ok" and result["cost_usd"] == .0002
    for request in requests:
        assert request["tools"] == [] and request["tool_choice"] == "none"
        assert request["store"] is False and request["model"] == "fixture-snapshot"
        assert "previous_response_id" not in request
        assert "fixture-key" not in json.dumps(request)
    assert requests[1]["input"] == "independent revision payload"


@pytest.mark.parametrize("changes", [{"model": "changed-model"}, {"usage": None},
                                      {"usage": {"input_tokens": 10001, "output_tokens": 1}}])
def test_api_validation_preserves_success_response(mocked_provider, monkeypatch, changes):
    response = api_response(**changes)
    monkeypatch.setattr(providers.urllib.request, "urlopen", lambda *_a, **_k: io.BytesIO(json.dumps(response).encode()))
    with pytest.raises(providers.FatalProviderError) as error:
        mocked_provider.generate("public payload", configured_settings())
    assert error.value.response == response


def test_timeout_does_not_retry_and_reserves_possible_cost(mocked_provider, monkeypatch):
    calls = []
    def timeout(*args, **kwargs):
        calls.append(1)
        raise urllib.error.URLError("fixture timeout")
    monkeypatch.setattr(providers.urllib.request, "urlopen", timeout)
    result = mocked_provider.generate("public payload", configured_settings())
    assert len(calls) == 1 and result["status"] == "transport_failure"
    assert result["cost_usd"] is None
    assert result["cost_reserved_usd"] == providers.call_reservation(configured_settings())


def test_input_limit_refuses_before_request(mocked_provider, monkeypatch):
    monkeypatch.setattr(providers.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("request exceeded local limit"))
    settings = configured_settings()
    settings["max_input_tokens"] = 150
    assert mocked_provider.generate("too long" * 100, settings)["status"] == "input_limit"


def released_fixture(tmp_path, monkeypatch):
    config = governance.load_config()
    config["generation"] = configured_settings()
    config_file = tmp_path / "config.json"
    artifacts.write_json(config_file, config)
    prepared = tmp_path / "prepared"
    governance.prepare(prepared, config_file)
    qualification = tmp_path / "qualification.json"
    assert governance.qualification(prepared, qualification)["status"] == "qualified"
    monkeypatch.setattr(governance, "git_state", lambda: {"head": "fixture-source-commit", "dirty": False})
    frozen_dir = tmp_path / "freeze"
    governance.freeze(prepared, qualification, "development", frozen_dir)
    freeze_hash = artifacts.file_hash(frozen_dir / "freeze.json")
    review = tmp_path / "review.json"
    artifacts.write_json(review, {"status": "PASS", "freeze_sha256": freeze_hash,
        "reviewer": "unit-test fixture; no human review claim", "evidence_url": "https://example.invalid/review",
        "public_freeze": {"commit": "fixture-public-commit", "url": "https://example.invalid/freeze",
                          "published_at": "fixture-time; no public timing claim"}})
    release = tmp_path / "release.json"
    artifacts.write_json(release, {"authorized": True, "freeze_sha256": freeze_hash,
        "review_sha256": artifacts.file_hash(review), "authorization": "unit-test-only simulation",
        "authorized_by": "fixture", "authorized_at": "fixture"})
    class FixtureProvider(providers.FakeProvider):
        model = "fixture-snapshot"
        def __init__(self, _):
            pass
        def generate(self, prompt, settings):
            result = super().generate(prompt, settings)
            result["provider"] = "openai_responses"
            result["cost_reserved_usd"] = providers.call_reservation(settings)
            return result
    monkeypatch.setattr(providers, "OpenAIProvider", FixtureProvider)
    return prepared, frozen_dir, review, release


def test_authorized_bundle_archives_population_and_refuses_second_execution(tmp_path, monkeypatch):
    prepared, frozen, review, release = released_fixture(tmp_path, monkeypatch)
    out = tmp_path / "run"
    result = runner.execute_live(prepared, frozen, review, release, "development", out, True)
    assert result["status"] == "completed" and result["cost"]["calls"] == 36
    assert runner.verify_run(out)["status"] == "verified"
    summary = artifacts.read_json(out / "summary.json")
    assert summary["status"] == "development_complete_descriptive"
    assert (out / "provenance/prepared/private.json").exists()
    with pytest.raises(FileExistsError):
        runner.execute_live(prepared, frozen, review, release, "development", tmp_path / "rerun", True)
    assert not (tmp_path / "rerun").exists()
    # Even updating all run-local hashes cannot change the population bound to the freeze.
    archived = out / "provenance/prepared"
    labels = artifacts.read_json(archived / "private.json")
    labels[0]["truth_ast"] = {"const": 0}
    (archived / "private.json").write_text(json.dumps(labels))
    manifest = artifacts.read_json(archived / "manifest.json")
    manifest["files"]["private.json"] = artifacts.file_hash(archived / "private.json")
    (archived / "manifest.json").write_text(json.dumps(manifest))
    run = artifacts.read_json(out / "run.json")
    for name in run["files"]:
        run["files"][name] = artifacts.file_hash(out / name)
    (out / "run.json").write_text(json.dumps(run))
    with pytest.raises(ValueError, match="public freeze"):
        runner.verify_run(out)


def test_fixed_inference_fields_cannot_be_relabelled(tmp_path):
    config = governance.load_config()
    config["inference"]["statistical_unit"] = "cell"
    path = tmp_path / "config.json"
    artifacts.write_json(path, config)
    with pytest.raises(ValueError, match="inference"):
        governance.load_config(path)
