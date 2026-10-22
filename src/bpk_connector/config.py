"""Configuration (``config/pipeline.toml``).

Relative paths resolve against the config file's directory, so the connector behaves the same
whatever the working directory (e.g. under cron).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from bpk_connector import __version__

DEFAULT_CONFIG_PATH = Path("config/pipeline.toml")
MB = 1024 * 1024
KNOWN = {
    "pipeline": {"data_dir", "contact"},
    "targets": {"targets_csv", "watch_toml"},
    "source": {"requests_per_second", "max_attempts", "max_file_mb", "max_mb_per_run"},
    "monitoring": {"max_hours_between_runs"},
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    path: Path
    data_dir: Path
    targets_csv: Path
    watch_toml: Path
    user_agent: str
    requests_per_second: float = 1.0
    max_attempts: int = 3
    max_file_bytes: int = 200 * MB
    max_bytes_per_run: int = 2048 * MB
    max_hours_between_runs: float = 36.0  # `health` turns critical after this without a successful run


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    _refuse_unknown(raw, path)
    base = path.resolve().parent
    pipeline, targets, source = raw.get("pipeline", {}), raw.get("targets", {}), raw.get("source", {})
    contact = pipeline.get("contact")
    return Config(
        path=path.resolve(),
        data_dir=_resolve(base, pipeline.get("data_dir", "../data")),
        targets_csv=_resolve(base, targets.get("targets_csv", "targets.csv")),
        watch_toml=_resolve(base, targets.get("watch_toml", "watch.toml")),
        user_agent=f"bpk-connector/{__version__}" + (f" (+{contact})" if contact else ""),
        requests_per_second=float(source.get("requests_per_second", 1.0)),
        max_attempts=int(source.get("max_attempts", 3)),
        max_file_bytes=int(source.get("max_file_mb", 200)) * MB,
        max_bytes_per_run=int(source.get("max_mb_per_run", 2048)) * MB,
        max_hours_between_runs=float(raw.get("monitoring", {}).get("max_hours_between_runs", 36.0)),
    )


def _refuse_unknown(raw: dict, path: Path) -> None:
    for section, values in raw.items():
        if section not in KNOWN:
            raise ConfigError(f"{path}: unknown section [{section}]")
        if unknown := set(values) - KNOWN[section]:
            raise ConfigError(f"{path}: unknown [{section}] settings: {', '.join(sorted(unknown))}")


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()
