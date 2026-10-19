"""ExportBundle: every target we hold, identified and linked, handed to the platform's bundle writer."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from fakes.memory import MemoryBundleWriter, MemoryCatalog, MemoryRepository

from bpk_connector.application.dto import Method, StoredFile, StoredText
from bpk_connector.application.use_cases.export_bundle import ExportBundle
from bpk_connector.domain.file_roles import FileRole
from bpk_connector.domain.models import FileRef, Regulation, Relation, Target, TargetOrigin, Tier

EARLIER, LATER = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 12, tzinfo=UTC)
LAW = FileRef("295189", "UU Nomor 4 Tahun 2023.pdf", "/Download/295189/UU.pdf")
RULING = FileRef("300001", "Putusan MK.pdf", "/Download/300001/MK.pdf", category="UjiMateri")
P2SK = Regulation(
    "240203", "Undang-undang (UU) Nomor 4 Tahun 2023 tentang P2SK", "UU", "4", "2023", status="Berlaku",
    relations=(
        Relation("Diubah dengan", "350166", "UU No. 4 Tahun 2026"),
        Relation("Mengubah", "38785", "UU No. 40 Tahun 2014", "Perasuransian"),
        Relation("Mencabut", "46603", "UU No. 11 Tahun 1992", "Dana Pensiun"),
    ),
    files=(LAW, RULING),
)  # fmt: skip
INSURANCE = Regulation("38785", "UU 40/2014 tentang Perasuransian", "UU", "40", "2014", status="Berlaku")


def seed(*record_ids: str) -> MemoryCatalog:
    return MemoryCatalog([Target(record_id, Tier.P1, TargetOrigin.SEED) for record_id in record_ids])


def hold(repository: MemoryRepository, regulation: Regulation, *files: tuple[FileRef, datetime, bool]) -> None:
    repository.observations[regulation.record_id] = regulation
    for ref, fetched_at, with_text in files:
        sha = ref.file_id * 4
        repository.stored_files[(regulation.record_id, ref.path)] = StoredFile(
            sha, None, 8, "application/pdf", f"https://bpk{ref.path}", fetched_at=fetched_at
        )
        if with_text:
            repository.texts[sha] = StoredText(sha, f"text-{sha}", Method.TEXT_LAYER, pages=2)


def export(repository: MemoryRepository, catalog: MemoryCatalog) -> tuple[MemoryBundleWriter, object]:
    writer = MemoryBundleWriter()
    summary = ExportBundle(repository, catalog, writer).run()
    return writer, summary


def test_a_held_target_is_identified_with_its_standing_files_and_texts() -> None:
    repository = MemoryRepository()
    hold(repository, P2SK, (LAW, EARLIER, True), (RULING, LATER, False))

    writer, summary = export(repository, seed("240203"))

    document = writer.by_record()["240203"]
    assert (document.canonical_id, document.id_conflict, document.standing) == ("id:uu:2023:4", False, "amended")
    assert [f.ref.category for f in document.files] == ["Peraturan", "UjiMateri"]
    assert [f.text is not None for f in document.files] == [True, False]
    assert document.fetched_at == LATER
    assert (summary.documents, summary.texts) == (1, 1)


def test_each_file_carries_its_role_so_annex_volumes_are_not_read_as_the_regulation() -> None:
    annex = FileRef("394931", "2.2 Lampiran I.B PP Nomor 28 Tahun 2025 (I.B.1-810).pdf", "/Download/394931/I.B.pdf")
    repository = MemoryRepository()
    hold(repository, replace(P2SK, files=(LAW, annex, RULING)), (LAW, EARLIER, True), (annex, EARLIER, True),
         (RULING, LATER, False))  # fmt: skip

    writer, _ = export(repository, seed("240203"))

    assert [f.role for f in writer.by_record()["240203"].files] == [FileRole.MAIN, FileRole.ANNEX, FileRole.OTHER]


def test_citations_point_at_held_records_or_at_the_id_bpk_s_citation_names() -> None:
    repository = MemoryRepository()
    hold(repository, P2SK, (LAW, EARLIER, True))
    hold(repository, INSURANCE, (FileRef("9", "UU 40.pdf", "/Download/9/UU.pdf"), EARLIER, False))

    writer, summary = export(repository, seed("240203", "38785"))

    citations = writer.by_record()["240203"].citations
    assert [(c.relation, c.target_id) for c in citations] == [("amends", "id:uu:2014:40"), ("revokes", "id:uu:1992:11")]
    assert (summary.citations, summary.citations_with_target) == (2, 2)


def test_a_target_without_a_stored_file_has_no_content_to_hand_over() -> None:
    repository = MemoryRepository()
    hold(repository, P2SK)

    writer, summary = export(repository, seed("240203"))

    assert writer.written == []
    assert summary.without_content == ["240203"]


def test_a_target_never_observed_is_missing() -> None:
    writer, summary = export(MemoryRepository(), seed("1"))

    assert writer.written == [] and summary.missing == ["1"]


def test_two_records_claiming_one_id_keep_it_for_the_first_and_flag_the_second() -> None:
    repository = MemoryRepository()
    duplicate = Regulation("999999", "UU 4/2023 (salinan)", "UU", "4", "2023", status="Berlaku", files=(LAW,))
    hold(repository, P2SK, (LAW, EARLIER, False))
    hold(repository, duplicate, (LAW, EARLIER, False))

    writer, summary = export(repository, seed("240203", "999999"))

    by_record = writer.by_record()
    assert by_record["240203"].id_conflict is False
    assert by_record["999999"].id_conflict is True
    assert summary.unresolved == 1
