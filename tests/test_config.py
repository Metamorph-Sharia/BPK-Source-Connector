"""Configuration loading: paths resolve against the config file, unknown settings are refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from bpk_connector.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_the_shipped_config_loads_with_paths_resolved_against_it() -> None:
    config = load_config(ROOT / "config/pipeline.toml")

    assert config.data_dir == ROOT / "data"
    assert config.targets_csv == ROOT / "config/targets.csv"
    assert config.requests_per_second == 1.0
    assert config.max_file_bytes == 200 * 1024 * 1024
    assert config.user_agent.startswith("bpk-connector/")


def test_a_contact_is_added_to_the_user_agent(tmp_path: Path) -> None:
    path = tmp_path / "pipeline.toml"
    path.write_text('[pipeline]\ncontact = "mailto:team@example.com"\n')

    assert load_config(path).user_agent.endswith("(+mailto:team@example.com)")


def test_unknown_settings_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "pipeline.toml"
    path.write_text("[source]\nrequests_per_secnd = 5\n")

    with pytest.raises(ConfigError, match="requests_per_secnd"):
        load_config(path)
