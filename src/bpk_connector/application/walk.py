"""Walk the targets: read each target's detail page and follow its version links to new targets.

Shared by ``CheckTargets`` (which records what it sees) and ``BPKConnector`` (which only lists),
so both apply the same targeting rules.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from bpk_connector.application.dto import DetailPage
from bpk_connector.application.ports import BpkGateway, NotFound
from bpk_connector.domain.models import Relation, Target
from bpk_connector.domain.targeting import WatchRules, lineage_of


@dataclass(frozen=True)
class Visit:
    target: Target
    page: DetailPage | None  # None: BPK no longer has the record
    added: list[Target] = field(default_factory=list)  # lineage targets first found on this page
    for_review: list[Relation] = field(default_factory=list)  # links to queue as review candidates


def walk_targets(gateway: BpkGateway, targets: dict[str, Target], rules: WatchRules) -> Iterator[Visit]:
    """Visits every target once, including lineage found on the way. Gateway errors other than NotFound propagate."""
    known = dict(targets)
    queue = list(targets.values())
    while queue:
        target = queue.pop(0)
        try:
            page = gateway.detail(target.record_id)
        except NotFound:
            yield Visit(target, None)
            continue
        lineage = lineage_of(target, page.regulation, rules)
        added = [t for t in lineage.targets if t.record_id not in known]
        for found in added:
            known[found.record_id] = found
            queue.append(found)
        yield Visit(target, page, added, [r for r in lineage.for_review if r.record_id not in known])
