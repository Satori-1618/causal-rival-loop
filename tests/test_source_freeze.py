"""Source/input checkpoints are reproducible snapshots, never live releases."""
import stat

import pytest

from rival_loop import artifacts, governance, worlds


def qualified_inputs(tmp_path):
    """Minimal qualification fixture for snapshot mechanics, not a QA claim."""
    prepared = tmp_path / "prepared"
    governance.prepare(prepared)
    qualification = tmp_path / "qualification.json"
    artifacts.write_json(qualification, {
        "status": "qualified",
        "prepared_manifest_sha256": artifacts.file_hash(prepared / "manifest.json"),
        "source_bindings": artifacts.source_bindings(),
        "fixture_only": True,
    })
    return prepared, qualification


def test_design_qualification_preserves_classes_without_measuring_outcomes(monkeypatch):
    monkeypatch.setattr(worlds, "execute", lambda *_a, **_k: pytest.fail("outcomes must not be measured"))
    result = governance.qualify_design()
    assert result["structural_gate_passed"] is True
    assert result["total_settings"] == len(result["parameter_checks"]) == 48
    assert all(row["structural_classes_preserved"] for row in result["parameter_checks"])
    assert all(row["purchased_cell_class_count"] == 59 for row in result["parameter_checks"])
    assert {row["resolution_status"] for row in result["parameter_checks"]} == {"resolved", "noise_limit"}
    assert {row["initial_bank"] for row in result["adversarial_initial_banks"]} == {
        "empty_generation_seed_only", "context_independent_generation"}
    assert all(row["structural_catalog_preserved"] and row["purchased_classes"] == 59
               for row in result["adversarial_initial_banks"])


def test_source_snapshot_archives_bound_inputs_and_leaves_live_settings_pending(tmp_path, monkeypatch):
    prepared, qualification = qualified_inputs(tmp_path)
    monkeypatch.setattr(governance, "git_state", lambda: {"head": "fixture-commit", "dirty": False})
    snapshot = tmp_path / "snapshot"
    result = governance.freeze_source(prepared, qualification, snapshot)
    assert result["status"] == "source_input_freeze_not_live_release"
    assert result["live_execution_authorized"] is False
    assert result["freeze_executes_measurements"] is False
    assert result["config"]["generation"]["model"] is None
    assert result["git"]["head"] == "fixture-commit"
    assert set(result["files"]) == {"qualification.json", *("prepared/" + name for name in (
        "manifest.json", "config.json", "public.json", "private.json", "population.json"))}
    for name, expected_hash in result["files"].items():
        assert artifacts.file_hash(snapshot / name) == expected_hash
    assert artifacts.file_hash(snapshot / "prepared/manifest.json") == result["prepared_manifest_sha256"]
    assert artifacts.file_hash(snapshot / "qualification.json") == result["qualification_sha256"]
    assert governance.prepared_data(snapshot / "prepared") == governance.prepared_data(prepared)
    assert stat.S_IMODE((snapshot / "prepared/private.json").stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        governance.freeze_source(prepared, qualification, snapshot)


@pytest.mark.parametrize("state", [{"head": None, "dirty": False}, {"head": "fixture", "dirty": True}])
def test_source_snapshot_requires_clean_committed_source(tmp_path, monkeypatch, state):
    prepared, qualification = qualified_inputs(tmp_path)
    monkeypatch.setattr(governance, "git_state", lambda: state)
    snapshot = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="committed, clean"):
        governance.freeze_source(prepared, qualification, snapshot)
    assert not snapshot.exists()


@pytest.mark.parametrize("change", ["not_qualified", "different_inputs", "changed_source"])
def test_source_snapshot_rejects_unbound_qualification(tmp_path, monkeypatch, change):
    prepared, qualification = qualified_inputs(tmp_path)
    monkeypatch.setattr(governance, "git_state", lambda: {"head": "fixture", "dirty": False})
    record = artifacts.read_json(qualification)
    if change == "not_qualified":
        record["status"] = "not_qualified"
    elif change == "different_inputs":
        record["prepared_manifest_sha256"] = "0" * 64
    else:
        record["source_bindings"]["PROTOCOL.md"] = "0" * 64
    qualification.write_bytes(artifacts.canonical(record))
    snapshot = tmp_path / "snapshot"
    with pytest.raises(ValueError):
        governance.freeze_source(prepared, qualification, snapshot)
    assert not snapshot.exists()


def test_source_snapshot_cannot_authorize_live_execution(tmp_path, monkeypatch):
    prepared, qualification = qualified_inputs(tmp_path)
    monkeypatch.setattr(governance, "git_state", lambda: {"head": "fixture", "dirty": False})
    snapshot = tmp_path / "snapshot"
    governance.freeze_source(prepared, qualification, snapshot)
    monkeypatch.setattr(governance, "validate_live_settings",
                        lambda *_a, **_k: pytest.fail("reject before live settings or provider"))
    with pytest.raises(ValueError, match="source/input freeze is not a live-run freeze"):
        governance.authorize(prepared, snapshot, tmp_path / "nonexistent-review.json",
                             tmp_path / "nonexistent-release.json", "development", True)
