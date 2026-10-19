"""Composition root: the only module that knows every concrete class. Builds adapters, hands them to use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from bpk_connector import __version__
from bpk_connector.adapters.bpk.detail_parser import parse_detail
from bpk_connector.adapters.bpk.gateway import BASE_URL, HttpBpkGateway
from bpk_connector.adapters.catalog.files import FileCatalog
from bpk_connector.adapters.extraction.archive import ArchiveTextExtractor
from bpk_connector.adapters.extraction.ocr import OcrTextExtractor, ocr_problems
from bpk_connector.adapters.extraction.pdf import PdfTextExtractor
from bpk_connector.adapters.monitoring.reports import ReportFiles
from bpk_connector.adapters.storage.blobs import FileBlobStore
from bpk_connector.adapters.storage.corpus import CorpusWriter
from bpk_connector.adapters.storage.sqlite import SqliteStore
from bpk_connector.adapters.storage.v2_bundle import V2BundleWriter
from bpk_connector.application.ports import TextExtractor
from bpk_connector.application.use_cases.check_targets import CheckTargets
from bpk_connector.application.use_cases.export_bundle import ExportBundle
from bpk_connector.application.use_cases.export_corpus import ExportCorpus
from bpk_connector.application.use_cases.extract_texts import ExtractTexts
from bpk_connector.application.use_cases.fetch_files import FetchFiles
from bpk_connector.application.use_cases.reparse import Reparse
from bpk_connector.application.use_cases.report_run import ReportRun
from bpk_connector.application.use_cases.review_candidates import ReviewCandidates
from bpk_connector.application.use_cases.run_pipeline import RunPipeline
from bpk_connector.application.use_cases.sync_sitemaps import SyncSitemaps
from bpk_connector.application.use_cases.triage_new_records import TriageNewRecords
from bpk_connector.config import Config

HTTP_TIMEOUT_SECONDS = 60.0


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass
class App:
    config: Config
    store: SqliteStore
    blobs: FileBlobStore
    catalog: FileCatalog
    gateway: HttpBpkGateway
    check: CheckTargets
    fetch: FetchFiles
    extract: ExtractTexts
    export: ExportCorpus
    pipeline: RunPipeline
    reports: ReportFiles
    clock: SystemClock
    reparse: Reparse
    review: ReviewCandidates

    def close(self) -> None:
        self.gateway.close()
        self.store.close()

    def export_bundle(self, out_dir: Path, run_id: str) -> ExportBundle:
        """The platform hand-off: a contract v2 bundle in `out_dir` (empty or new)."""
        writer = V2BundleWriter(out_dir, self.blobs, run_id=run_id, connector_version=__version__)
        return ExportBundle(self.store, self.catalog, writer)


def build_gateway(config: Config) -> HttpBpkGateway:
    return HttpBpkGateway(
        httpx.Client(base_url=BASE_URL, timeout=HTTP_TIMEOUT_SECONDS),
        user_agent=config.user_agent,
        requests_per_second=config.requests_per_second,
        max_attempts=config.max_attempts,
        max_file_bytes=config.max_file_bytes,
    )


def build_extractor(config: Config) -> TextExtractor:
    pdf = OcrTextExtractor(config.ocr_languages) if config.ocr else PdfTextExtractor()
    return ArchiveTextExtractor(pdf)  # .zip annexes hold PDFs too (Perpres 10/2021's investment list)


def environment_problems(config: Config) -> list[str]:
    """What this machine lacks to run the connector as configured. Checked before work starts."""
    return ocr_problems(config.ocr_languages) if config.ocr else []


def build_catalog(config: Config) -> FileCatalog:
    return FileCatalog(config.targets_csv, config.watch_toml)


def build(config: Config) -> App:
    gateway = build_gateway(config)
    store = SqliteStore(config.data_dir / "db" / "bpk_connector.sqlite")
    blobs = FileBlobStore(config.data_dir / "raw")
    catalog = build_catalog(config)
    clock = SystemClock()
    check = CheckTargets(gateway, store, store, blobs, catalog, clock)
    fetch = FetchFiles(gateway, store, store, blobs, clock)
    export = ExportCorpus(store, catalog, CorpusWriter(config.data_dir / "corpus", blobs), clock)
    extract = ExtractTexts(store, blobs, build_extractor(config), store, catalog, clock, ocr_available=config.ocr)
    pipeline = RunPipeline(
        sync=SyncSitemaps(gateway, store, clock),
        triage=TriageNewRecords(gateway, store, store, catalog, clock),
        check=check,
        fetch=fetch,
        extract=extract,
        export=export,
        report=ReportRun(store, store, catalog, clock),
        catalog=catalog,
        repository=store,
        clock=clock,
    )
    return App(
        config=config,
        store=store,
        blobs=blobs,
        catalog=catalog,
        gateway=gateway,
        check=check,
        fetch=fetch,
        extract=extract,
        export=export,
        pipeline=pipeline,
        reports=ReportFiles(config.data_dir),
        clock=clock,
        reparse=Reparse(store, store, blobs, parse_detail, clock),
        review=ReviewCandidates(gateway, store, store, catalog, clock),
    )
