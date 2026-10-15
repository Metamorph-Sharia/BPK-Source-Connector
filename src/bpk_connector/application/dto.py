"""Plain data the adapters hand to the use cases. No HTTP, HTML or SQL objects cross inward."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from bpk_connector.domain.models import FileRef, Regulation


@dataclass(frozen=True)
class SitemapFile:
    """One entry of ``/sitemap.xml``: the sitemap of one regulation year."""

    year: str
    url: str
    lastmod: date | None


@dataclass(frozen=True)
class SitemapEntry:
    """One record in a yearly sitemap."""

    record_id: str
    slug: str  # unreliable (some are wrong); kept only to help people read logs
    lastmod: date | None


@dataclass(frozen=True)
class DetailPage:
    """A detail page: the bytes as served, and what we parsed from them."""

    html: bytes
    regulation: Regulation


@dataclass(frozen=True)
class Download:
    """A file download. ``content`` is None when the server said the file is unchanged (304)."""

    content: bytes | None
    etag: str | None
    media_type: str
    url: str
    last_modified: str | None = None

    @property
    def not_modified(self) -> bool:
        return self.content is None


@dataclass(frozen=True)
class StoredFile:
    """A file we hold: its bytes' hash, and the validators (ETag, Last-Modified) to ask BPK whether it changed."""

    sha256: str
    etag: str | None
    size: int
    media_type: str
    url: str
    last_modified: str | None = None  # BPK's judicial-review files have no ETag, only this
    fetched_at: datetime | None = None  # when we first held these bytes; None until saved


@dataclass(frozen=True)
class CorpusDocument:
    """One regulation for the corpus: its metadata, and which stored blobs to place beside it."""

    record_id: str
    metadata: dict
    files: tuple[tuple[str, str], ...]  # (path inside the document folder, sha256)


@dataclass(frozen=True)
class Candidate:
    """A record queued for a person to decide on."""

    record_id: str
    reason: str
    state: str  # open | approved | rejected
    found_on: date


class Method(StrEnum):
    """How a text was obtained. Stored as its string value."""

    TEXT_LAYER = "text_layer"  # the PDF's own text
    OCR = "ocr"  # some or all pages recognised from images
    UNSUPPORTED = "unsupported"  # not a document we can read


@dataclass(frozen=True)
class ExtractedText:
    """Indonesian text extracted from one official file, with how complete it is."""

    text: str  # pages separated by "<!-- page N -->" markers
    pages: int
    pages_without_text: int  # usually scanned pages: need OCR
    method: Method

    @property
    def coverage(self) -> float:
        return round(1 - self.pages_without_text / self.pages, 3) if self.pages else 0.0

    @property
    def needs_ocr(self) -> bool:
        return self.pages_without_text > 0


@dataclass(frozen=True)
class StoredText:
    """Text we extracted from one stored file (keyed by the file's sha256), or why we couldn't."""

    file_sha256: str
    text_sha256: str | None  # None when the file isn't extractable
    method: Method
    pages: int = 0
    pages_without_text: int = 0
    chars: int = 0
    note: str = ""

    @property
    def coverage(self) -> float:
        return round(1 - self.pages_without_text / self.pages, 3) if self.pages else 0.0


# Provenance of every text we extract: from an official file, in Indonesian, free to use.
SELF_EXTRACTED_TEXT = {"origin": "self_extracted", "rights": "public", "language": "id"}


@dataclass(frozen=True)
class BundleFile:
    """A file we hold for a regulation, and the text we extracted from it (None when there is none)."""

    ref: FileRef
    stored: StoredFile
    text: StoredText | None


@dataclass(frozen=True)
class BundleCitation:
    """Something this regulation does to another, per BPK: e.g. it amends "UU No. 9 Tahun 2016"."""

    relation: str  # contract v2's name: amends | revokes | partly_revokes | refers_to
    kind: str  # BPK's label, unchanged
    citation: str  # the other regulation, as BPK writes it
    about: str
    target_id: str | None  # its canonical ID, when we can tell


@dataclass(frozen=True)
class BundleDocument:
    """One regulation for the platform's contract v2 bundle."""

    regulation: Regulation
    canonical_id: str | None  # None when the record has no usable number or year
    id_conflict: bool  # another record we hold claims the same canonical ID
    standing: str  # contract v2's status name
    files: tuple[BundleFile, ...]
    citations: tuple[BundleCitation, ...]
    fetched_at: datetime  # when we first held the newest of its files
