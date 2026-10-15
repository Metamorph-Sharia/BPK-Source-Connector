"""BPK's "Status Peraturan" in the platform's terms (contract v2's status and relation names).

BPK lists each link from both ends: A "Mengubah" (amends) B, and B "Diubah dengan" (is amended
by) A. A citation is what a regulation itself does, so only the outgoing labels become
citations; the incoming ones tell us the regulation's own standing.
"""

from __future__ import annotations

from bpk_connector.domain.models import IN_FORCE, NOT_IN_FORCE, Regulation, Relation

OUTGOING = {
    "Mengubah": "amends",
    "Mencabut": "revokes",
    "Mencabut sebagian": "partly_revokes",
    "Menetapkan": "refers_to",  # a law enacting a Perppu: it neither amends nor revokes it
}
AMENDED_BY = "Diubah dengan"
PARTLY_REVOKED_BY = "Dicabut sebagian dengan"


def standing(regulation: Regulation) -> str:
    if regulation.status == NOT_IN_FORCE:
        return "revoked"
    if regulation.status != IN_FORCE:
        return "unknown"
    kinds = {relation.kind for relation in regulation.relations}
    if PARTLY_REVOKED_BY in kinds:
        return "partly_revoked"
    if AMENDED_BY in kinds:
        return "amended"
    return "in_force"


def outgoing(regulation: Regulation) -> list[tuple[Relation, str]]:
    """(BPK's relation, the contract's name for it), once each, in BPK's order."""
    unique = dict.fromkeys(relation for relation in regulation.relations if relation.kind in OUTGOING)
    return [(relation, OUTGOING[relation.kind]) for relation in unique]
