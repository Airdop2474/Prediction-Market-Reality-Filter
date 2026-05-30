import json
import os
import tempfile
import threading
from contextlib import contextmanager
from typing import Any, Iterator


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: str) -> threading.RLock:
    normalized = os.path.abspath(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[normalized] = lock
        return lock


@contextmanager
def locked_file(path: str) -> Iterator[None]:
    lock = _lock_for(path)
    with lock:
        yield


def read_json(path: str, fallback: Any) -> Any:
    with locked_file(path):
        if not os.path.exists(path):
            return fallback
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return fallback


def write_json_atomic(path: str, data: Any, *, indent: int | None = 2) -> None:
    with locked_file(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        directory = os.path.dirname(path)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=directory,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=indent, ensure_ascii=False)
                handle.write("\n")
            os.replace(temp_path, path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
