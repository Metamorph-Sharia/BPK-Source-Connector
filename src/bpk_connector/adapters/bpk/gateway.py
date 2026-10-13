"""``BpkGateway`` over HTTP: polite, paced requests to peraturan.bpk.go.id.

1 request/s by default, an identifying User-Agent, backoff on 5xx and 429. A 403 or a bot
challenge stops the run as ``Blocked``: we never work around it (team interface rule 5).
"""

from __future__ import annotations

import itertools
import logging
import time
from collections.abc import Callable
from urllib.parse import urljoin

import httpx

from bpk_connector.adapters.bpk.detail_parser import parse_detail
from bpk_connector.adapters.bpk.sitemap import parse_index, parse_year
from bpk_connector.application.dto import DetailPage, Download, SitemapEntry, SitemapFile, StoredFile
from bpk_connector.application.ports import Blocked, FileTooLarge, NotFound, Unavailable
from bpk_connector.domain.models import FileRef

log = logging.getLogger(__name__)

BASE_URL = "https://peraturan.bpk.go.id"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_FILE_BYTES = 200 * 1024 * 1024  # UU 4/2023 is 82 MB; leave headroom
BACKOFF_SECONDS = 2.0


class HttpBpkGateway:
    def __init__(
        self,
        client: httpx.Client,
        *,
        user_agent: str,
        requests_per_second: float = 1.0,
        max_attempts: int = 3,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.client.headers["User-Agent"] = user_agent
        self.interval = 1.0 / requests_per_second
        self.max_attempts = max_attempts
        self.max_file_bytes = max_file_bytes
        self.sleep = sleep
        self.clock = clock
        self._last_request: float | None = None

    def close(self) -> None:
        self.client.close()

    def sitemap_index(self) -> list[SitemapFile]:
        return parse_index(self._get("/sitemap.xml").content)

    def sitemap(self, file: SitemapFile) -> list[SitemapEntry]:
        return parse_year(self._get(file.url).content)

    def detail(self, record_id: str) -> DetailPage:
        html = self._get(f"/Details/{record_id}").content
        return DetailPage(html, parse_detail(record_id, html))

    def download(self, file: FileRef, held: StoredFile | None = None) -> Download:
        url = urljoin(BASE_URL, file.path)
        response = self._send(file.path, _validators(held), stream=True)
        try:
            if response.status_code == 304:
                return Download(None, held.etag, "", url, held.last_modified)
            content = self._read_capped(response, file)
            headers = response.headers
            return Download(
                content, headers.get("ETag"), headers.get("Content-Type", ""), url, headers.get("Last-Modified")
            )
        finally:
            response.close()

    def _get(self, path: str) -> httpx.Response:
        return self._send(path, {}, stream=False)

    def _send(self, path: str, headers: dict[str, str], *, stream: bool) -> httpx.Response:
        for attempt in itertools.count(1):  # ends by returning, or by _back_off raising on the last attempt
            self._pace()
            try:
                response = self.client.send(
                    self.client.build_request("GET", path, headers=headers), stream=stream, follow_redirects=True
                )
            except httpx.TransportError as e:
                log.warning("GET %s failed (%s), attempt %d", path, e, attempt)
                self._back_off(attempt, path, str(e))
                continue
            if _is_blocked(response):
                raise Blocked(
                    f"{path}: HTTP {response.status_code}{' (bot challenge)' if _is_challenge(response) else ''}"
                )
            if response.status_code == 404:
                raise NotFound(path)
            if response.status_code in RETRYABLE_STATUS:
                response.close()
                self._back_off(attempt, path, f"HTTP {response.status_code}")
                continue
            if response.status_code >= 400:
                raise Unavailable(f"{path}: HTTP {response.status_code}")
            return response

    def _back_off(self, attempt: int, path: str, reason: str) -> None:
        if attempt == self.max_attempts:
            raise Unavailable(f"{path}: {reason} after {attempt} attempts")
        self.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))

    def _pace(self) -> None:
        if self._last_request is not None:
            wait = self.interval - (self.clock() - self._last_request)
            if wait > 0:
                self.sleep(wait)
        self._last_request = self.clock()

    def _read_capped(self, response: httpx.Response, file: FileRef) -> bytes:
        declared = int(response.headers.get("Content-Length") or 0)
        if declared > self.max_file_bytes:
            raise FileTooLarge(f"{file.path}: {declared} bytes")
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > self.max_file_bytes:
                raise FileTooLarge(f"{file.path}: over {self.max_file_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)


def _validators(held: StoredFile | None) -> dict[str, str]:
    if held is None:
        return {}
    if held.etag:
        return {"If-None-Match": held.etag}
    return {"If-Modified-Since": held.last_modified} if held.last_modified else {}


def _is_challenge(response: httpx.Response) -> bool:
    return response.headers.get("cf-mitigated") == "challenge"


def _is_blocked(response: httpx.Response) -> bool:
    return response.status_code == 403 or _is_challenge(response)
