"""Run reports on disk (``data/reports/``) and the alert log (``data/alerts.jsonl``, the always-on channel).

Other channels (Slack, email, webhook) are deferred to the orchestration phase, as in the OJK connector.
"""

from __future__ import annotations

import json
from pathlib import Path

from bpk_connector.application.run_report import RunReport


class ReportFiles:
    def __init__(self, data_dir: Path) -> None:
        self.reports = data_dir / "reports"
        self.alert_log = data_dir / "alerts.jsonl"

    def write(self, report: RunReport) -> None:
        self.reports.mkdir(parents=True, exist_ok=True)
        data = report.as_dict()
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        (self.reports / f"run-{report.run_id}.json").write_text(text, encoding="utf-8")
        (self.reports / "latest.json").write_text(text, encoding="utf-8")
        (self.reports / "latest.md").write_text(_summary(report), encoding="utf-8")
        (self.reports / "freshness.md").write_text(_freshness(report), encoding="utf-8")
        with self.alert_log.open("a", encoding="utf-8") as log:
            for alert in data["alerts"]:
                log.write(json.dumps({"run_id": report.run_id, **alert}, ensure_ascii=False, default=str) + "\n")


def _summary(report: RunReport) -> str:
    lines = [
        f"# Run {report.run_id}: {report.status}",
        "",
        f"Started {report.started_at:%Y-%m-%d %H:%M} UTC. Worst alert: {report.worst_severity or 'none'}.",
    ]
    if report.error:
        lines += ["", f"**Error:** {report.error}"]
    lines += ["", "## Alerts", ""]
    lines += [f"- **{a.severity}** `{a.code}`: {a.message}" for a in report.alerts] or ["None."]
    lines += ["", "## Stages", ""]
    for name in ("check", "fetch", "export"):
        stage = getattr(report, name)
        if stage is not None:
            counts = ", ".join(f"{k}: {v if not isinstance(v, list) else len(v)}" for k, v in vars(stage).items())
            lines.append(f"- **{name}**: {counts}")
    return "\n".join(lines) + "\n"


def _freshness(report: RunReport) -> str:
    measured = [row for row in report.freshness if row.lag_days is not None]
    baseline = sum(row.baseline for row in report.freshness)
    lines = [
        "# Freshness: BPK's publishing lag",
        "",
        "Days from promulgation to the day this connector first saw the record on BPK. The lag is accepted",
        "under decision D2 (BPK is the only source) and measured here so that decision can be revisited.",
        "",
        f"{baseline} record(s) were already on BPK when monitoring began; their lag can't be known.",
        "",
        "## Median lag by form",
        "",
        "| Form | Median days |",
        "|---|---|",
        *[f"| {form} | {days:g} |" for form, days in report.median_lag_by_form.items()],
        "",
        "## Records first seen after monitoring began",
        "",
        "| Regulation | Promulgated | First seen | Lag (days) |",
        "|---|---|---|---|",
        *[f"| {r.citation} | {r.promulgated_on} | {r.first_seen} | {r.lag_days} |" for r in measured],
    ]
    return "\n".join(lines) + "\n"
