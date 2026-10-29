"""Option-root selectors read the YAML-seeded local registry."""

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
