"""Sitemap parsing, on BPK's real index and an excerpt of its 2026 file."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bpk_connector.adapters.bpk.sitemap import parse_index, parse_year
from bpk_connector.application.dto import SitemapEntry, SitemapFile

SITEMAPS = Path(__file__).parent / "fixtures" / "bpk" / "sitemaps"


def test_the_index_lists_one_file_per_regulation_year_with_its_lastmod() -> None:
    files = parse_index((SITEMAPS / "sitemap.xml").read_bytes())

    years = [f.year for f in files]
    assert years[0] == "2026" and "1945" in years and len(years) == 82  # the static sitemap is skipped
    assert files[0] == SitemapFile("2026", "https://peraturan.bpk.go.id/sitemap-peraturan-2026.xml", date(2026, 10, 13))


def test_a_year_file_lists_record_ids_slugs_and_lastmod() -> None:
    entries = parse_year((SITEMAPS / "sitemap-peraturan-2026.xml").read_bytes())

    assert entries[0] == SitemapEntry("337869", "uu-no-1-tahun-2026", date(2026, 1, 5))
    assert "350166" in [e.record_id for e in entries]
