"""What each file is to its regulation, from the files BPK actually holds (2026-10-16)."""

from __future__ import annotations

from bpk_connector.domain.file_roles import FileRole, file_roles
from bpk_connector.domain.models import FileRef


def ref(file_id: str, name: str, category: str = "Peraturan") -> FileRef:
    return FileRef(file_id, name, f"/Download/{file_id}/{name}", category)


def test_annex_volumes_filed_as_the_regulation_are_annexes() -> None:
    # PP 28/2025: the regulation, then 21 annex volumes BPK also files under "Peraturan"
    law = ref("381375", "PP Nomor 28 Tahun 2025.pdf")
    kbli = ref("394931", "2.2 Lampiran I.B PP Nomor 28 Tahun 2025 (I.B.1-810).pdf")
    last = ref("394950", "PP Nomor 28 Tahun 2025 - Lampiran IV.pdf")

    roles = file_roles([law, kbli, last])

    assert roles == {law.path: FileRole.MAIN, kbli.path: FileRole.ANNEX, last.path: FileRole.ANNEX}


def test_every_way_bpk_spells_an_annex_is_recognised() -> None:
    law = ref("1", "Peraturan-PPATK-Nomor-11-Tahun-2020.pdf")
    names = [
        "Lampiran-Peraturan-PPATK-Nomor-11-Tahun-2020.pdf",
        "2021._4_Salinan_Lampiran_Pelayanan_.pdf",
        "6._2020_Peraturan_BKPM_Lampiran_.pdf",
        "Perpres Nomor 10 Tahun 2021 - Lampiran.zip",
        "Perpres Nomor 82 Tahun 2016 - Lampiran-.pdf",
    ]
    annexes = [ref(str(n), name) for n, name in enumerate(names, start=2)]

    roles = file_roles([law, *annexes])

    assert [roles[a.path] for a in annexes] == [FileRole.ANNEX] * len(names)


def test_a_separate_elucidation_stays_part_of_the_regulation() -> None:
    law, elucidation = ref("1", "PP Nomor 5 Tahun 2021.pdf"), ref("2", "PP Nomor 5 Tahun 2021_penjelasan.pdf")

    assert set(file_roles([law, elucidation]).values()) == {FileRole.MAIN}


def test_judicial_review_rulings_are_other_files() -> None:
    ruling = ref("160", "13_PUU-XV_2017.pdf", category="UjiMateri")

    assert file_roles([ref("1", "UU Nomor 1 Tahun 2023.pdf"), ruling])[ruling.path] == FileRole.OTHER


def test_a_regulation_whose_only_file_is_named_as_an_annex_keeps_it_as_its_main_file() -> None:
    # e.g. one PDF holding the regulation and its annex: demoting it would leave the regulation without text
    combined = ref("1", "PMK Nomor 5 Tahun 2020 beserta Lampiran.pdf")

    assert file_roles([combined]) == {combined.path: FileRole.MAIN}
