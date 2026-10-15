"""The command line, offline: commands that need no network, exit codes, and failing loudly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bpk_connector.cli import EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, main

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "pipeline.toml"
    path.write_text(
        f'[pipeline]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[targets]\ntargets_csv = "{ROOT}/config/targets.csv"\nwatch_toml = "{ROOT}/config/watch.toml"\n'
        "[extraction]\nocr = false\n"
    )
    return path


def run(capsys, *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_status_counts_the_curated_seeds(config: Path, capsys) -> None:
    code, out = run(capsys, "--config", str(config), "status")

    assert code == EXIT_OK and json.loads(out)["seeds"] == 93


def test_health_is_critical_before_any_successful_run(config: Path, capsys) -> None:
    code, out = run(capsys, "--config", str(config), "health")

    assert code == EXIT_PROBLEMS and json.loads(out)["health"] == "critical"


def test_an_empty_review_queue_lists_nothing(config: Path, capsys) -> None:
    assert run(capsys, "--config", str(config), "review", "list") == (EXIT_OK, "[]\n")


def test_rejecting_something_not_queued_is_a_usage_error(config: Path, capsys) -> None:
    code, _ = run(capsys, "--config", str(config), "review", "reject", "1", "--note", "x")

    assert code == EXIT_USAGE


def test_a_missing_config_is_a_usage_error(tmp_path: Path, capsys) -> None:
    assert run(capsys, "--config", str(tmp_path / "nope.toml"), "status")[0] == EXIT_USAGE


def test_run_refuses_to_start_on_a_machine_missing_its_ocr_tools(config: Path, capsys) -> None:
    config.write_text(config.read_text().replace("ocr = false", 'ocr = true\nocr_languages = "ind+xxx"'))

    code, _ = run(capsys, "--config", str(config), "run")  # returns before any network call

    assert code == EXIT_PROBLEMS


def test_export_v2_writes_a_complete_bundle_even_when_nothing_is_held(config: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "bundle"

    code, printed = run(
        capsys, "--config", str(config), "export", "--format", "v2", "--out", str(out), "--run-id", "r1"
    )

    assert code == EXIT_OK
    assert json.loads(printed)["documents"] == 0
    assert json.loads((out / "manifest.json").read_text())["run_id"] == "r1"


def test_export_v2_needs_an_output_directory(config: Path, capsys) -> None:
    assert run(capsys, "--config", str(config), "export", "--format", "v2")[0] == EXIT_USAGE
