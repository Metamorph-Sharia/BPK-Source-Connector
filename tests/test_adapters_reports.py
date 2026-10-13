"""Run reports on disk: JSON for machines, markdown for people, an alert log, and the freshness table."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fakes.memory import NOW

from bpk_connector.adapters.monitoring.reports import ReportFiles
from bpk_connector.application.run_report import RunReport
from bpk_connector.application.use_cases.check_targets import CheckSummary
from bpk_connector.domain.alerts import Alert, Severity
from bpk_connector.domain.freshness import FreshnessRow


def report() -> RunReport:
    return RunReport(
        "20261014T060000Z",
        NOW,
        NOW,
        check=CheckSummary(checked=130),
        alerts=[Alert("target_changed", Severity.INFO, "1 target(s) amended", {"record_ids": ["240203"]})],
        freshness=[
            FreshnessRow("400001", "PMK 70/2026", "PMK", date(2026, 9, 1), date(2026, 10, 13), 42, False),
            FreshnessRow("240203", "UU 4/2023", "UU", date(2023, 1, 12), date(2026, 10, 1), None, True),
        ],
        median_lag_by_form={"PMK": 42},
    )


def test_a_run_writes_json_markdown_and_appends_its_alerts(tmp_path: Path) -> None:
    files = ReportFiles(tmp_path)

    files.write(report())
    files.write(report())

    latest = json.loads((tmp_path / "reports/latest.json").read_text())
    assert latest["run_id"] == "20261014T060000Z" and latest["alerts"][0]["severity"] == "info"
    assert (tmp_path / "reports/run-20261014T060000Z.json").exists()
    markdown = (tmp_path / "reports/latest.md").read_text()
    assert "target_changed" in markdown and "checked: 130" in markdown
    assert len((tmp_path / "alerts.jsonl").read_text().splitlines()) == 2


def test_the_freshness_table_lists_measured_lags_and_counts_the_baseline(tmp_path: Path) -> None:
    ReportFiles(tmp_path).write(report())

    freshness = (tmp_path / "reports/freshness.md").read_text()
    assert "| PMK | 42 |" in freshness
    assert "| PMK 70/2026 | 2026-09-01 | 2026-10-13 | 42 |" in freshness
    assert "1 record(s) were already on BPK" in freshness
