from __future__ import annotations

import hashlib
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path


HASH_CHUNK_BYTES = 4 * 1024 * 1024
_HASH_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wdywfm-hash")


class HashCancelled(RuntimeError):
    pass


def sha256_file(path: str | Path, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            if cancel is not None and cancel.is_set():
                raise HashCancelled("Model hashing was cancelled.")
            chunk = handle.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def submit_sha256(
    path: str | Path, cancel: threading.Event | None = None,
) -> Future[str]:
    return _HASH_POOL.submit(sha256_file, path, cancel)


def file_fingerprint(path: str | Path, kind: str) -> tuple[str, int, int]:
    target = Path(path)
    stat = target.stat()
    normalized = target.name.casefold()
    return f"{kind}:{normalized}:{stat.st_size}:{stat.st_mtime_ns}", stat.st_size, stat.st_mtime_ns
