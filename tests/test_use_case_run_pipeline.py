"""RunPipeline: one scheduled run, start to finish, and how it ends when BPK is down or blocks us."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fakes.memory import (
    FakeGateway,
    FixedClock,
    MemoryCatalog,
    MemoryEventLog,
    MemoryHistory,
    MemoryRepository,
    MemorySitemapState,
)

from bpk_connector.adapters.extraction.pdf import PdfTextExtractor
from bpk_connector.adapters.storage.blobs import FileBlobStore
from bpk_connector.adapters.storage.corpus import CorpusWriter
from bpk_connector.application.dto import SitemapEntry
from bpk_connector.application.ports import Blocked, Unavailable
from bpk_connector.application.use_cases.check_targets import CheckTargets
from bpk_connector.application.use_cases.export_corpus import ExportCorpus
from bpk_connector.application.use_cases.extract_texts import ExtractTexts
from bpk_connector.application.use_cases.fetch_files import FetchFiles
from bpk_connector.application.use_cases.report_run import ReportRun
from bpk_connector.application.use_cases.run_pipeline import RunPipeline
from bpk_connector.application.use_cases.sync_sitemaps import SyncSitemaps
from bpk_connector.application.use_cases.triage_new_records import TriageNewRecords
from bpk_connector.domain.models import FileRef, Regulation, Relation, Target, TargetOrigin, Tier

LAW = FileRef("295189", "UU.pdf", "/Download/295189/UU.pdf")
SEED = Target("240203", Tier.P1, TargetOrigin.SEED, "A")


def pipeline(tmp_path: Path, gateway: FakeGateway) -> RunPipeline:
    repository, events, catalog, clock = MemoryRepository(), MemoryEventLog(), MemoryCatalog([SEED]), FixedClock()
    blobs = FileBlobStore(tmp_path / "raw")
    return RunPipeline(
        SyncSitemaps(gateway, MemorySitemapState(), clock),
        TriageNewRecords(gateway, repository, events, catalog, clock),
        CheckTargets(gateway, repository, events, blobs, catalog, clock),
        FetchFiles(gateway, repository, events, blobs, clock),
        ExtractTexts(repository, blobs, PdfTextExtractor(), events, catalog, clock),
        ExportCorpus(repository, catalog, CorpusWriter(tmp_path / "corpus", blobs), clock),
        ReportRun(MemoryHistory(repository, events), repository, catalog, clock),
        catalog,
        repository,
        clock,
    )


def test_a_run_checks_fetches_and_exports(tmp_path: Path) -> None:
    gateway = FakeGateway(
        {"240203": Regulation("240203", "P2SK", "UU", "4", "2023", files=(LAW,))}, {LAW.path: b"%PDF"}
    )

    report = pipeline(tmp_path, gateway).run("run-1")

    assert report.status == "ok"
    assert (report.check.checked, report.fetch.stored, report.export.documents) == (1, 1, 1)
    assert (tmp_path / "corpus/documents/bpk/240203/files/Peraturan-295189.pdf").exists()


def test_an_unavailable_source_pauses_the_run_and_still_exports_what_we_have(tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.failure = Unavailable("HTTP 503 after 3 attempts")

    report = pipeline(tmp_path, gateway).run("run-1")

    assert report.status == "paused" and "503" in report.error
    assert report.export is not None


def test_being_blocked_is_an_error_a_person_must_look_at(tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.failure = Blocked("HTTP 403")

    report = pipeline(tmp_path, gateway).run("run-1")

    assert report.status == "error" and report.failed_exit


def test_a_completed_run_carries_its_alerts_and_freshness(tmp_path: Path) -> None:
    gateway = FakeGateway(
        {"240203": Regulation("240203", "P2SK", "UU", "4", "2023", files=(LAW,))}, {LAW.path: b"%PDF"}
    )

    report = pipeline(tmp_path, gateway).run("run-1")

    assert [a.code for a in report.alerts] == []  # a first run's new records are not alerts
    assert report.fill_rates["files"] == 1.0 and len(report.freshness) == 1


def test_new_records_on_bpk_are_triaged_before_targets_are_checked(tmp_path: Path) -> None:
    amendment = Regulation(
        "350166", "UU 4/2026", "UU", "4", "2026", relations=(Relation("Mengubah", "240203", "UU 4/2023"),)
    )
    gateway = FakeGateway({"240203": Regulation("240203", "P2SK", "UU", "4", "2023"), "350166": amendment})
    gateway.sitemaps = {"2026": [SitemapEntry("240203", "s", None)]}
    gateway.sitemap_lastmods = {"2026": date(2026, 10, 12)}
    runner = pipeline(tmp_path, gateway)
    runner.run("run-1")  # baseline
    gateway.sitemaps["2026"].append(SitemapEntry("350166", "s", None))
    gateway.sitemap_lastmods["2026"] = date(2026, 10, 13)

    report = runner.run("run-2")

    assert report.sync.new_ids == ["350166"] and report.triage.added == ["350166"]
    assert report.check.checked == 2  # the new target was checked (and its files fetched) in the same run


def test_text_is_extracted_even_when_bpk_is_down_because_it_is_local(tmp_path: Path) -> None:
    gateway = FakeGateway(
        {"240203": Regulation("240203", "P2SK", "UU", "4", "2023", files=(LAW,))}, {LAW.path: b"%PDF"}
    )
    runner = pipeline(tmp_path, gateway)
    runner.run("run-1")
    gateway.failure = Unavailable("HTTP 503")

    report = runner.run("run-2")

    assert report.status == "paused" and report.extract is not None
