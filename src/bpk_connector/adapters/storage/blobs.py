"""Content-addressed, write-once blobs on disk: ``{root}/{sha256[:2]}/{sha256}``. Same layout as OJK."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


class FileBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        path = self._path(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(".partial")
            partial.write_bytes(data)
            os.replace(partial, path)  # atomic: a crash never leaves a half-written blob under its hash
        return sha

    def get(self, sha256: str) -> bytes:
        return self._path(sha256).read_bytes()

    def path(self, sha256: str) -> Path:
        return self._path(sha256)

    def _path(self, sha: str) -> Path:
        return self.root / sha[:2] / sha
