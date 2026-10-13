"""Change detection: what differs between two observations of the same BPK record."""

from __future__ import annotations

from dataclasses import replace

from bpk_connector.domain.changes import diff, fingerprint, one_sided_links
from bpk_connector.domain.models import FileRef, Regulation, Relation

P2SK = Regulation(
    "240203",
    "Pengembangan dan Penguatan Sektor Keuangan",
    "UU",
    "4",
    "2023",
    status="Berlaku",
    files=(FileRef("295189", "UU Nomor 4 Tahun 2023.pdf", "/Download/295189/x.pdf"),),
    fields={"Judul": "UU 4/2023", "Status": "Berlaku"},
)
AMENDED_BY_UU_4_2026 = Relation("Diubah dengan", "350166", "UU No. 4 Tahun 2026")


def kinds(events) -> list[str]:
    return [e.kind for e in events]


def test_a_record_seen_for_the_first_time_is_new() -> None:
    assert kinds(diff(None, P2SK)) == ["new_record"]


def test_an_unchanged_record_has_no_events() -> None:
    assert diff(P2SK, P2SK) == []


def test_a_new_amendment_link_is_reported_with_its_target() -> None:
    events = diff(P2SK, replace(P2SK, relations=(AMENDED_BY_UU_4_2026,)))

    assert kinds(events) == ["relation_added"]
    assert events[0].detail == {"kind": "Diubah dengan", "record_id": "350166", "citation": "UU No. 4 Tahun 2026"}


def test_a_status_flip_is_reported_with_old_and_new_values() -> None:
    revoked = replace(P2SK, status="Tidak Berlaku", fields={**P2SK.fields, "Status": "Tidak Berlaku"})

    events = diff(P2SK, revoked)

    assert kinds(events) == ["status_changed"]
    assert events[0].detail == {"from": "Berlaku", "to": "Tidak Berlaku"}


def test_added_and_removed_files_are_reported() -> None:
    ruling = FileRef("242", "putusan_mkri.pdf", "/DownloadUjiMateri/242/x.pdf", category="Uji Materi")

    events = diff(P2SK, replace(P2SK, files=(ruling,)))

    assert kinds(events) == ["file_added", "file_removed"]


def test_edited_fields_are_listed_by_label() -> None:
    edited = replace(P2SK, fields={**P2SK.fields, "Judul": "corrected title"})

    events = diff(P2SK, edited)

    assert kinds(events) == ["metadata_changed"]
    assert events[0].detail == {"fields": ["Judul"]}


def test_the_fingerprint_changes_exactly_when_something_worth_refetching_changes() -> None:
    assert fingerprint(P2SK) == fingerprint(replace(P2SK))
    assert fingerprint(P2SK) != fingerprint(replace(P2SK, relations=(AMENDED_BY_UU_4_2026,)))
    assert fingerprint(P2SK) != fingerprint(replace(P2SK, fields={**P2SK.fields, "Judul": "x"}))


def test_a_link_bpk_shows_on_only_one_side_is_found() -> None:
    # Shaped like the live case: Permenkumham 1/2016 lists 21/2021 as "amended by"; 21/2021 only says "Mencabut".
    core_tax = Regulation(
        "306614", "t", "PMK", "81", "2024", relations=(Relation("Diubah dengan", "326338", "PMK 53/2025"),)
    )
    other = Regulation("326338", "t", "PMK", "53", "2025", relations=(Relation("Mengubah", "999", "PMK 11/2025"),))

    assert one_sided_links({"306614": core_tax, "326338": other}) == [("306614", core_tax.relations[0])]


def test_matching_links_on_both_sides_and_links_to_unobserved_records_are_fine() -> None:
    old = Regulation(
        "1",
        "t",
        "PP",
        "1",
        "2020",
        relations=(Relation("Dicabut dengan", "2", "PP 2/2025"), Relation("Diubah dengan", "3", "x")),
    )
    new = Regulation("2", "t", "PP", "2", "2025", relations=(Relation("Mencabut", "1", "PP 1/2020"),))

    assert one_sided_links({"1": old, "2": new}) == []  # "3" was never observed: nothing to compare
