"""Shared, range-aware historical source inventories for chart cache jobs."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from tractatus.reader import CacheReader, OptionSource

from options_monitor.data.cache_jobs import CacheJobs, now_utc


class SourceInventory:
    """Persist one multi-root discovery and reuse it across symbols and parameters."""

    def __init__(self, jobs: CacheJobs, refresh_seconds: int = 900) -> None:
        self.jobs = jobs
        self.refresh_seconds = refresh_seconds

    def get(
        self, reader: CacheReader, roots: list[str], after: date, before: date
    ) -> dict[str, list[OptionSource]]:
        roots = sorted(set(roots))
        if not roots or before < after:
            return {root: [] for root in roots}
        placeholders = ",".join("?" for _ in roots)
        with self.jobs.connection() as db:
            rows = db.execute(
                "SELECT root,after_date,before_date,refreshed_at FROM cache_source_scans "
                f"WHERE namespace_id=? AND root IN ({placeholders})",
                (self.jobs.namespace, *roots),
            ).fetchall()
        scans = {root: (start, end, checked) for root, start, end, checked in rows}
        freshness = (datetime.now(UTC) - timedelta(seconds=self.refresh_seconds)).isoformat()
        stale = [
            root
            for root in roots
            if root not in scans
            or not (
                scans[root][0] <= after.isoformat()
                and scans[root][1] >= before.isoformat()
                and scans[root][2] > freshness
            )
        ]
        if stale:
            # Network calls happen before the transaction; failure preserves old inventory.
            discovered = reader.discover_option_sources(
                stale, after, before, provider=self.jobs.provider
            )
            checked = now_utc()
            with self.jobs.connection() as db:
                for root in stale:
                    db.execute(
                        "DELETE FROM cache_sources WHERE namespace_id=? AND root=?",
                        (self.jobs.namespace, root),
                    )
                    db.executemany(
                        "INSERT INTO cache_sources VALUES (?,?,?,?,?,?,?)",
                        [
                            (
                                self.jobs.namespace,
                                root,
                                source.sample_date.isoformat(),
                                source.uri,
                                source.revision,
                                source.size_bytes,
                                checked,
                            )
                            for source in discovered.get(root, [])
                        ],
                    )
                    # Successful empty roots need a scan record too, avoiding repeated scans.
                    db.execute(
                        "INSERT INTO cache_source_scans VALUES (?,?,?,?,?) "
                        "ON CONFLICT(namespace_id,root) DO UPDATE SET "
                        "after_date=excluded.after_date,before_date=excluded.before_date,"
                        "refreshed_at=excluded.refreshed_at",
                        (self.jobs.namespace, root, after.isoformat(), before.isoformat(), checked),
                    )
        result: dict[str, list[OptionSource]] = {root: [] for root in roots}
        with self.jobs.connection() as db:
            for root, day, uri, revision, size in db.execute(
                "SELECT root,sample_date,uri,revision,size_bytes FROM cache_sources "
                f"WHERE namespace_id=? AND root IN ({placeholders}) "
                "AND sample_date>=? AND sample_date<=? ORDER BY root,sample_date",
                (self.jobs.namespace, *roots, after.isoformat(), before.isoformat()),
            ):
                result[root].append(OptionSource(date.fromisoformat(day), uri, revision, size))
        return result
