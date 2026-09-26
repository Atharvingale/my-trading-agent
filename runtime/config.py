"""Runtime configuration: paper by default, production locked (integration).

Why paper-default: no live-trading path may arm by accident. Production boot
demands an explicit HERMES_LIVE_TRADING=1 flag on top of production
credentials — and even then the pipeline idles without a real Module 1 PASS
plus approval plus immutable version.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    data_dir: str
    symbols: tuple[str, ...]
    starting_equity: float = 10000.0

    def __post_init__(self) -> None:
        if self.environment not in ("paper", "production"):
            raise ValueError("environment must be paper or production")
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if self.starting_equity <= 0:
            raise ValueError("starting_equity must be positive")

    @staticmethod
    def from_environment() -> RuntimeConfig:
        """Paper unless explicitly production; production needs a live flag."""
        env = str(os.environ.get("HERMES_EXEC_ENV", "") or "paper").strip().lower()
        if env not in ("paper", "production"):
            raise ValueError("HERMES_EXEC_ENV must be paper or production")
        if env == "production":
            flag = str(os.environ.get("HERMES_LIVE_TRADING", "") or "").strip().lower()
            if flag != "1":
                raise ValueError(
                    "production boot refused: set HERMES_LIVE_TRADING=1 explicitly"
                )
        data_dir = str(os.environ.get("HERMES_DATA_DIR", "data") or "data").strip()
        raw_symbols = str(os.environ.get("BINANCE_SYMBOLS", "BTCUSDT") or "BTCUSDT")
        symbols: list[str] = []
        for item in raw_symbols.split(","):
            token = str(item).strip().upper()
            if token and token not in symbols:
                symbols.append(token)
        equity_raw = str(os.environ.get("HERMES_STARTING_EQUITY", "10000.0") or "10000.0")
        try:
            equity = float(equity_raw)
        except (TypeError, ValueError):
            raise ValueError("HERMES_STARTING_EQUITY must be a number")
        return RuntimeConfig(
            environment=env,
            data_dir=data_dir,
            symbols=tuple(symbols),
            starting_equity=equity,
        )

    def store_paths(self) -> dict[str, str]:
        """One SQLite file per store under the data directory."""
        base = Path(self.data_dir)
        paths: dict[str, str] = {}
        paths["edge"] = str(base / "runtime_edge_validation.sqlite3")
        paths["edge_report"] = str(base / "EXPERIMENT_REGISTRY_RUNTIME.md")
        paths["versions"] = str(base / "production_versions.sqlite3")
        paths["reviews"] = str(base / "review_queue.sqlite3")
        paths["execution"] = str(base / "execution.sqlite3")
        paths["lifecycle"] = str(base / "lifecycle.sqlite3")
        paths["memory"] = str(base / "memory.sqlite3")
        paths["lessons"] = str(base / "lessons.sqlite3")
        paths["candidates"] = str(base / "candidates.sqlite3")
        return paths
