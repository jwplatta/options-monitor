"""Option-root selectors read the YAML-seeded local registry."""

import json

import pandas as pd

from options_monitor.data.option_root_config import configured_namespace
from options_monitor.data.sqlite_cache import connect_cache


def available_roots() -> tuple[list[str], bool]:
    """Return configured roots synchronously; never discover symbols remotely."""
    namespace, _ = configured_namespace()
    conn = connect_cache()
    try:
        return [
            row[0]
            for row in conn.execute(
                "SELECT option_root FROM option_roots WHERE namespace_id=? ORDER BY option_root",
                (namespace,),
            )
        ], True
    finally:
        conn.close()


def available_root_details() -> pd.DataFrame:
    """Read all configured root mappings for the active storage namespace."""
    namespace, _ = configured_namespace()
    conn = connect_cache()
    try:
        rows = conn.execute(
            "SELECT option_root,underlying,metadata_json FROM option_roots "
            "WHERE namespace_id=? ORDER BY option_root",
            (namespace,),
        ).fetchall()
        return pd.DataFrame(
            [
                (root, underlying, json.loads(metadata).get("asset_class"))
                for root, underlying, metadata in rows
            ],
            columns=["Option root", "Underlying", "Asset class"],
        )
    finally:
        conn.close()
