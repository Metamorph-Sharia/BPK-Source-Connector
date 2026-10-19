"""ExportBundle: every target we hold, as the platform's contract v2 bundle (a full snapshot).

The same targets as the corpus export (ExportCorpus). Here each regulation also gets its
canonical ID (domain/identity.py), its standing, and citations for what it does to other
regulations (domain/standing.py). Writing the contract's format is the BundleWriter's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bpk_connector.application.dto import BundleCitation, BundleDocument, BundleFile
from bpk_connector.application.ports import BundleWriter, Repository, TargetCatalog
from bpk_connector.application.targets import all_targets
from bpk_connector.domain.file_roles import file_roles
from bpk_connector.domain.identity import cited_id, national_id
from bpk_connector.domain.models import Regulation
from bpk_connector.domain.standing import outgoing, standing


@dataclass
class BundleSummary:
    documents: int = 0
    texts: int = 0
    unresolved: int = 0  # no usable number, or another record has the same ID: loaded for review
    citations: int = 0
    citations_with_target: int = 0
    without_content: list[str] = field(default_factory=list)  # observed, but no file stored yet
    missing: list[str] = field(default_factory=list)  # targets never observed


class ExportBundle:
    def __init__(self, repository: Repository, catalog: TargetCatalog, writer: BundleWriter) -> None:
        self.repository = repository
        self.catalog = catalog
        self.writer = writer

    def run(self) -> BundleSummary:
        summary = BundleSummary()
        held = self._held(summary)
        ids = _first_claims(held)
        documents = []
        for regulation in held:
            document = self._document(regulation, ids)
            if document is None:
                summary.without_content.append(regulation.record_id)
                continue
            documents.append(document)
            _count(summary, document)
        self.writer.write(documents)
        return summary

    def _held(self, summary: BundleSummary) -> list[Regulation]:
        held = []
        for record_id in sorted(all_targets(self.repository, self.catalog)):
            regulation = self.repository.regulation(record_id)
            if regulation is None:
                summary.missing.append(record_id)
            else:
                held.append(regulation)
        return held

    def _document(self, regulation: Regulation, ids: dict[str, str]) -> BundleDocument | None:
        files = self._files(regulation)
        if not files:
            return None
        canonical = national_id(regulation)
        return BundleDocument(
            regulation=regulation,
            canonical_id=canonical,
            id_conflict=canonical is not None and ids.get(regulation.record_id) != canonical,
            standing=standing(regulation),
            files=files,
            citations=_citations(regulation, ids),
            fetched_at=max(file.stored.fetched_at for file in files if file.stored.fetched_at),
        )

    def _files(self, regulation: Regulation) -> tuple[BundleFile, ...]:
        files, roles = [], file_roles(regulation.files)
        for ref in regulation.files:
            stored = self.repository.file_state(regulation.record_id, ref.path)
            if stored is None:
                continue
            text = self.repository.text_state(stored.sha256)
            files.append(BundleFile(ref, stored, text if text and text.text_sha256 else None, roles[ref.path]))
        return tuple(files)


def _first_claims(held: list[Regulation]) -> dict[str, str]:
    """Record ID → canonical ID, for the first record (lowest record ID) to claim each ID."""
    claimed: dict[str, str] = {}
    for regulation in held:
        canonical = national_id(regulation)
        if canonical and canonical not in claimed.values():
            claimed[regulation.record_id] = canonical
    return claimed


def _citations(regulation: Regulation, ids: dict[str, str]) -> tuple[BundleCitation, ...]:
    return tuple(
        BundleCitation(
            relation=name,
            kind=relation.kind,
            citation=relation.citation,
            about=relation.about,
            target_id=ids.get(relation.record_id) or cited_id(relation.citation),
        )
        for relation, name in outgoing(regulation)
    )


def _count(summary: BundleSummary, document: BundleDocument) -> None:
    summary.documents += 1
    summary.texts += sum(file.text is not None for file in document.files)
    summary.unresolved += document.canonical_id is None or document.id_conflict
    summary.citations += len(document.citations)
    summary.citations_with_target += sum(c.target_id is not None for c in document.citations)
