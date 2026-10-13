"""The BPK gateway over HTTP, against a mock transport: pacing, retries and error translation."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from bpk_connector.adapters.bpk.gateway import HttpBpkGateway
from bpk_connector.application.dto import SitemapFile, StoredFile
from bpk_connector.application.ports import Blocked, FileTooLarge, NotFound, Unavailable
from bpk_connector.domain.models import FileRef

FIXTURES = Path(__file__).parent / "fixtures" / "bpk"
PDF = FileRef("157089", "PMK.pdf", "/Download/157089/PMK%20Nomor%20130.pdf")


class Site:
    """A scripted peraturan.bpk.go.id: path → list of responses, served in order (the last one repeats)."""

    def __init__(self, routes: dict[str, list[httpx.Response]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get(request.url.raw_path.decode(), [httpx.Response(404)])
        return queue.pop(0) if len(queue) > 1 else queue[0]


def gateway(site: Site, **settings) -> tuple[HttpBpkGateway, list[float]]:
    sleeps: list[float] = []
    client = httpx.Client(transport=httpx.MockTransport(site), base_url="https://peraturan.bpk.go.id")
    return HttpBpkGateway(client, user_agent="bpk-connector/test", sleep=sleeps.append, **settings), sleeps


def test_detail_returns_the_bytes_and_the_parsed_regulation() -> None:
    html = (FIXTURES / "details/164278.html").read_bytes()
    gw, _ = gateway(Site({"/Details/164278": [httpx.Response(200, content=html)]}))

    page = gw.detail("164278")

    assert page.html == html and page.regulation.citation == "PMK 130/PMK.010/2012"


def test_requests_are_paced_and_identified() -> None:
    site = Site({"/sitemap.xml": [httpx.Response(200, content=(FIXTURES / "sitemaps/sitemap.xml").read_bytes())]})
    gw, sleeps = gateway(site, requests_per_second=1.0)

    gw.sitemap_index()
    gw.sitemap_index()

    assert site.requests[0].headers["User-Agent"] == "bpk-connector/test"
    assert sleeps and sleeps[-1] > 0.9  # the second request waited about a second


def test_a_year_sitemap_is_fetched_from_its_listed_url() -> None:
    xml = (FIXTURES / "sitemaps/sitemap-peraturan-2026.xml").read_bytes()
    gw, _ = gateway(Site({"/sitemap-peraturan-2026.xml": [httpx.Response(200, content=xml)]}))

    entries = gw.sitemap(SitemapFile("2026", "https://peraturan.bpk.go.id/sitemap-peraturan-2026.xml", None))

    assert len(entries) == 5


def test_server_errors_are_retried_then_reported_as_unavailable() -> None:
    gw, _ = gateway(Site({"/Details/1": [httpx.Response(503)]}), max_attempts=3)

    with pytest.raises(Unavailable):
        gw.detail("1")


def test_a_transient_error_recovers_on_retry() -> None:
    html = (FIXTURES / "details/164278.html").read_bytes()
    gw, _ = gateway(Site({"/Details/164278": [httpx.Response(502), httpx.Response(200, content=html)]}))

    assert gw.detail("164278").regulation.record_id == "164278"


def test_forbidden_or_a_bot_challenge_means_blocked_and_is_not_retried() -> None:
    site = Site(
        {
            "/Details/1": [httpx.Response(403)],
            "/Details/2": [httpx.Response(503, headers={"cf-mitigated": "challenge"})],
        }
    )
    gw, _ = gateway(site)

    for record_id in ("1", "2"):
        with pytest.raises(Blocked):
            gw.detail(record_id)
    assert len(site.requests) == 2


def test_a_missing_record_is_not_found() -> None:
    gw, _ = gateway(Site({}))

    with pytest.raises(NotFound):
        gw.detail("999999999")


def test_downloads_are_conditional_on_the_etag() -> None:
    site = Site({PDF.path: [httpx.Response(304)]})
    gw, _ = gateway(site)

    download = gw.download(PDF, held=StoredFile("sha", '"abc"', 1, "application/pdf", "u"))

    assert download.not_modified
    assert site.requests[0].headers["If-None-Match"] == '"abc"'


def test_without_an_etag_downloads_are_conditional_on_last_modified() -> None:
    # BPK's judicial-review rulings (/DownloadUjiMateri) send Last-Modified but no ETag.
    site = Site({PDF.path: [httpx.Response(304)]})
    gw, _ = gateway(site)
    since = "Mon, 12 Oct 2026 05:54:20 GMT"

    download = gw.download(PDF, held=StoredFile("sha", None, 1, "application/pdf", "u", last_modified=since))

    assert download.not_modified and site.requests[0].headers["If-Modified-Since"] == since
    assert "If-None-Match" not in site.requests[0].headers


def test_a_download_returns_bytes_etag_and_media_type() -> None:
    headers = {"ETag": '"v1"', "Content-Type": "application/pdf", "Last-Modified": "Mon, 16 Jan 2023 01:42:40 GMT"}
    gw, _ = gateway(Site({PDF.path: [httpx.Response(200, content=b"%PDF-1.7", headers=headers)]}))

    download = gw.download(PDF)

    assert (download.content, download.etag, download.media_type) == (b"%PDF-1.7", '"v1"', "application/pdf")
    assert download.last_modified == "Mon, 16 Jan 2023 01:42:40 GMT"
    assert download.url == "https://peraturan.bpk.go.id/Download/157089/PMK%20Nomor%20130.pdf"


def test_files_over_the_size_cap_are_refused() -> None:
    gw, _ = gateway(Site({PDF.path: [httpx.Response(200, content=b"x" * 2048)]}), max_file_bytes=1024)

    with pytest.raises(FileTooLarge):
        gw.download(PDF)
