"""The report of one run: what each stage did, what it raised, and how fresh the corpus is."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from bpk_connector.application.use_cases.check_targets import CheckSummary
from bpk_connector.application.use_cases.export_corpus import ExportSummary
from bpk_connector.application.use_cases.extract_texts import ExtractSummary
from bpk_connector.application.use_cases.fetch_files import FetchSummary
from bpk_connector.application.use_cases.sync_sitemaps import SyncResult
from bpk_connector.application.use_cases.triage_new_records import TriageSummary
from bpk_connector.domain.alerts import Alert, Severity
from bpk_connector.domain.freshness import FreshnessRow


@dataclass
class RunReport:
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "ok"  # ok | paused | error
    error: str | None = None
    sync: SyncResult | None = None
    triage: TriageSummary | None = None
    check: CheckSummary | None = None
    fetch: FetchSummary | None = None
    extract: ExtractSummary | None = None
    export: ExportSummary | None = None
    alerts: list[Alert] = field(default_factory=list)
    fill_rates: dict[str, float] = field(default_factory=dict)
    freshness: list[FreshnessRow] = field(default_factory=list)
    median_lag_by_form: dict[str, float] = field(default_factory=dict)

    @property
    def worst_severity(self) -> Severity | None:
        return max((a.severity for a in self.alerts), default=None)

    @property
    def failed_exit(self) -> bool:
        """Fail loudly: the run errored, or raised an error or critical alert."""
        return self.status == "error" or (self.worst_severity or 0) >= Severity.ERROR

    def as_dict(self) -> dict:
        data = asdict(self)
        data["alerts"] = [asdict(a) | {"severity": str(a.severity)} for a in self.alerts]
        data["worst_severity"] = str(self.worst_severity) if self.worst_severity else None
        return data
