"""The targeting policy (decision D1): what joins the targets, what a person reviews, what is ignored.

Relevance is decided by people when they curate the target list; these rules only follow BPK's
own links from that list and propose candidates. Nothing here classifies by meaning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from bpk_connector.domain.models import Regulation, Relation, Target, TargetOrigin, Tier

# BPK's "Status Peraturan" labels, by which way they point in time.
NEWER_VERSION_LINKS = frozenset({"Diubah dengan", "Dicabut dengan"})
OLDER_VERSION_LINKS = frozenset({"Mengubah", "Mencabut"})
# Partial revocations usually come from another sector's law (PP 5/2021 on licensing is partly
# revoked by PP 11/2023 on fishing quotas), so they are reviewed rather than followed.
PARTIAL_LINKS = frozenset({"Dicabut sebagian dengan", "Mencabut sebagian"})


@dataclass(frozen=True)
class WatchRules:
    """From ``config/watch.toml``."""

    forms: frozenset[str]  # "Bentuk Singkat" values we watch; everything else (regional, OJK, BI) is ignored
    title_keywords: tuple[str, ...] = ()  # lowercase
    subjects: frozenset[str] = frozenset()  # BPK "Subjek" values
    # A page with more version links than this in one direction is an omnibus law (UU 4/2023 amends ~25
    # laws): its links go to review rather than joining, so expansion can't run away.
    max_auto_links: int = 5


@dataclass(frozen=True)
class Lineage:
    targets: list[Target] = field(default_factory=list)
    for_review: list[Relation] = field(default_factory=list)  # the links a person should judge


class Action(StrEnum):
    AUTO_ADD = "auto_add"
    CANDIDATE = "candidate"
    IGNORE = "ignore"


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    target: Target | None = None  # set when AUTO_ADD


def lineage_of(target: Target, page: Regulation, rules: WatchRules) -> Lineage:
    """Follow the version links on a target's own detail page.

    Newer versions are followed so targets stay current; older ones only from curated targets,
    and they join as history that is never expanded (else every revocation chain is walked).
    """
    lineage = Lineage()
    if target.historical:
        return lineage
    lineage.for_review.extend(_links(page, PARTIAL_LINKS))
    directions = [(NEWER_VERSION_LINKS, target.tier, False)]
    if target.origin is not TargetOrigin.LINEAGE:
        directions.append((OLDER_VERSION_LINKS, Tier.P3, True))
    for kinds, tier, historical in directions:
        links = _links(page, kinds)
        if _is_omnibus(links, rules):
            lineage.for_review.extend(links)
        else:
            lineage.targets.extend(_lineage_target(r.record_id, tier, target, historical) for r in links)
    return lineage


def triage(new: Regulation, targets: Mapping[str, Target], rules: WatchRules) -> Decision:
    """Decide what to do with a record BPK just published."""
    if partial := _touching(_links(new, PARTIAL_LINKS), targets):
        return Decision(Action.CANDIDATE, f"{partial.kind} target {partial.record_id}")
    older = _links(new, OLDER_VERSION_LINKS)
    if touched := _touching(older, targets):
        if _is_omnibus(older, rules):
            return Decision(Action.CANDIDATE, f"omnibus; {touched.kind} target {touched.record_id}")
        via = targets[touched.record_id]
        return Decision(
            Action.AUTO_ADD, f"{touched.kind} target {via.record_id}", _lineage_target(new.record_id, via.tier, via)
        )
    if new.form not in rules.forms:
        return Decision(Action.IGNORE, f"form {new.form!r} not watched")
    if match := _watch_match(new, rules):
        return Decision(Action.CANDIDATE, match)
    return Decision(Action.IGNORE, "no watch rule matched")


def _links(page: Regulation, kinds: frozenset[str]) -> list[Relation]:
    return [r for r in page.relations if r.kind in kinds]


def _touching(links: list[Relation], targets: Mapping[str, Target]) -> Relation | None:
    return next((r for r in links if r.record_id in targets), None)


def _is_omnibus(links: list[Relation], rules: WatchRules) -> bool:
    return len(links) > rules.max_auto_links


def _lineage_target(record_id: str, tier: Tier, via: Target, historical: bool = False) -> Target:
    return Target(record_id, tier, TargetOrigin.LINEAGE, domain=via.domain, via=via.record_id, historical=historical)


def _watch_match(new: Regulation, rules: WatchRules) -> str | None:
    title = new.title.lower()
    for keyword in rules.title_keywords:
        if keyword in title:
            return f"title keyword {keyword!r}"
    for subject in new.subjects:
        if subject in rules.subjects:
            return f"subject {subject!r}"
    return None
