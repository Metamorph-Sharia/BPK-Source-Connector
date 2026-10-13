"""The full target set: what the pipeline found (lineage, approved), with the curated seeds over it."""

from __future__ import annotations

from bpk_connector.application.ports import Repository, TargetCatalog
from bpk_connector.domain.models import Target


def all_targets(repository: Repository, catalog: TargetCatalog) -> dict[str, Target]:
    """Seeds first, then what the pipeline found. A seed's tier and origin always win: people curated them."""
    seeds = {t.record_id: t for t in catalog.seeds()}
    return seeds | {k: t for k, t in repository.targets().items() if k not in seeds}
