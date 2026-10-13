"""The target catalog, on the real config files: a bad edit to targets.csv or watch.toml fails here."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from bpk_connector.adapters.catalog.files import CatalogError, FileCatalog
from bpk_connector.domain.models import Target, TargetOrigin, Tier

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_the_curated_list_has_93_seeds_in_three_tiers() -> None:
    seeds = FileCatalog(CONFIG / "targets.csv", CONFIG / "watch.toml").seeds()

    assert len(seeds) == 93
    assert Counter(s.tier for s in seeds) == {Tier.P1: 35, Tier.P2: 25, Tier.P3: 33}
    assert seeds[0] == Target("240203", Tier.P1, TargetOrigin.SEED, domain="A", note=seeds[0].note)
    assert all(s.origin is TargetOrigin.SEED for s in seeds)


def test_watch_rules_are_normalised_for_matching() -> None:
    rules = FileCatalog(CONFIG / "targets.csv", CONFIG / "watch.toml").watch_rules()

    assert "Permenkum" in rules.forms and "Perbup" not in rules.forms
    assert "fidusia" in rules.title_keywords
    assert "PERBANKAN, LEMBAGA KEUANGAN" in rules.subjects
    assert rules.max_auto_links == 5


def test_a_duplicate_or_malformed_row_is_rejected(tmp_path: Path) -> None:
    targets = tmp_path / "targets.csv"
    targets.write_text("record_id,tier,domain,citation,rationale\n1,P1,A,x,y\n1,P2,A,x,y\n")

    with pytest.raises(CatalogError, match="duplicate"):
        FileCatalog(targets, CONFIG / "watch.toml").seeds()

    targets.write_text("record_id,tier,domain,citation,rationale\nabc,P9,A,x,y\n")
    with pytest.raises(CatalogError, match="line 2"):
        FileCatalog(targets, CONFIG / "watch.toml").seeds()


def test_approving_appends_a_row_that_reads_back_as_a_seed(tmp_path: Path) -> None:
    targets = tmp_path / "targets.csv"
    targets.write_text((CONFIG / "targets.csv").read_text(encoding="utf-8"), encoding="utf-8")
    catalog = FileCatalog(targets, CONFIG / "watch.toml")

    catalog.approve(
        Target("400001", Tier.P1, TargetOrigin.SEED, "B"), citation="Permenkum 9/2026", rationale="fiduciary"
    )

    seeds = catalog.seeds()
    assert len(seeds) == 94 and seeds[-1] == Target("400001", Tier.P1, TargetOrigin.SEED, "B", note="fiduciary")
    assert targets.read_text(encoding="utf-8").splitlines()[-1] == "400001,P1,B,Permenkum 9/2026,fiduciary"
