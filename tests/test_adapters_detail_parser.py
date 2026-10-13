"""The detail-page parser, on real BPK pages saved in tests/fixtures/bpk/details/ (2026-10-13)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bpk_connector.adapters.bpk.detail_parser import parse_detail, parse_indonesian_date

DETAILS = Path(__file__).parent / "fixtures" / "bpk" / "details"
ALL_FIXTURES = sorted(p.stem for p in DETAILS.glob("*.html"))


def page(record_id: str):
    return parse_detail(record_id, (DETAILS / f"{record_id}.html").read_bytes())


@pytest.mark.parametrize("record_id", ALL_FIXTURES)
def test_every_seed_form_parses_its_core_fields(record_id: str) -> None:
    regulation = page(record_id)

    assert regulation.record_id == record_id
    assert regulation.title and regulation.form and regulation.number and regulation.year
    assert regulation.status in ("Berlaku", "Tidak Berlaku")
    assert regulation.promulgated_on or regulation.enacted_on
    assert len(regulation.fields) == 18  # every metadata label BPK shows, passed through unchanged


def test_old_style_pmk_with_its_revocation_and_file() -> None:
    pmk = page("164278")

    assert (pmk.form, pmk.number, pmk.year) == ("PMK", "130/PMK.010/2012", "2012")
    assert pmk.citation == "PMK 130/PMK.010/2012"
    assert pmk.in_force is False
    assert (pmk.enacted_on, pmk.promulgated_on, pmk.effective_on) == (
        date(2012, 8, 7),
        date(2012, 8, 7),
        date(2012, 10, 7),
    )
    assert [(r.kind, r.record_id, r.citation) for r in pmk.relations] == [
        ("Dicabut dengan", "112608", "PMK No. 23/PMK.010/2017")
    ]
    assert pmk.relations[0].about.startswith("Pencabutan Peraturan Menteri Keuangan")
    assert [(f.file_id, f.category) for f in pmk.files] == [("157089", "Peraturan")]
    assert pmk.files[0].path == "/Download/157089/PMK%20Nomor%20130%20Tahun%202012.pdf"
    assert pmk.subjects == ("PERLINDUNGAN USAHA, PERUSAHAAN, BADAN USAHA, PERDAGANGAN", "PERIZINAN, PELAYANAN PUBLIK")
    assert pmk.issuer == "Indonesia, Kementerian Keuangan"


def test_omnibus_law_keeps_every_link_and_its_judicial_review_rulings() -> None:
    p2sk = page("240203")

    assert ("Diubah dengan", "350166") in [(r.kind, r.record_id) for r in p2sk.relations]
    assert sum(r.kind == "Mengubah" for r in p2sk.relations) >= 20
    categories = sorted(f.category for f in p2sk.files)
    assert categories.count("Peraturan") == 1 and len(categories) == 5  # the law + 4 Constitutional Court rulings


def test_revoked_regulation_shows_what_revoked_it() -> None:
    pp = page("161835")

    assert pp.in_force is False
    assert ("Dicabut dengan", "319773") in [(r.kind, r.record_id) for r in pp.relations]


@pytest.mark.parametrize(
    "text, expected",
    [("07 Agustus 2012", date(2012, 8, 7)), ("1 Mei 2025", date(2025, 5, 1)), ("13 Januari 2026", date(2026, 1, 13))],
)
def test_indonesian_dates(text: str, expected: date) -> None:
    assert parse_indonesian_date(text) == expected


@pytest.mark.parametrize("text", ["", "-", "Agustus 2012", "31 Februari 2026"])
def test_unparseable_dates_are_none_not_errors(text: str) -> None:
    assert parse_indonesian_date(text) is None
