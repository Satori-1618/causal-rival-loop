"""Source bindings cover reviewed inputs independently of installation state."""
import shutil

import pytest

from rival_loop import artifacts


SOURCE_FILES = {
    "src/rival_loop/example.py": "def example():\n    return 1\n",
    "tests/test_example.py": "def test_example():\n    assert True\n",
    "prompts/rival.txt": "Generate a rival explanation.\n",
    "configs/example.json": '{"seed": 1}\n',
    "docs/design.md": "Reviewed design.\n",
    "README.md": "Project overview.\n",
    "PROTOCOL.md": "Reviewed protocol.\n",
    "schema.json": '{"type": "object"}\n',
    "pyproject.toml": '[project]\nname = "example"\n',
    "LICENSE": "License terms.\n",
    "requirements-lock.txt": "pytest==8.0.0\n",
}


def write_file(root, name, contents):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    return path


@pytest.fixture
def source_root(tmp_path, monkeypatch):
    root = tmp_path / "source"
    for name, contents in SOURCE_FILES.items():
        write_file(root, name, contents)
    monkeypatch.setattr(artifacts, "ROOT", root)
    return root


@pytest.mark.parametrize("suffix", ["egg-info", "dist-info"])
def test_generated_metadata_additions_and_edits_do_not_change_bindings(source_root, suffix):
    bindings = artifacts.source_bindings()
    metadata = f"src/example.{suffix}"
    metadata_file = write_file(source_root, f"{metadata}/PKG-INFO", "version one\n")
    write_file(source_root, f"{metadata}/nested/RECORD", "installed files\n")

    assert artifacts.source_bindings() == bindings
    artifacts.check_sources(bindings)

    metadata_file.write_text("version two\n")
    write_file(source_root, f"{metadata}/entry_points.txt", "new entry point\n")
    assert artifacts.source_bindings() == bindings
    artifacts.check_sources(bindings)


@pytest.mark.parametrize("name", SOURCE_FILES)
def test_reviewed_source_and_input_edits_are_detected(source_root, name):
    bindings = artifacts.source_bindings()
    assert set(bindings) == set(SOURCE_FILES)
    (source_root / name).write_text(SOURCE_FILES[name] + "changed\n")

    changed = artifacts.source_bindings()
    assert changed[name] != bindings[name]
    assert {key for key in bindings if changed[key] != bindings[key]} == {name}
    with pytest.raises(ValueError, match="source bindings changed"):
        artifacts.check_sources(bindings)


def test_clean_export_and_installed_source_bind_the_same_surface(source_root, tmp_path, monkeypatch):
    # Only directories with metadata suffixes are excluded; reviewed files
    # with these suffixes are still part of the source surface.
    metadata_named_file = "docs/distribution.egg-info"
    write_file(source_root, metadata_named_file, "Reviewed packaging notes.\n")
    clean_bindings = artifacts.source_bindings()
    assert set(clean_bindings) == {*SOURCE_FILES, metadata_named_file}

    installed_root = tmp_path / "installed"
    shutil.copytree(source_root, installed_root)
    write_file(installed_root, "src/example.egg-info/PKG-INFO", "Generated metadata.\n")
    write_file(installed_root, "src/example-1.0.dist-info/METADATA", "Generated metadata.\n")
    write_file(installed_root, "src/rival_loop/__pycache__/example.cpython-311.pyc", "bytecode")
    write_file(installed_root, "src/rival_loop/example.pyc", "bytecode")
    monkeypatch.setattr(artifacts, "ROOT", installed_root)

    assert artifacts.source_bindings() == clean_bindings
    artifacts.check_sources(clean_bindings)
