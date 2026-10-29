"""Settings renders the complete relational root registry without discovery."""

from streamlit.testing.v1 import AppTest
from tractatus.reader import ReaderConfig

from options_monitor.data import vol_regime_jobs
from options_monitor.data.cache_jobs import CacheJobs
from options_monitor.data.option_root_config import configured_option_roots


def test_settings_displays_all_configured_option_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIONS_MONITOR_CACHE_DIR", str(tmp_path))
    cfg = ReaderConfig.load()
    jobs = CacheJobs(cfg.minio_endpoint, cfg.minio_lakehouse_bucket)
    vol_regime_jobs.register_vol_regime(jobs)
    monkeypatch.setattr(vol_regime_jobs, "_runtime", jobs)
    app = AppTest.from_string(
        "from options_monitor.tabs.settings import render_settings_page\nrender_settings_page()\n"
    ).run()
    assert not app.exception
    table = app.dataframe[0].value
    assert len(table) == len(configured_option_roots())
    mapping = table.set_index("Option root")["Underlying"]
    assert mapping["NDX"] == "$NDX"
    assert mapping["NDXP"] == "$NDX"
    assert mapping["XSP"] == "$XSP"
    assert set(table.columns) == {"Option root", "Underlying", "Asset class"}
