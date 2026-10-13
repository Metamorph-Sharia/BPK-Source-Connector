"""``TargetCatalog`` from two reviewed files: ``config/targets.csv`` and ``config/watch.toml``.

Approving a review candidate is a pull request adding a row to targets.csv.
"""

from __future__ import annotations

import csv
import tomllib
from pathlib import Path

from bpk_connector.domain.models import Target, TargetOrigin, Tier
from bpk_connector.domain.targeting import WatchRules


class CatalogError(ValueError):
    pass


class FileCatalog:
    def __init__(self, targets_csv: Path, watch_toml: Path) -> None:
        self.targets_csv = targets_csv
        self.watch_toml = watch_toml

    def seeds(self) -> list[Target]:
        seeds: dict[str, Target] = {}
        with self.targets_csv.open(newline="", encoding="utf-8") as f:
            for line, row in enumerate(csv.DictReader(f), start=2):
                target = self._target(row, line)
                if target.record_id in seeds:
                    raise CatalogError(f"{self.targets_csv}: line {line}: duplicate record_id {target.record_id}")
                seeds[target.record_id] = target
        return list(seeds.values())

    def watch_rules(self) -> WatchRules:
        raw = tomllib.loads(self.watch_toml.read_text(encoding="utf-8"))
        return WatchRules(
            forms=frozenset(raw["forms"]),
            title_keywords=tuple(k.lower() for k in raw.get("title_keywords", [])),
            subjects=frozenset(s.upper() for s in raw.get("subjects", [])),
            max_auto_links=int(raw.get("max_auto_links", WatchRules.max_auto_links)),
        )

    def approve(self, target: Target, *, citation: str, rationale: str) -> None:
        if target.record_id in {t.record_id for t in self.seeds()}:
            raise CatalogError(f"{target.record_id} is already in {self.targets_csv}")
        text = self.targets_csv.read_text(encoding="utf-8")
        with self.targets_csv.open("a", newline="", encoding="utf-8") as f:
            if text and not text.endswith("\n"):
                f.write("\n")
            csv.writer(f, lineterminator="\n").writerow(
                [target.record_id, target.tier.value, target.domain, citation, rationale]
            )

    def _target(self, row: dict[str, str], line: int) -> Target:
        try:
            record_id = row["record_id"].strip()
            if not record_id.isdigit():
                raise ValueError(f"record_id {record_id!r} is not a BPK record number")
            return Target(
                record_id,
                Tier(row["tier"].strip()),
                TargetOrigin.SEED,
                row["domain"].strip(),
                note=row["rationale"].strip(),
            )
        except (KeyError, ValueError) as e:
            raise CatalogError(f"{self.targets_csv}: line {line}: {e}") from None
