"""Change detection between two observations of one BPK record.

BPK's sitemap ``lastmod`` doesn't move when a newer regulation amends or revokes a record
(watch-feasibility.md), so targets are re-read every run and compared here.
Signals are recorded, not interpreted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from bpk_connector.domain.models import ChangeEvent, FileRef, Regulation, Relation

STATUS_LABEL = "Status"


def diff(old: Regulation | None, new: Regulation) -> list[ChangeEvent]:
    if old is None:
        return [ChangeEvent("new_record", new.record_id, {"citation": new.citation})]
    events = []
    if old.status != new.status:
        events.append(ChangeEvent("status_changed", new.record_id, {"from": old.status, "to": new.status}))
    events += _set_changes("relation", old.relations, new.relations, new.record_id)
    events += _set_changes("file", old.files, new.files, new.record_id)
    if edited := _edited_fields(old, new):
        events.append(ChangeEvent("metadata_changed", new.record_id, {"fields": edited}))
    return events


def fingerprint(regulation: Regulation) -> str:
    """Changes exactly when the record should be fetched again: fields, status, links or files."""
    payload = {
        "fields": regulation.fields,
        "status": regulation.status,
        "relations": sorted(_describe(r) for r in regulation.relations),
        "files": sorted(_describe(f) for f in regulation.files),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _set_changes(noun: str, old: tuple, new: tuple, record_id: str) -> list[ChangeEvent]:
    added = [ChangeEvent(f"{noun}_added", record_id, x.summary) for x in new if x not in old]
    removed = [ChangeEvent(f"{noun}_removed", record_id, x.summary) for x in old if x not in new]
    return added + removed


def _edited_fields(old: Regulation, new: Regulation) -> list[str]:
    labels = (old.fields.keys() | new.fields.keys()) - {STATUS_LABEL}  # status has its own event
    return sorted(k for k in labels if old.fields.get(k) != new.fields.get(k))


def _describe(item: Relation | FileRef) -> str:
    return json.dumps(item.summary, sort_keys=True, ensure_ascii=False)


INVERSE_LINKS = {
    "Diubah dengan": "Mengubah",
    "Mengubah": "Diubah dengan",
    "Dicabut dengan": "Mencabut",
    "Mencabut": "Dicabut dengan",
    "Dicabut sebagian dengan": "Mencabut sebagian",
    "Mencabut sebagian": "Dicabut sebagian dengan",
}


def one_sided_links(regulations: Mapping[str, Regulation]) -> list[tuple[str, Relation]]:
    """Links BPK shows on one record but not, reversed, on the other. A sign of a data error at BPK."""
    found = []
    for record_id, regulation in regulations.items():
        for relation in regulation.relations:
            other = regulations.get(relation.record_id)
            inverse = INVERSE_LINKS.get(relation.kind)
            if other is None or inverse is None:
                continue
            if not any(r.kind == inverse and r.record_id == record_id for r in other.relations):
                found.append((record_id, relation))
    return found
