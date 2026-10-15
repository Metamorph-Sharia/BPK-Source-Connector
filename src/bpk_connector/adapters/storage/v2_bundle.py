"""BundleDocuments → one contract v2 bundle (metamorph_contract), the platform loader's input.

The use case decides what goes in (ExportBundle); this adapter only speaks the contract:
its types, its file layout, and its spelling of kinds, roles and statuses.
"""

from __future__ import annotations

import re
from pathlib import Path

from metamorph_contract import (
    BundleWriter,
    Citation,
    Confidence,
    Dates,
    DocumentInfo,
    ExtractionMethod,
    FileRef,
    FileRole,
    FoundIn,
    Kind,
    NormalizedDocument,
    Relation,
    Rights,
    SourceRef,
    Status,
    StatusClaim,
    TextOrigin,
    TextRef,
    unresolved_id,
)

from bpk_connector.application.dto import BundleCitation, BundleDocument, BundleFile
from bpk_connector.application.ports import BlobStore
from bpk_connector.application.use_cases.export_corpus import DETAILS_URL, MAIN_CATEGORY, SOURCE
from bpk_connector.domain.identity import ISSUER, family_of, source_id

LAW_FAMILIES = {"uu", "perppu", "uudrt"}  # everything else BPK holds is a regulation below a law
ALIAS_SEPARATOR = " • "
_SUBJECT = re.compile(r"\s+tentang\s+(.+)$", re.IGNORECASE | re.DOTALL)
_FORM_IN_BRACKETS = re.compile(r"\s*\([^)]*\)")


class V2BundleWriter:
    def __init__(self, directory: Path, blobs: BlobStore, *, run_id: str, connector_version: str) -> None:
        self.directory = directory
        self.blobs = blobs
        self.run_id = run_id
        self.connector_version = connector_version

    def write(self, documents: list[BundleDocument]) -> None:
        with BundleWriter(
            self.directory, connector=SOURCE, connector_version=self.connector_version, run_id=self.run_id
        ) as bundle:
            for document in documents:
                for file in document.files:
                    bundle.put_blob(self.blobs.get(file.stored.sha256))
                    if file.text:
                        bundle.put_blob(self.blobs.get(file.text.text_sha256))
                bundle.add(self._normalized(document))

    def _normalized(self, document: BundleDocument) -> NormalizedDocument:
        regulation = document.regulation
        return NormalizedDocument(
            source=SourceRef(
                connector=SOURCE,
                connector_version=self.connector_version,
                source_id=source_id(regulation.record_id),
                url=DETAILS_URL.format(regulation.record_id),
                fetched_at=document.fetched_at.isoformat(),
            ),
            document=_document_info(document),
            files=tuple(_file_ref(file) for file in document.files),
            texts=tuple(_text_ref(file) for file in document.files if file.text),
            citations=tuple(_citation(citation) for citation in document.citations),
            source_fields={
                "record_id": regulation.record_id,
                "issuer": regulation.issuer,
                "subjects": list(regulation.subjects),
                "relations": [relation.summary | {"about": relation.about} for relation in regulation.relations],
                "fields": dict(regulation.fields),
            },
        )


def _document_info(document: BundleDocument) -> DocumentInfo:
    regulation = document.regulation
    family = family_of(regulation.form)
    return DocumentInfo(
        id=_document_id(document),
        id_confidence=_confidence(document),
        id_evidence=f"BPK record {regulation.record_id}: {regulation.form} {regulation.number} ({regulation.year})",
        issuer=ISSUER,
        family=family,
        number=regulation.number or "?",
        year=int(regulation.year) if regulation.year.isdigit() else None,
        citation=_citation_text(regulation.form, regulation.number, regulation.year),
        title=_subject(regulation.title),
        language="id",
        kind=Kind.LAW if family in LAW_FAMILIES else Kind.REGULATION,
        status=StatusClaim(value=Status(document.standing), source=SOURCE),
        dates=Dates(
            enacted=_iso(regulation.enacted_on),
            promulgated=_iso(regulation.promulgated_on),
            effective=_iso(regulation.effective_on),
        ),
        aliases=_aliases(regulation.fields.get("Alias", ""), regulation.title),
    )


def _document_id(document: BundleDocument) -> str:
    if document.canonical_id is None or document.id_conflict:
        return unresolved_id(SOURCE, document.regulation.record_id)
    return document.canonical_id


def _confidence(document: BundleDocument) -> Confidence:
    if document.canonical_id is None:
        return Confidence.NONE
    return Confidence.CONFLICT if document.id_conflict else Confidence.HIGH


def _citation_text(form: str, number: str, year: str) -> str:
    """BPK's way of citing: "UU No. 4 Tahun 2023"; numbers that carry their year stand alone."""
    return f"{form} No. {number}" if "/" in number else f"{form} No. {number} Tahun {year}"


def _subject(title: str) -> str:
    found = _SUBJECT.search(title)
    return " ".join((found[1] if found else title).split())


def _aliases(bpk_aliases: str, title: str) -> tuple[str, ...]:
    """BPK's own list ("UU No. 4 Tahun 2023 • UU 4/2023 • …"), and the full name from the title."""
    listed = [alias.strip() for alias in bpk_aliases.split(ALIAS_SEPARATOR) if alias.strip()]
    full_name = _FORM_IN_BRACKETS.sub("", _SUBJECT.sub("", title)).strip()
    return tuple(dict.fromkeys([*listed, *([full_name] if full_name else [])]))


def _file_ref(file: BundleFile) -> FileRef:
    is_main = file.ref.category == MAIN_CATEGORY
    return FileRef(
        sha256=file.stored.sha256,
        role=FileRole.MAIN if is_main else FileRole.OTHER,  # e.g. a Constitutional Court judicial-review ruling
        media_type=file.stored.media_type,
        source_url=file.stored.url,
        rights=Rights.PUBLIC,
        title=None if is_main else file.ref.name,
        pages=file.text.pages if file.text and file.text.pages else None,
    )


def _text_ref(file: BundleFile) -> TextRef:
    return TextRef(
        sha256=file.text.text_sha256,
        language="id",
        origin=TextOrigin.SELF_EXTRACTED,
        method=ExtractionMethod(file.text.method),
        rights=Rights.PUBLIC,
        paged=True,
        of_file=file.stored.sha256,
    )


def _citation(citation: BundleCitation) -> Citation:
    about = f" ({citation.about})" if citation.about else ""
    return Citation(
        relation=Relation(citation.relation),
        target_text=citation.citation,
        evidence=f'BPK "Status Peraturan": {citation.kind} {citation.citation}{about}',
        found_in=FoundIn.SOURCE_METADATA,
        confidence=Confidence.HIGH,
        target_id=citation.target_id,
    )


def _iso(value) -> str | None:
    return value.isoformat() if value else None
