from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_wdywfm.domain.models import ModelMetadata


SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60
NEGATIVE_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class CacheEntry:
    metadata: ModelMetadata
    fetched_at: float
    expires_at: float

    @property
    def stale(self) -> bool:
        return self.expires_at <= time.time()


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class SQLiteMetadataCache:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_cache_path()
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path), timeout=10, factory=_ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _migrate(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS local_models (
                    local_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    sha256 TEXT,
                    size INTEGER,
                    mtime_ns INTEGER,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata_snapshots (
                    local_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY(local_id) REFERENCES local_models(local_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS field_provenance (
                    local_id TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY(local_id, field_name),
                    FOREIGN KEY(local_id) REFERENCES local_models(local_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS fetch_state (
                    lookup_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    http_status INTEGER,
                    retry_after REAL,
                    updated_at REAL NOT NULL
                );
                """
            )
            db.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, time.time()),
            )

    def upsert_local_model(
        self,
        metadata: ModelMetadata,
        *,
        fingerprint: str,
        size: int | None = None,
        mtime_ns: int | None = None,
    ) -> None:
        with self._lock, self._connect() as db:
            previous = db.execute(
                "SELECT fingerprint FROM local_models WHERE local_id=?", (metadata.local_id,)
            ).fetchone()
            if previous is not None and previous["fingerprint"] != fingerprint:
                db.execute("DELETE FROM metadata_snapshots WHERE local_id=?", (metadata.local_id,))
                db.execute("DELETE FROM field_provenance WHERE local_id=?", (metadata.local_id,))
            db.execute(
                """INSERT INTO local_models
                   (local_id, kind, display_name, fingerprint, sha256, size, mtime_ns, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(local_id) DO UPDATE SET
                     kind=excluded.kind, display_name=excluded.display_name,
                     fingerprint=excluded.fingerprint,
                     sha256=COALESCE(excluded.sha256, local_models.sha256),
                     size=excluded.size, mtime_ns=excluded.mtime_ns, updated_at=excluded.updated_at""",
                (
                    metadata.local_id, metadata.kind, metadata.display_name, fingerprint,
                    metadata.sha256, size, mtime_ns, time.time(),
                ),
            )

    def stored_sha256(self, local_id: str, fingerprint: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT sha256 FROM local_models WHERE local_id=? AND fingerprint=?",
                (local_id, fingerprint),
            ).fetchone()
        return str(row["sha256"]) if row is not None and row["sha256"] else None

    def store_sha256(self, local_id: str, fingerprint: str, sha256: str) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE local_models SET sha256=?, updated_at=? WHERE local_id=? AND fingerprint=?",
                (sha256, time.time(), local_id, fingerprint),
            )

    def get_metadata(self, local_id: str) -> CacheEntry | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json, fetched_at, expires_at FROM metadata_snapshots WHERE local_id=?",
                (local_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["payload_json"])
            return CacheEntry(
                ModelMetadata.from_dict(value), float(row["fetched_at"]), float(row["expires_at"])
            )
        except (TypeError, ValueError, KeyError):
            self.delete_metadata(local_id)
            return None

    def put_metadata(self, metadata: ModelMetadata, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        now = time.time()
        payload = json.dumps(metadata.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO metadata_snapshots(local_id, payload_json, fetched_at, expires_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(local_id) DO UPDATE SET
                     payload_json=excluded.payload_json, fetched_at=excluded.fetched_at,
                     expires_at=excluded.expires_at""",
                (metadata.local_id, payload, now, now + max(60, int(ttl))),
            )
            db.execute("DELETE FROM field_provenance WHERE local_id=?", (metadata.local_id,))
            db.executemany(
                "INSERT INTO field_provenance(local_id, field_name, source) VALUES (?, ?, ?)",
                [(metadata.local_id, key, value) for key, value in metadata.provenance.items()],
            )

    def delete_metadata(self, local_id: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM metadata_snapshots WHERE local_id=?", (local_id,))

    def mark_not_found(self, lookup_key: str, ttl: int = NEGATIVE_TTL_SECONDS) -> None:
        now = time.time()
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO fetch_state(lookup_key, status, http_status, retry_after, updated_at)
                   VALUES (?, 'not_found', 404, ?, ?)
                   ON CONFLICT(lookup_key) DO UPDATE SET status='not_found', http_status=404,
                     retry_after=excluded.retry_after, updated_at=excluded.updated_at""",
                (lookup_key, now + max(60, int(ttl)), now),
            )

    def is_negative_cached(self, lookup_key: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT retry_after FROM fetch_state WHERE lookup_key=? AND status='not_found'",
                (lookup_key,),
            ).fetchone()
        return row is not None and float(row["retry_after"] or 0) > time.time()


def default_cache_path() -> Path:
    try:
        from modules.paths_internal import data_path

        return Path(data_path) / "ai-wdywfm" / "cache.sqlite3"
    except (ImportError, AttributeError):
        return Path(__file__).resolve().parents[3] / "data" / "ai-wdywfm" / "cache.sqlite3"
