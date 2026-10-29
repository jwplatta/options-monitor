# Frozen real SPXW chains

Captured 2026-10-29 through Tractatus CacheReader from the local historical MinIO
lakehouse. `sources.json` records the four original object URIs, ETag/size revision
tokens, and source object sizes. The observation dates are October 12–15, 2026.
No values were synthesized or perturbed.

`spxw_chains.csv` retains 45 original rows from eight actual snapshots: the first
sample at or after 10:30 New York time and the closing sample on each date, for
the expiry nearest 30 DTE. For each snapshot it retains the valid ATM strike rows
and the lower/upper delta brackets required for each 25-delta leg. This is a
calculation fixture, not a complete option chain or a test of source discovery.
Synthetic tests separately exercise snapshot selection edge cases.

`expected.json` contains fixed reference values calculated with Python standard
library `decimal.Decimal` arithmetic directly from the captured CSV fields,
without calling dashboard or Tractatus calculation functions:

- ATM IV is the arithmetic mean of available call/put IVs at the valid strike
  nearest the captured spot.
- For each leg, IV(target) = IV(low) + (target - delta(low)) /
  (delta(high) - delta(low)) * (IV(high) - IV(low)). Targets are +0.25 and -0.25.
- Risk reversal is interpolated call IV minus interpolated put IV.

The October 15 closing observation has ATM IV 11.405 and RR
-2.6157142857142857. Against the six October 12–14 observations its IV percentile
is 5/6 * 100 and RR percentile is 1/6 * 100. Both October 15 snapshots are excluded
from that historical comparison. Tests also persist and reload the computed
metrics through SQLite. Tests never fetch live data or regenerate their oracle.
