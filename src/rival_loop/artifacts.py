"""Create-only JSON, stage receipts, and reproducible file bindings.

Hashes detect changes relative to a seal. They do not authenticate the operator
or establish public timing by themselves.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version


ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    def bad_constant(value):
        raise ValueError(f"non-finite JSON value: {value}")
    return json.loads(Path(path).read_text(), object_pairs_hook=_unique,
                      parse_constant=bad_constant)


def write_json(path, value):
    """Atomic publication without replacing a previous artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)  # Existing destination raises; never overwrite.
    finally:
        os.unlink(temporary)
    return file_hash(path)


def source_bindings():
    paths = []
    for directory in ("src", "tests", "prompts", "configs", "docs"):
        paths.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts
                     and not p.name.endswith(".pyc"))
    paths.extend(ROOT / p for p in ("README.md", "PROTOCOL.md", "schema.json",
                                    "pyproject.toml", "LICENSE", "requirements-lock.txt")
                 if (ROOT / p).is_file())
    return {str(p.relative_to(ROOT)): file_hash(p) for p in sorted(set(paths))}


def check_sources(bindings):
    if source_bindings() != bindings:
        raise ValueError("source bindings changed; create a new reviewed freeze")


def git_state():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    try:
        return {"head": git("rev-parse", "HEAD"),
                "dirty": bool(git("status", "--porcelain"))}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"head": None, "dirty": True}


def environment():
    packages = {}
    for package in ("numpy", "scipy", "torch"):
        try:
            packages[package] = version(package)
        except Exception:
            packages[package] = None
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": packages}


class Receipts:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.events = []

    def add(self, kind, payload, parents=()):
        entry = {"sequence": len(self.events), "kind": kind, "created_at": now(),
                 "parents": list(parents), "payload": payload}
        name = f"{len(self.events):04d}-{kind}.json"
        sha = write_json(self.root / name, entry)
        self.events.append({"file": name, "sha256": sha, "kind": kind})
        return sha

    def seal(self):
        return write_json(self.root / "seal.json", {"events": self.events})


def verify_receipts(root):
    root = Path(root)
    seal = read_json(root / "seal.json")
    known, events = set(), []
    expected = {"seal.json"}
    for index, entry in enumerate(seal["events"]):
        name = entry["file"]
        if Path(name).name != name or name in expected:
            raise ValueError("invalid receipt path")
        expected.add(name)
        if file_hash(root / name) != entry["sha256"]:
            raise ValueError(f"receipt changed: {name}")
        record = read_json(root / name)
        if record["sequence"] != index or record["kind"] != entry["kind"]:
            raise ValueError("receipt order changed")
        if any(parent not in known for parent in record["parents"]):
            raise ValueError("receipt refers to a future or unknown parent")
        known.add(entry["sha256"])
        events.append(record)
    if {p.name for p in root.iterdir()} != expected:
        raise ValueError("unsealed or missing receipts")
    return events
