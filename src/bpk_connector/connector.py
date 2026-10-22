"""The BPK connector as the orchestrator sees it: the team's ``SourceConnector`` interface (v1.0).

    connector = BPKConnector({"config": "config/pipeline.toml"})

It never touches our SQLite store: under the orchestrator, the orchestrator owns storage and
cursors. Targets come from the catalog and BPK's own links (re-derived every time), and BPK's
fields pass through unchanged (contract rule 3). No canonical IDs (decision D4).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from bpk_connector import __version__
from bpk_connector.application.dto import SELF_EXTRACTED_TEXT, DetailPage, ExtractedText
from bpk_connector.application.ports import (
    BpkGateway,
    FileTooLarge,
    NotExtractable,
    NotFound,
    TargetCatalog,
    TextExtractor,
    Unavailable,
)
from bpk_connector.application.walk import walk_targets
from bpk_connector.config import DEFAULT_CONFIG_PATH, load_config
from bpk_connector.domain.changes import fingerprint
from bpk_connector.domain.file_roles import FileRole, file_roles
from bpk_connector.domain.identity import source_id
from bpk_connector.domain.models import FileRef, Target
from bpk_connector.source_connector import (
    Discovered,
    Discovery,
    Fetched,
    FileStore,
    ItemFailed,
    SourceConnector,
    SourceUnavailable,
    StoredFile,
)
from bpk_connector.wiring import build_catalog, build_extractor, build_gateway

log = logging.getLogger(__name__)

DETAILS_URL = "https://peraturan.bpk.go.id/Details/{}"
HTML = "text/html"
PDF = "application/pdf"
TEXT = "text/plain; charset=utf-8"


class BPKConnector(SourceConnector):
    name = "bpk"
    version = __version__
    max_concurrency = 1  # one polite client, about 1 request per second

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        gateway: BpkGateway | None = None,
        catalog: TargetCatalog | None = None,
        extractor: TextExtractor | None = None,
    ) -> None:
        super().__init__(config)
        if gateway is None or catalog is None or extractor is None:
            settings = load_config(config.get("config", DEFAULT_CONFIG_PATH))
            gateway = gateway or build_gateway(settings)
            catalog = catalog or build_catalog(settings)
            extractor = extractor or build_extractor()
        self.gateway = gateway
        self.catalog = catalog
        self.extractor = extractor

    def discover(self, cursor: str | None) -> Discovery:
        """Every target, every time: BPK can't signal when a record gains an "amended by" link."""
        seeds = {t.record_id: t for t in self.catalog.seeds()}
        items = []
        try:
            for visit in walk_targets(self.gateway, seeds, self.catalog.watch_rules()):
                if visit.page is None:
                    log.warning("target %s is gone from BPK", visit.target.record_id)
                    continue
                items.append(_discovered(visit.target, visit.page))
        except Unavailable as e:  # includes Blocked
            raise SourceUnavailable(str(e)) from e
        return Discovery(items=items, cursor=None)

    def fetch(self, item: Discovered, store: FileStore) -> Fetched:
        record_id = item.metadata["record_id"]
        try:
            page = self.gateway.detail(record_id)
            saved = [store.put(page.html, media_type=HTML, source_url=item.source_url)]
            roles = file_roles(page.regulation.files)
            files = [self._fetch_file(ref, roles[ref.path], store, saved) for ref in page.regulation.files]
        except NotFound as e:
            raise ItemFailed(f"gone from BPK: {e}", retryable=False) from e
        except FileTooLarge as e:
            raise ItemFailed(f"file over the size cap: {e}", retryable=False) from e
        except Unavailable as e:
            raise SourceUnavailable(str(e)) from e
        return Fetched(files=saved, metadata=_metadata(record_id, page) | {"files": files})

    def _fetch_file(self, ref: FileRef, role: FileRole, store: FileStore, saved: list[StoredFile]) -> dict[str, Any]:
        """Save the file and its extracted text through ``store``; describe both."""
        download = self.gateway.download(ref)
        stored = store.put(download.content, media_type=download.media_type or PDF, source_url=download.url)
        saved.append(stored)
        entry = {**_file(ref, role), "sha256": stored.sha256, "url": download.url, "text": None}
        try:
            extracted = self.extractor.extract(download.content)
        except NotExtractable as e:
            return entry | {"text_note": str(e)}
        text = store.put(extracted.text.encode("utf-8"), media_type=TEXT, source_url=download.url)
        saved.append(text)
        return entry | {"text": _text_entry(text.sha256, extracted)}


def _discovered(target: Target, page: DetailPage) -> Discovered:
    regulation = page.regulation
    roles = file_roles(regulation.files)
    return Discovered(
        source_id=source_id(regulation.record_id),
        source_url=DETAILS_URL.format(regulation.record_id),
        version=fingerprint(regulation),
        metadata=_metadata(regulation.record_id, page)
        | {
            "files": [_file(f, roles[f.path]) for f in regulation.files],
            "target": {
                "tier": target.tier.value,
                "domain": target.domain,
                "origin": target.origin.value,
                "via": target.via,
                "historical": target.historical,
            },
        },
    )


def _metadata(record_id: str, page: DetailPage) -> dict[str, Any]:
    regulation = page.regulation
    return {
        "record_id": record_id,
        "citation": regulation.citation,
        "fields": dict(regulation.fields),
        "relations": [r.summary | {"about": r.about} for r in regulation.relations],
    }


def _text_entry(sha256: str, extracted: ExtractedText) -> dict[str, Any]:
    return {
        "sha256": sha256,
        "method": extracted.method,
        "pages": extracted.pages,
        "pages_without_text": extracted.pages_without_text,
        "coverage": extracted.coverage,
    } | SELF_EXTRACTED_TEXT


def _file(ref: FileRef, role: FileRole) -> dict[str, str]:
    return {**ref.summary, "role": role, "path": ref.path}
