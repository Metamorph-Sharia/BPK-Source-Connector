"""SyncSitemaps: find what BPK published since the last run, from its daily-updated sitemaps.

The first sync records every existing record ID as a baseline (they were on BPK before monitoring
began); only IDs that appear after it are new. Year files whose ``lastmod`` hasn't changed are
skipped; a full sweep (weekly) reads them all, catching anything missed and any removals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bpk_connector.application.dto import SitemapFile
from bpk_connector.application.ports import BpkGateway, Clock, SitemapState, Unavailable

FULL_SWEEP_DAYS = 7


@dataclass
class SyncResult:
    baseline: bool = False  # this sync only recorded what already existed
    years_read: int = 0
    new_ids: list[str] = field(default_factory=list)
    removed_ids: list[str] = field(default_factory=list)


class SyncSitemaps:
    def __init__(self, gateway: BpkGateway, state: SitemapState, clock: Clock) -> None:
        self.gateway = gateway
        self.state = state
        self.clock = clock

    def run(self, *, full: bool | None = None) -> SyncResult:
        """``full=None``: a full sweep when the last one is ``FULL_SWEEP_DAYS`` old."""
        if full is None:
            last = self.state.last_full_sweep()
            full = last is None or (self.clock.now().date() - last).days >= FULL_SWEEP_DAYS
        known_lastmods = self.state.sitemap_lastmods()
        result = SyncResult(baseline=not known_lastmods)
        for file in self.gateway.sitemap_index():
            if full or result.baseline or self._changed(file, known_lastmods):
                self._read(file, result)
        if full or result.baseline:
            self.state.mark_full_sweep(at=self.clock.now())
        return result

    def _changed(self, file: SitemapFile, known: dict) -> bool:
        return file.year not in known or known[file.year] != file.lastmod

    def _read(self, file: SitemapFile, result: SyncResult) -> None:
        entries = self.gateway.sitemap(file)
        before = self.state.sitemap_ids(file.year)
        now = {e.record_id for e in entries}
        if before and not now:
            raise Unavailable(f"sitemap {file.year} lists nothing (it listed {len(before)}): not saved")
        if not result.baseline:
            result.new_ids += sorted(now - before, key=int)
            result.removed_ids += sorted(before - now, key=int)
        self.state.save_sitemap(file, entries, at=self.clock.now())
        result.years_read += 1
