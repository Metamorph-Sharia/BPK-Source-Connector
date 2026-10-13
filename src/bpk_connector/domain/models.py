"""Records the rest of the connector shares: a BPK regulation, its links and files, and our targets.

Pure data and rules; nothing here knows about HTTP, HTML or storage. There is no canonical
ID (decision D4): a regulation is keyed by BPK's own record ID, and BPK's fields travel
unchanged in ``fields`` beside the few typed values we need ourselves.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

IN_FORCE = "Berlaku"
NOT_IN_FORCE = "Tidak Berlaku"


@dataclass(frozen=True)
class Relation:
    """One line of BPK's "Status Peraturan": e.g. this regulation *Diubah dengan* (is amended by) another."""

    kind: str  # BPK's label, unchanged: "Diubah dengan", "Mencabut", …
    record_id: str  # the other regulation's BPK record ID
    citation: str  # as BPK writes it, e.g. "UU No. 4 Tahun 2026"
    about: str = ""  # the other regulation's subject

    @property
    def summary(self) -> dict[str, str]:
        return {"kind": self.kind, "record_id": self.record_id, "citation": self.citation}


@dataclass(frozen=True)
class FileRef:
    """A file BPK offers for a regulation."""

    file_id: str
    name: str
    path: str  # site-relative download path, e.g. "/Download/295189/UU Nomor 4 Tahun 2023.pdf"
    category: str = "Peraturan"  # BPK's data-kategori: the regulation itself, or e.g. a judicial review ruling

    @property
    def summary(self) -> dict[str, str]:
        return {"file_id": self.file_id, "name": self.name, "category": self.category}


@dataclass(frozen=True)
class Regulation:
    """One BPK record, as its detail page shows it."""

    record_id: str
    title: str
    form: str  # "Bentuk Singkat", e.g. "PMK", "Permenkum"
    number: str  # "Nomor", unchanged: "49" or "130/PMK.010/2012"
    year: str
    issuer: str = ""  # "T.E.U."
    status: str = ""  # "Berlaku" / "Tidak Berlaku"
    subjects: tuple[str, ...] = ()
    enacted_on: date | None = None
    promulgated_on: date | None = None
    effective_on: date | None = None
    relations: tuple[Relation, ...] = ()
    files: tuple[FileRef, ...] = ()
    fields: Mapping[str, Any] = field(default_factory=dict)  # every metadata field, BPK's labels and values unchanged

    @property
    def citation(self) -> str:
        """For people and reports, not an identifier: "Permenkum 49/2025", "PMK 130/PMK.010/2012"."""
        if "/" in self.number:
            return f"{self.form} {self.number}"
        return f"{self.form} {self.number}/{self.year}"

    @property
    def in_force(self) -> bool | None:
        return {IN_FORCE: True, NOT_IN_FORCE: False}.get(self.status)


class Tier(StrEnum):
    P1 = "P1"  # core: the entry route and day-to-day obligations
    P2 = "P2"  # cross-cutting compliance
    P3 = "P3"  # lineage and context


class TargetOrigin(StrEnum):
    SEED = "seed"  # curated in the target list
    APPROVED = "approved"  # a reviewed candidate
    LINEAGE = "lineage"  # added by the expansion rule: amends, revokes or is amended by a target


@dataclass(frozen=True)
class Target:
    """A regulation we collect."""

    record_id: str
    tier: Tier
    origin: TargetOrigin
    domain: str = ""  # target-list domain letter, e.g. "B"
    via: str | None = None  # for lineage: the target whose link added this one
    note: str = ""
    historical: bool = False  # added as an older version of a target: kept for history, never expanded


@dataclass(frozen=True)
class ChangeEvent:
    kind: str  # e.g. "status_changed", "relation_added"
    record_id: str
    detail: Mapping[str, Any] = field(default_factory=dict)
