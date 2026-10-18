"""Shared timing and reporting helpers for the Vol dashboard benchmarks."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

DEFAULT_SYMBOLS = ("QQQ", "SPY", "IWM", "GLD", "CRWV")


class Timings:
    def __init__(self) -> None:
        self.samples: dict[str, list[float]] = defaultdict(list)

    def measure(self, label: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            self.samples[label].append(time.perf_counter() - started)

    def patch(self, stack: ExitStack, obj: Any, attr: str, label: str) -> None:
        original = getattr(obj, attr)

        def timed(*args: Any, **kwargs: Any) -> Any:
            return self.measure(label, original, *args, **kwargs)

        stack.enter_context(patch.object(obj, attr, timed))

    def print(self) -> None:
        print("  Stage                              Calls    Total s    Mean ms    Max ms")
        for label, samples in sorted(
            self.samples.items(), key=lambda item: sum(item[1]), reverse=True
        ):
            total = sum(samples)
            print(
                f"  {label:<34} {len(samples):>5} {total:>10.2f} "
                f"{1000 * total / len(samples):>10.1f} {1000 * max(samples):>9.1f}"
            )
        print("  Times are inclusive; nested stages overlap.")


def benchmark_date(value: str, latest: date) -> date:
    if value == "latest":
        return latest
    if value == "today":
        return date.today()
    return date.fromisoformat(value)


class BenchmarkDate(date):
    as_of = date.today()

    @classmethod
    def today(cls) -> date:
        return cls.as_of


def frozen_date(as_of: date) -> type[date]:
    BenchmarkDate.as_of = as_of
    return BenchmarkDate


def cache_stats(cache_dir: Path, symbol: str) -> tuple[int, int]:
    files = (cache_dir / "options" / "schwab").glob(f"**/{symbol}_samples_*.parquet")
    sizes = [path.stat().st_size for path in files]
    return len(sizes), sum(sizes)


def format_bytes(size: int) -> str:
    return f"{size / 1024**2:.1f} MiB"
