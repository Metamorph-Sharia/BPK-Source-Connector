"""BPK sitemaps → DTOs. ``/sitemap.xml`` lists one file per regulation year; each lists records."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from bpk_connector.application.dto import SitemapEntry, SitemapFile

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
YEAR_FILE = re.compile(r"sitemap-peraturan-(\d{4})\.xml$")
DETAILS_URL = re.compile(r"/Details/(\d+)/?([^/]*)$")


def parse_index(xml: bytes) -> list[SitemapFile]:
    files = []
    for node in ET.fromstring(xml).findall("sm:sitemap", NS):
        url = node.findtext("sm:loc", "", NS).strip()
        if match := YEAR_FILE.search(url):
            files.append(SitemapFile(match.group(1), url, _date(node.findtext("sm:lastmod", None, NS))))
    return files


def parse_year(xml: bytes) -> list[SitemapEntry]:
    entries = []
    for node in ET.fromstring(xml).findall("sm:url", NS):
        if match := DETAILS_URL.search(node.findtext("sm:loc", "", NS).strip()):
            entries.append(SitemapEntry(match.group(1), match.group(2), _date(node.findtext("sm:lastmod", None, NS))))
    return entries


def _date(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text.strip()[:10]) if text else None
    except ValueError:
        return None
