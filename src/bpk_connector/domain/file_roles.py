"""What each file BPK offers is to its regulation: the regulation itself, one of its annexes, or another file.

BPK files the regulation and each of its annex volumes under one category, "Peraturan" (PP 28/2025
has 21 annex volumes, KBLI tables of 182-1,056 pages). Read as the regulation, an annex fails
structure parsing with "no Pasal found": 29 review items on 2026-10-15. Only the file name tells
them apart, and BPK names every annex "Lampiran" (32 of 32 held). The first page can't: KBLI volumes
open mid-table, and some annexes open with their own headings ("A. Latar Belakang").
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from bpk_connector.domain.models import FileRef

MAIN_CATEGORY = "Peraturan"  # BPK's data-kategori for the regulation and its annexes
ANNEX_WORD = "lampiran"


class FileRole(StrEnum):
    MAIN = "main"  # the regulation itself; a separate elucidation (penjelasan) is part of it
    ANNEX = "annex"
    OTHER = "other"  # e.g. a Constitutional Court judicial-review ruling


def file_roles(files: Iterable[FileRef]) -> dict[str, FileRole]:
    """File path → role.

    A regulation always keeps a main file: when every one of its files is named as an annex (one PDF
    holding the regulation and its annex), none is demoted, so its text is never lost.
    """
    files = list(files)
    regulation_files = [f for f in files if f.category == MAIN_CATEGORY]
    annexes = {f.path for f in regulation_files if ANNEX_WORD in f.name.lower()}
    if len(annexes) == len(regulation_files):
        annexes = set()
    return {f.path: _role(f, annexes) for f in files}


def _role(file: FileRef, annexes: set[str]) -> FileRole:
    if file.category != MAIN_CATEGORY:
        return FileRole.OTHER
    return FileRole.ANNEX if file.path in annexes else FileRole.MAIN
