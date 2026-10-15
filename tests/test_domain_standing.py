"""What BPK's "Status Peraturan" says, in the platform's terms: a regulation's standing and what it does to others."""

from __future__ import annotations

import pytest

from bpk_connector.domain.models import Regulation, Relation
from bpk_connector.domain.standing import outgoing, standing


def regulation(status: str, *kinds: str) -> Regulation:
    relations = tuple(Relation(kind, str(i), f"UU No. {i} Tahun 2020") for i, kind in enumerate(kinds))
    return Regulation("1", "t", "UU", "4", "2023", status=status, relations=relations)


@pytest.mark.parametrize(
    ("status", "kinds", "expected"),
    [
        ("Berlaku", (), "in_force"),
        ("Berlaku", ("Diubah dengan",), "amended"),
        ("Berlaku", ("Diubah dengan", "Dicabut sebagian dengan"), "partly_revoked"),
        ("Berlaku", ("Mengubah", "Mencabut"), "in_force"),  # what it does to others says nothing of its own standing
        ("Tidak Berlaku", ("Diubah dengan",), "revoked"),
        ("", (), "unknown"),
    ],
)
def test_standing(status, kinds, expected):
    assert standing(regulation(status, *kinds)) == expected


def test_only_what_this_regulation_does_to_others_is_its_own_citation():
    """BPK's "Diubah dengan X" is X's claim; X's own record says "Mengubah", and that is where the link comes from."""
    record = regulation("Berlaku", "Mengubah", "Diubah dengan", "Mencabut", "Mencabut sebagian", "Dicabut dengan")

    assert [(relation.kind, name) for relation, name in outgoing(record)] == [
        ("Mengubah", "amends"),
        ("Mencabut", "revokes"),
        ("Mencabut sebagian", "partly_revokes"),
    ]


def test_a_relation_bpk_lists_twice_is_cited_once():
    twice = Relation("Mengubah", "37298", "UU No. 9 Tahun 2016")
    record = Regulation("1", "t", "UU", "4", "2023", relations=(twice, twice))

    assert len(outgoing(record)) == 1
