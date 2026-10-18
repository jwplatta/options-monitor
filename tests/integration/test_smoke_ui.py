"""Smoke checks for the current Streamlit dashboard navigation."""

from __future__ import annotations

from playwright.sync_api import Page, expect


def test_dashboard_loads_navigation(page: Page, streamlit_server: str) -> None:
    page.goto(streamlit_server)
    expect(page.get_by_text("Options Monitor")).to_be_visible(timeout=20000)
    sidebar = page.locator("[data-testid=stSidebar]")
    for panel in ("Vol", "GEX", "Flow", "OI", "History"):
        expect(sidebar.get_by_text(panel, exact=True)).to_be_visible(timeout=20000)


def test_vol_and_gex_panels_render(page: Page, streamlit_server: str) -> None:
    page.goto(streamlit_server)
    sidebar = page.locator("[data-testid=stSidebar]")
    sidebar.get_by_text("Vol", exact=True).click()
    expect(page.get_by_text("Volatility")).to_be_visible(timeout=20000)
    sidebar.get_by_text("GEX", exact=True).click()
    expect(page.get_by_text("GEX", exact=True).last).to_be_visible(timeout=20000)


def test_vol_regime_renders_when_selected(page: Page, streamlit_server: str) -> None:
    page.goto(streamlit_server)
    regime = page.get_by_role("tab", name="Vol Regime")
    expect(regime).to_be_visible(timeout=20000)
    prompt = page.get_by_text("Select one or more symbols to generate the vol regime chart.")
    expect(prompt).to_have_count(0)
    regime.click()
    expect(prompt).to_be_visible(timeout=20000)
