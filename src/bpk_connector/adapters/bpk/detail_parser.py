"""BPK detail page (``/Details/{id}``) → ``Regulation``.

Matches the page's structure, not literal headings (headings carry markup, e.g.
``STATUS <span>PERATURAN</span>``). Every metadata field is kept with BPK's label and
value unchanged; a few are also typed for our own use.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from bpk_connector.domain.models import FileRef, Regulation, Relation

MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}  # fmt: skip
SUBJECT_SEPARATOR = " - "  # subjects themselves contain commas
DETAILS_LINK = re.compile(r"^/Details/(\d+)")


def parse_detail(record_id: str, html: bytes | str) -> Regulation:
    soup = BeautifulSoup(html, "html.parser")
    fields = _metadata_fields(soup)
    return Regulation(
        record_id=record_id,
        title=fields.get("Judul", ""),
        form=fields.get("Bentuk Singkat", ""),
        number=fields.get("Nomor", ""),
        year=fields.get("Tahun", ""),
        issuer=fields.get("T.E.U.", ""),
        status=fields.get("Status", ""),
        subjects=tuple(s.strip() for s in fields.get("Subjek", "").split(SUBJECT_SEPARATOR) if s.strip()),
        enacted_on=parse_indonesian_date(fields.get("Tanggal Penetapan", "")),
        promulgated_on=parse_indonesian_date(fields.get("Tanggal Pengundangan", "")),
        effective_on=parse_indonesian_date(fields.get("Tanggal Berlaku", "")),
        relations=tuple(_relations(soup)),
        files=tuple(_files(soup)),
        fields=fields,
    )


def parse_indonesian_date(text: str) -> date | None:
    """ "07 Agustus 2012" → 2012-08-07; anything else → None (BPK data has gaps and errors)."""
    match = re.fullmatch(r"(\d{1,2}) (\w+) (\d{4})", text.strip())
    if not match or match.group(2).lower() not in MONTHS:
        return None
    try:
        return date(int(match.group(3)), MONTHS[match.group(2).lower()], int(match.group(1)))
    except ValueError:
        return None


def _metadata_fields(soup: BeautifulSoup) -> dict[str, str]:
    fields = {}
    for label in soup.select("div.col-lg-3.fw-bold"):
        value = label.find_next_sibling("div")
        fields[_text(label)] = _text(value) if value else ""
    return fields


def _relations(soup: BeautifulSoup) -> list[Relation]:
    relations = []
    for label in soup.select("div.col-12.fw-semibold.bg-light-primary"):
        kind = _text(label).rstrip(":").strip()
        listing = label.find_parent("div", class_="row").find_next_sibling("div")
        for item in listing.select("li") if listing else []:
            link = item.find("a", href=DETAILS_LINK)
            if link:
                relations.append(Relation(kind, DETAILS_LINK.match(link["href"]).group(1), _text(link), _about(item)))
    return relations


def _about(item: Tag) -> str:
    text = _text(item)
    return text.split(" tentang ", 1)[1].strip() if " tentang " in text else ""


def _files(soup: BeautifulSoup) -> list[FileRef]:
    files = {}
    for link in soup.select("a.download-file[data-id]"):
        path = link["href"]
        files[path] = FileRef(link["data-id"], unquote(path.rsplit("/", 1)[-1]), path, link.get("data-kategori", ""))
    return list(files.values())


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())
