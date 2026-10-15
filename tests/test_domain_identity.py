"""Canonical IDs for national regulations: `id:{family}:{year}:{n}`, shared with every other connector."""

from __future__ import annotations

import pytest

from bpk_connector.domain.identity import cited_id, national_id
from bpk_connector.domain.models import Regulation


def regulation(form: str, number: str, year: str = "2023") -> Regulation:
    return Regulation("1", "t", form, number, year)


@pytest.mark.parametrize(
    ("form", "number", "year", "expected"),
    [
        ("UU", "4", "2023", "id:uu:2023:4"),
        ("Perpu", "2", "2022", "id:perppu:2022:2"),  # the family OJK's citations already use
        ("PP", "05", "2021", "id:pp:2021:5"),
        ("Perpres", "10", "2021", "id:perpres:2021:10"),
        ("PMK", "130/PMK.010/2012", "2012", "id:pmk:2012:130"),
        ("Permenko Perekonomian", "7", "2021", "id:permenko-perekonomian:2021:7"),
        ("Permeninves/BKPM", "4", "2021", "id:permeninves-bkpm:2021:4"),
        ("Perka PPATK", "PER-02/1.02/PPATK/02/15", "2015", "id:perka-ppatk:2015:per-02-1.02-ppatk-02-15"),
    ],
)
def test_national_id(form, number, year, expected):
    assert national_id(regulation(form, number, year)) == expected


def test_a_record_without_a_number_or_year_has_no_id():
    assert national_id(regulation("UU", "", "2023")) is None
    assert national_id(regulation("UU", "4", "")) is None


@pytest.mark.parametrize(
    ("citation", "expected"),
    [
        ("UU No. 4 Tahun 2026", "id:uu:2026:4"),
        ("PERPU No. 2 Tahun 2022", "id:perppu:2022:2"),
        ("PERPRES No. 10 Tahun 2021", "id:perpres:2021:10"),
        ("KEPPRES No. 3 Tahun 2019", "id:keppres:2019:3"),
        ("PMK No. 130/PMK.010/2012", "id:pmk:2012:130"),
        ("UUDrt No. 7 Tahun 1955", "id:uudrt:1955:7"),
        ("Pasal 33 UUD 1945", None),
    ],
)
def test_the_id_a_relation_names(citation, expected):
    """BPK writes the other regulation as "{form} No. {number}[ Tahun {year}]"."""
    assert cited_id(citation) == expected
