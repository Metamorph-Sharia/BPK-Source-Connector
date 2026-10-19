"""ExportCorpus: rebuild the corpus from what we hold. One folder per target, readable offline.

Keyed by BPK's record ID: there is no cross-agency ID yet (decision D4). BPK's fields go in
unchanged; BPK's editorial abstract is not exported (it is BPK's text, kept only in the raw page).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from bpk_connector.application.dto import SELF_EXTRACTED_TEXT, CorpusDocument
from bpk_connector.application.ports import Clock, CorpusWriter, Repository, TargetCatalog
from bpk_connector.application.targets import all_targets
from bpk_connector.domain.file_roles import FileRole, file_roles
from bpk_connector.domain.models import FileRef, Regulation, Target

SOURCE = "bpk"
DETAILS_URL = "https://peraturan.bpk.go.id/Details/{}"
FILE_RIGHTS = "public"  # official regulatory instruments, court rulings, and text we extract from them
MAIN_TEXT = "text.id.md"


@dataclass
class ExportSummary:
    documents: int = 0
    files: int = 0
    missing: list[str] = field(default_factory=list)


class ExportCorpus:
    def __init__(self, repository: Repository, catalog: TargetCatalog, writer: CorpusWriter, clock: Clock) -> None:
        self.repository = repository
        self.catalog = catalog
        self.writer = writer
        self.clock = clock

    def run(self) -> ExportSummary:
        summary = ExportSummary()
        documents = []
        for target in all_targets(self.repository, self.catalog).values():
            regulation = self.repository.regulation(target.record_id)
            if regulation is None:
                summary.missing.append(target.record_id)
                continue
            document = self._document(target, regulation)
            documents.append(document)
            summary.documents += 1
            summary.files += len(document.files)
        self.writer.write(documents)
        return summary

    def _document(self, target: Target, regulation: Regulation) -> CorpusDocument:
        files, local, main_texts = [], [], []
        roles = file_roles(regulation.files)
        for ref in regulation.files:
            entry, placed = self._file_entry(regulation.record_id, ref, roles[ref.path])
            files.append(entry)
            local += placed
            if roles[ref.path] is FileRole.MAIN:
                main_texts += [sha for path, sha in placed if path.startswith("texts/")]
        if main_texts:
            local.append((MAIN_TEXT, main_texts[0]))
        return CorpusDocument(regulation.record_id, self._metadata(target, regulation, files), tuple(local))

    def _file_entry(self, record_id: str, ref: FileRef, role: FileRole) -> tuple[dict, list[tuple[str, str]]]:
        """The file's metadata, and the blobs to place beside it: the file itself and its extracted text."""
        stored = self.repository.file_state(record_id, ref.path)
        entry = {**ref.summary, "role": role, "url": None, "sha256": None, "size": None, "media_type": None}
        entry |= {"path": None, "rights": FILE_RIGHTS, "text": None}
        if stored is None:
            return entry, []
        path = f"files/{ref.category}-{ref.file_id}{_extension(ref.name)}"
        entry |= {"url": stored.url, "sha256": stored.sha256, "size": stored.size, "media_type": stored.media_type}
        entry["path"] = path
        placed = [(path, stored.sha256)]
        text = self.repository.text_state(stored.sha256)
        if text and text.text_sha256:
            text_path = f"texts/{ref.category}-{ref.file_id}.id.md"
            entry["text"] = {
                "path": text_path,
                "method": text.method,
                "pages": text.pages,
                "coverage": text.coverage,
            } | SELF_EXTRACTED_TEXT
            placed.append((text_path, text.text_sha256))
        return entry, placed

    def _metadata(self, target: Target, regulation: Regulation, files: list[dict]) -> dict:
        return {
            "source": {
                "name": SOURCE,
                "record_id": regulation.record_id,
                "url": DETAILS_URL.format(regulation.record_id),
            },
            "citation": regulation.citation,
            "title": regulation.title,
            "form": regulation.form,
            "number": regulation.number,
            "year": regulation.year,
            "status": regulation.status,
            "in_force": regulation.in_force,
            "issuer": regulation.issuer,
            "subjects": list(regulation.subjects),
            "dates": {
                "enacted": _iso(regulation.enacted_on),
                "promulgated": _iso(regulation.promulgated_on),
                "effective": _iso(regulation.effective_on),
            },
            "relations": [r.summary | {"about": r.about} for r in regulation.relations],
            "files": files,
            "target": {
                "tier": target.tier.value,
                "domain": target.domain,
                "origin": target.origin.value,
                "via": target.via,
                "note": target.note,
            },
            "fields": dict(regulation.fields),
            "exported_at": self.clock.now().isoformat(),
        }


def _extension(name: str) -> str:
    """The file's own extension (".pdf", ".zip", ".PDF" → ".pdf"); ".pdf" when the name has none."""
    suffix = PurePosixPath(name).suffix.lower()
    return suffix if 1 < len(suffix) <= 5 else ".pdf"


def _iso(value) -> str | None:
    return value.isoformat() if value else None
