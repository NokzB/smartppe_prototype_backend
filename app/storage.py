"""
JSON-file storage layer standing in for a database in this prototype.

Why this needs more than json.load/json.dump:
- FastAPI can serve requests concurrently (multiple threads/async tasks), so
  two requests could read-modify-write the same file at once and clobber
  each other's changes. We guard every read-modify-write cycle with a
  per-file threading.Lock.
- A crash mid-write must not corrupt the file. We write to a temp file and
  os.replace() it over the real one, which is atomic on POSIX and Windows.

This is still a prototype-grade solution: it works for one process on one
machine. See README for the migration path to SQLite/Postgres.
"""
import json
import os
import threading
from pathlib import Path
from typing import Any

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def ensure_file(path: Path, default: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _atomic_write(path, default)


def _atomic_write(path: Path, data: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp_path, path)


def read(path: Path) -> Any:
    lock = _lock_for(path)
    with lock:
        if not path.exists():
            return None
        with open(path, "r") as f:
            return json.load(f)


def write(path: Path, data: Any) -> None:
    lock = _lock_for(path)
    with lock:
        _atomic_write(path, data)


def update(path: Path, mutate_fn):
    """
    Read-modify-write under a single lock so no other request can slip in
    between the read and the write. `mutate_fn` receives the current data
    and must return the new data to persist.
    """
    lock = _lock_for(path)
    with lock:
        current = {}
        if path.exists():
            with open(path, "r") as f:
                current = json.load(f)
        new_data = mutate_fn(current)
        _atomic_write(path, new_data)
        return new_data
