"""Committed option-root configuration and relational cache seeding."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import yaml
from tractatus.reader import ReaderConfig

CONFIG_PATH = Path(__file__).parents[1] / "config" / "option_roots.yaml"


def source_namespace(endpoint: str, bucket: str, provider: str = "schwab") -> str:
    payload = json.dumps(
        {"endpoint": endpoint.rstrip("/"), "bucket": bucket, "provider": provider},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def load_option_roots(path: Path) -> tuple[tuple[str, str, str], ...]:
    """Validate identities; retain any additional per-root YAML fields as metadata."""
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or set(payload) != {"option_roots"}:
        raise ValueError("Option roots YAML must contain an option_roots list")
    entries = payload["option_roots"]
    if not isinstance(entries, list):
        raise ValueError("option_roots must be a list")
    result: dict[str, tuple[str, str, str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each option root must be a mapping")
        root, underlying = entry.get("option_root"), entry.get("underlying")
        if not isinstance(root, str) or not isinstance(underlying, str):
            raise ValueError("Each root requires option_root and underlying strings")
        if (
            not root.strip()
            or not underlying.strip()
            or root != root.strip()
            or underlying != underlying.strip()
        ):
            raise ValueError("Root and underlying must be nonempty with no surrounding whitespace")
        if root in result:
            raise ValueError(f"Duplicate option root: {root}")
        extras = {k: v for k, v in entry.items() if k not in ("option_root", "underlying")}
        metadata = json.dumps(extras, sort_keys=True, allow_nan=False)
        result[root] = (root, underlying, metadata)
    return tuple(result[root] for root in sorted(result))


@lru_cache(maxsize=1)
def configured_option_roots() -> tuple[tuple[str, str, str], ...]:
    """Read once per process; restart after editing committed configuration."""
    return load_option_roots(CONFIG_PATH)


def configured_namespace() -> tuple[str, ReaderConfig]:
    cfg = ReaderConfig.load()
    return source_namespace(cfg.minio_endpoint, cfg.minio_lakehouse_bucket), cfg


def seed_option_roots(conn: sqlite3.Connection, namespace: str | None = None) -> None:
    """Sync configured roots, including after a schema reset, without bucket scans."""
    desired = configured_option_roots()
    if namespace is None:
        namespace, cfg = configured_namespace()
        if (
            conn.execute(
                "SELECT 1 FROM cache_namespaces WHERE namespace_id=?", (namespace,)
            ).fetchone()
            is None
        ):
            conn.execute(
                "INSERT INTO cache_namespaces VALUES (?,?,?,?)",
                (namespace, cfg.minio_endpoint.rstrip("/"), cfg.minio_lakehouse_bucket, "schwab"),
            )
    existing = conn.execute(
        "SELECT option_root,underlying,metadata_json FROM option_roots "
        "WHERE namespace_id=? ORDER BY option_root",
        (namespace,),
    ).fetchall()
    if tuple(existing) == desired:
        return
    now = datetime.now(UTC).isoformat()
    conn.executemany(
        "INSERT INTO option_roots "
        "(option_root,underlying,namespace_id,refreshed_at,last_error,metadata_json) "
        "VALUES (?,?,?,?,NULL,?) ON CONFLICT(namespace_id,option_root) DO UPDATE SET "
        "underlying=excluded.underlying,metadata_json=excluded.metadata_json,"
        "refreshed_at=excluded.refreshed_at,last_error=NULL "
        "WHERE underlying IS NOT excluded.underlying "
        "OR metadata_json IS NOT excluded.metadata_json",
        [(root, underlying, namespace, now, metadata) for root, underlying, metadata in desired],
    )
    removed = set(row[0] for row in existing) - {row[0] for row in desired}
    conn.executemany(
        "DELETE FROM option_roots WHERE namespace_id=? AND option_root=?",
        [(namespace, root) for root in removed],
    )
