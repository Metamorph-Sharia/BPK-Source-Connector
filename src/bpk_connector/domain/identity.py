"""Canonical IDs for national regulations, shared with the other connectors: `id:{family}:{year}:{n}`.

BPK's record ID stays the key inside this connector (decision D4). The canonical ID is how
the platform recognises a regulation whichever source describes it: an OJK regulation's
"Mengingat" names `id:uu:2011:21`, and this is where that law comes from.

    family   BPK's short form, lower-cased and hyphenated ("Permenko Perekonomian" →
             permenko-perekonomian), with BPK's spelling "Perpu" written "perppu" as elsewhere.
    n        the sequence: "130/PMK.010/2012" → 130 (numbers restart each year). A number that
             doesn't start with its sequence is kept whole, hyphenated.
"""

from __future__ import annotations

import re

from bpk_connector.domain.models import Regulation

ISSUER = "id"
FAMILY_SPELLING = {"perpu": "perppu"}

_SEPARATORS = re.compile(r"[\s/]+")
_SEQUENCE_FIRST = re.compile(r"^0*(\d+)(?:/|$)")
_YEAR = re.compile(r"^\d{4}$")
_CITED = re.compile(r"^(?P<form>\S.*?) No\. (?P<number>\S+)(?: Tahun (?P<year>\d{4}))?$")
_YEAR_AT_END = re.compile(r"/(\d{4})$")


def source_id(record_id: str) -> str:
    """The team interface's key for a BPK record (connector.py), and the bundle's source_id: the same record."""
    return f"bpk:{record_id}"


def national_id(regulation: Regulation) -> str | None:
    return _canonical(regulation.form, regulation.number, regulation.year)


def cited_id(citation: str) -> str | None:
    """The ID behind BPK's way of naming a related regulation: "UU No. 4 Tahun 2026", "PMK No. 130/PMK.010/2012"."""
    found = _CITED.match(citation.strip())
    if not found:
        return None
    year = found["year"] or _year_at_end(found["number"])
    return _canonical(found["form"], found["number"], year or "")


def family_of(form: str) -> str:
    family = _SEPARATORS.sub("-", form.strip().lower())
    return FAMILY_SPELLING.get(family, family)


def _canonical(form: str, number: str, year: str) -> str | None:
    if not form.strip() or not number.strip() or not _YEAR.match(year.strip()):
        return None
    return f"{ISSUER}:{family_of(form)}:{year.strip()}:{_sequence(number)}"


def _sequence(number: str) -> str:
    first = _SEQUENCE_FIRST.match(number.strip())
    return first[1] if first else _SEPARATORS.sub("-", number.strip().lower())


def _year_at_end(number: str) -> str | None:
    found = _YEAR_AT_END.search(number)
    return found[1] if found else None
