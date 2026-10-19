# Volatility Skew history chart

Status: implemented in the isolated Options Monitor dev runtime.

- Remove Overview and SPX RV from the Vol subtab navigation.
- Show the latest published 30-DTE intraday skew, falling back to a recent
  archived closing chain when intraday data is unavailable.
- Compare it with daily closing skews from the Vol Regime lookback choices:
  30, 45, 60, 180, and 360 calendar days.
- Align historical strikes by spot-relative moneyness; project the historical
  10th–90th percentile band and median onto today's strike scale.
- Cache each derived historical curve indefinitely in Options Monitor's own
  SQLite directory, with source file and calculation-version invalidation.
- Verify curve construction, band alignment, persistent reuse, tab navigation,
  and an isolated development-container smoke run.
