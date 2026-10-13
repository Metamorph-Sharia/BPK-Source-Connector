"""The corpus on disk (``data/corpus/``), rebuilt in full on every export:

regulations.jsonl                      one line per target
documents/bpk/{record_id}/metadata.json
documents/bpk/{record_id}/files/…      official files, copied from the blob store
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from bpk_connector.adapters.storage.blobs import FileBlobStore
from bpk_connector.application.dto import CorpusDocument

INDEX_FIELDS = ("citation", "title", "status", "in_force")


class CorpusWriter:
    def __init__(self, root: Path, blobs: FileBlobStore) -> None:
        self.root = root
        self.blobs = blobs

    def write(self, documents: list[CorpusDocument]) -> None:
        staging = self.root.with_name(self.root.name + ".partial")
        shutil.rmtree(staging, ignore_errors=True)
        index = []
        for document in documents:
            folder = staging / "documents" / "bpk" / document.record_id
            folder.mkdir(parents=True)
            (folder / "metadata.json").write_text(
                json.dumps(document.metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for relative, sha in document.files:
                self._place(sha, folder / relative)
            index.append(_index_line(document))
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "regulations.jsonl").write_text(
            "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in index), encoding="utf-8"
        )
        shutil.rmtree(self.root, ignore_errors=True)
        staging.rename(self.root)  # readers never see a half-written corpus

    def _place(self, sha: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.blobs.path(sha), target)  # PDFs can be 80+ MB: copy, don't load into memory


def _index_line(document: CorpusDocument) -> dict:
    metadata = document.metadata
    return {
        "record_id": document.record_id,
        **{k: metadata.get(k) for k in INDEX_FIELDS},
        "tier": metadata["target"]["tier"],
        "path": f"documents/bpk/{document.record_id}",
    }
