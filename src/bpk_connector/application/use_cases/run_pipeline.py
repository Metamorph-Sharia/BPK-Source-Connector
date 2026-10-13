"""RunPipeline: the scheduled run. Check every target, fetch new or changed files, rebuild the corpus.

A source outage pauses the run (the next run resumes); being blocked is an error a person must
look at. Either way the corpus is rebuilt from what we already hold.
"""

from __future__ import annotations

import logging

from bpk_connector.application.ports import Blocked, Clock, Repository, TargetCatalog, Unavailable
from bpk_connector.application.run_report import RunReport
from bpk_connector.application.targets import all_targets
from bpk_connector.application.use_cases.check_targets import CheckTargets
from bpk_connector.application.use_cases.export_corpus import ExportCorpus
from bpk_connector.application.use_cases.extract_texts import ExtractTexts
from bpk_connector.application.use_cases.fetch_files import FetchFiles
from bpk_connector.application.use_cases.report_run import ReportRun
from bpk_connector.application.use_cases.sync_sitemaps import SyncSitemaps
from bpk_connector.application.use_cases.triage_new_records import TriageNewRecords

log = logging.getLogger(__name__)


class RunPipeline:
    def __init__(
        self,
        sync: SyncSitemaps,
        triage: TriageNewRecords,
        check: CheckTargets,
        fetch: FetchFiles,
        extract: ExtractTexts,
        export: ExportCorpus,
        report: ReportRun,
        catalog: TargetCatalog,
        repository: Repository,
        clock: Clock,
    ) -> None:
        self.sync = sync
        self.triage = triage
        self.check = check
        self.fetch = fetch
        self.extract = extract
        self.export = export
        self.report = report
        self.catalog = catalog
        self.repository = repository
        self.clock = clock

    def run(self, run_id: str, *, max_bytes: int | None = None, export: bool = True) -> RunReport:
        report = RunReport(run_id, self.clock.now())
        try:
            report.sync = self.sync.run()
            report.triage = self.triage.run(run_id, report.sync.new_ids)
            report.check = self.check.run(run_id)
            record_ids = list(all_targets(self.repository, self.catalog))
            report.fetch = self.fetch.run(run_id, record_ids, max_bytes=max_bytes)
        except Blocked as e:
            log.error("blocked by BPK: %s", e)
            report.status, report.error = "error", f"blocked: {e}"
        except Unavailable as e:
            log.warning("BPK unavailable, pausing until the next run: %s", e)
            report.status, report.error = "paused", str(e)
        report.extract = self.extract.run(run_id)  # local: runs even when BPK is down
        if export:
            report.export = self.export.run()
        self.report.complete(report)
        report.finished_at = self.clock.now()
        return report
