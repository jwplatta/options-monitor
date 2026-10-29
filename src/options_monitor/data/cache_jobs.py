"""Persistent, bounded jobs shared by dashboard historical caches."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from options_monitor.data.option_root_config import seed_option_roots, source_namespace
from options_monitor.data.sqlite_cache import cache_path, connect_cache

log = logging.getLogger(__name__)


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def market_today() -> date:
    """Return the calendar date in the configured dashboard timezone."""
    timezone = ZoneInfo(os.environ.get("OPTIONS_MONITOR_TIMEZONE", "America/Chicago"))
    return datetime.now(timezone).date()


def canonical(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class JobDefinition:
    job_id: str
    defaults: dict[str, Any]
    validate: Callable[[dict[str, Any]], dict[str, Any]]
    compute: Callable[[str, dict[str, Any]], None]
    cleanup: Callable[[date], None]
    refresh_seconds: int = 900
    warmup_enabled: bool = True


class CacheJobs:
    """One scheduler/worker per process; all persistent writes use short transactions."""

    def __init__(
        self, endpoint: str, bucket: str, provider: str = "schwab", path: Path | None = None
    ) -> None:
        self.path = path or cache_path()
        self.namespace = source_namespace(endpoint, bucket, provider)
        self.definitions: dict[str, JobDefinition] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        with self.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO cache_namespaces VALUES (?,?,?,?)",
                (self.namespace, endpoint.rstrip("/"), bucket, provider),
            )
            seed_option_roots(conn, self.namespace)
            conn.execute(
                "UPDATE cache_job_state SET status='queued' WHERE namespace_id=? "
                "AND status IN ('running','queued')",
                (self.namespace,),
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Commit then close; connections are never shared between threads."""
        conn = connect_cache(self.path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def register(self, definition: JobDefinition) -> None:
        definition.validate(definition.defaults)
        with self._lock:
            self.definitions[definition.job_id] = definition

    def retention(self, job_id: str) -> int:
        return int(self.setting(f"{job_id}:retention_days", 365))

    def setting(self, key: str, default: Any) -> Any:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value_json FROM cache_settings WHERE setting_key=?",
                (f"{self.namespace}:{key}",),
            ).fetchone()
        return default if row is None else json.loads(row[0])

    def set_setting(self, key: str, value: Any) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache_settings VALUES (?,?,?)",
                (f"{self.namespace}:{key}", json.dumps(value), now_utc()),
            )

    def targets(self, job_id: str) -> list[str]:
        """Every chart uses the shared list; metadata jobs opt out of warmup."""
        if job_id in self.definitions and not self.definitions[job_id].warmup_enabled:
            return []
        with self.connection() as conn:
            return [
                row[0]
                for row in conn.execute(
                    "SELECT root FROM cache_warmup_targets WHERE namespace_id=? AND job_id='*' "
                    "AND enabled=1 ORDER BY position",
                    (self.namespace,),
                )
            ]

    def set_shared_targets(self, roots: list[str]) -> None:
        """Persist the shared list without changing chart-specific parameters."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM cache_warmup_targets WHERE namespace_id=? AND job_id='*'",
                (self.namespace,),
            )
            conn.executemany(
                "INSERT INTO cache_warmup_targets VALUES ('*',?,?,'{}',1,?)",
                [(self.namespace, root, index) for index, root in enumerate(dict.fromkeys(roots))],
            )

    def set_targets(self, job_id: str, roots: list[str], params: dict[str, Any]) -> None:
        """Set a job's parameters and the shared warmup list."""
        definition = self.definitions[job_id]
        payload = definition.validate(params)
        self.set_shared_targets(roots)
        self.set_setting(f"{job_id}:warmup_params", payload)

    def request(
        self,
        job_id: str,
        root: str,
        params: dict[str, Any],
        warmup: bool = False,
    ) -> None:
        definition = self.definitions[job_id]
        payload = canonical(definition.validate(params))
        key = (job_id, self.namespace, root, payload)
        now = now_utc()
        with self.connection() as conn:
            row = conn.execute(
                "SELECT status,completed_at,next_attempt_at "
                "FROM cache_job_state WHERE job_id=? AND namespace_id=? "
                "AND root=? AND params_json=?",
                key,
            ).fetchone()
            if row is not None:
                if not warmup:
                    conn.execute(
                        "UPDATE cache_job_state SET last_accessed_at=?,priority=0 "
                        "WHERE job_id=? AND namespace_id=? AND root=? AND params_json=?",
                        (now, *key),
                    )
                if row[0] in ("queued", "running"):
                    return
                if row[2] and row[2] > now:
                    return
                cutoff = (
                    datetime.now(UTC) - timedelta(seconds=definition.refresh_seconds)
                ).isoformat()
                if row[0] == "ready" and row[1] and row[1] > cutoff:
                    return
            conn.execute(
                "INSERT INTO cache_job_state "
                "(job_id,namespace_id,root,params_json,status,requested_at,"
                "last_accessed_at,priority) VALUES (?,?,?,?,'queued',?,?,?) "
                "ON CONFLICT(job_id,namespace_id,root,params_json) DO UPDATE SET "
                "status='queued',requested_at=excluded.requested_at,"
                "priority=excluded.priority",
                (*key, now, now, int(warmup)),
            )

    def state(self, job_id: str, root: str, params: dict[str, Any]) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT status,completed_at,last_error FROM cache_job_state "
                "WHERE job_id=? AND namespace_id=? AND root=? AND params_json=?",
                (job_id, self.namespace, root, canonical(params)),
            ).fetchone()
        return dict(zip(("status", "completed_at", "last_error"), row, strict=True)) if row else {}

    def tick(self) -> bool:
        """Run at most one expensive job. Also callable deterministically in tests."""
        with self._lock:
            definitions = dict(self.definitions)
        for job_id, definition in definitions.items():
            cleanup_key = f"{job_id}:cleanup_date"
            if self.setting(cleanup_key, "") != market_today().isoformat():
                definition.cleanup(market_today() - timedelta(days=self.retention(job_id)))
                self.set_setting(cleanup_key, market_today().isoformat())
            params = self.setting(f"{job_id}:warmup_params", definition.defaults)
            roots = self.targets(job_id)
            if definition.warmup_enabled:
                with self.connection() as conn:
                    sql = (
                        "DELETE FROM cache_job_state WHERE namespace_id=? AND job_id=? "
                        "AND priority=1 AND status IN ('queued','failed')"
                    )
                    if roots:
                        sql += " AND root NOT IN (" + ",".join("?" for _ in roots) + ")"
                    conn.execute(sql, (self.namespace, job_id, *roots))
            for root in roots:
                self.request(job_id, root, params, warmup=True)
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT job_id,root,params_json,attempt_count FROM cache_job_state "
                "WHERE namespace_id=? AND (status='queued' OR "
                "(status='failed' AND next_attempt_at<=?)) "
                "ORDER BY priority,requested_at",
                (self.namespace, now_utc()),
            ).fetchall()
            row = next((row for row in rows if row[0] in definitions), None)
            if row is None:
                return False
            job_id, root, payload, attempts = row
            key = (job_id, self.namespace, root, payload)
            conn.execute(
                "UPDATE cache_job_state SET status='running',started_at=? "
                "WHERE job_id=? AND namespace_id=? AND root=? AND params_json=?",
                (now_utc(), *key),
            )
        try:
            definitions[job_id].compute(root, json.loads(payload))
        except Exception as exc:
            log.exception("Cache job failed: %s %s", job_id, root)
            retry = datetime.now(UTC) + timedelta(seconds=min(900, 30 * 2 ** min(attempts, 5)))
            with self.connection() as conn:
                conn.execute(
                    "UPDATE cache_job_state SET status='failed',last_error=?,"
                    "attempt_count=attempt_count+1,next_attempt_at=? "
                    "WHERE job_id=? AND namespace_id=? AND root=? AND params_json=?",
                    (str(exc), retry.isoformat(), *key),
                )
        else:
            with self.connection() as conn:
                conn.execute(
                    "UPDATE cache_job_state SET status='ready',completed_at=?,"
                    "attempt_count=0,next_attempt_at=NULL,last_error=NULL "
                    "WHERE job_id=? AND namespace_id=? AND root=? AND params_json=?",
                    (now_utc(), *key),
                )
        return True

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run, daemon=True, name="dashboard-cache")
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                busy = self.tick()
            except Exception:
                log.exception("Cache scheduler failed")
                busy = False
            self._stop.wait(0.1 if busy else 2)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
