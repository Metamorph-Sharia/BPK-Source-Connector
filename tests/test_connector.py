"""BPKConnector through the team interface (contract v1.0), as the orchestrator will use it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fakes.memory import FakeGateway, MemoryCatalog

from bpk_connector import BPKConnector
from bpk_connector.application.dto import ExtractedText
from bpk_connector.application.ports import Blocked, FileTooLarge, NotExtractable, Unavailable
from bpk_connector.connector import EnvironmentNotReady
from bpk_connector.domain.models import FileRef, Regulation, Relation, Target, TargetOrigin, Tier
from bpk_connector.source_connector import Discovered, ItemFailed, SourceUnavailable, StoredFile

LAW = FileRef("295189", "UU Nomor 4 Tahun 2023.pdf", "/Download/295189/UU.pdf")
P2SK = Regulation(
    "240203", "UU 4/2023", "UU", "4", "2023", status="Berlaku", files=(LAW,),
    relations=(Relation("Diubah dengan", "350166", "UU No. 4 Tahun 2026"),), fields={"Judul": "UU 4/2023"},
)  # fmt: skip
AMENDMENT = Regulation("350166", "UU 4/2026", "UU", "4", "2026", status="Berlaku")
SEED = Target("240203", Tier.P1, TargetOrigin.SEED, "A")


class MemoryStore:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def put(self, data: bytes, *, media_type: str, source_url: str | None = None) -> StoredFile:
        sha = hashlib.sha256(data).hexdigest()
        self.files[sha] = data
        return StoredFile(sha256=sha, media_type=media_type, source_url=source_url)


class FakeExtractor:
    def extract(self, data: bytes) -> ExtractedText:
        if not data.startswith(b"%PDF"):
            raise NotExtractable("not a PDF: zip")
        return ExtractedText("<!-- page 1 -->\nUNDANG-UNDANG NOMOR 4 TAHUN 2023", 1, 0, "text_layer")


def connector(gateway: FakeGateway) -> BPKConnector:
    return BPKConnector({}, gateway=gateway, catalog=MemoryCatalog([SEED]), extractor=FakeExtractor())


def site() -> FakeGateway:
    return FakeGateway({"240203": P2SK, "350166": AMENDMENT}, {LAW.path: b"%PDF law"})


def test_discover_lists_every_target_including_lineage() -> None:
    discovery = connector(site()).discover(cursor=None)

    assert [i.source_id for i in discovery.items] == ["bpk:240203", "bpk:350166"]
    item = discovery.items[0]
    assert item.source_url == "https://peraturan.bpk.go.id/Details/240203"
    assert item.metadata["fields"] == {"Judul": "UU 4/2023"}  # BPK's fields, unchanged
    assert item.metadata["target"] == {"tier": "P1", "domain": "A", "origin": "seed", "via": None, "historical": False}
    assert discovery.items[1].metadata["target"]["origin"] == "lineage"


def test_the_version_changes_when_bpk_adds_an_amendment_link() -> None:
    gateway = site()
    before = connector(gateway).discover(None).items[0].version
    gateway.pages["240203"] = Regulation(
        **{**P2SK.__dict__, "relations": P2SK.relations + (Relation("Dicabut dengan", "1", "x"),)}
    )

    assert connector(gateway).discover(None).items[0].version != before


def test_fetch_saves_the_page_and_every_file_and_works_from_the_item_alone() -> None:
    item = connector(site()).discover(None).items[0]
    fresh = Discovered(item.source_id, item.source_url, item.version, json.loads(json.dumps(dict(item.metadata))))
    store = MemoryStore()

    fetched = connector(site()).fetch(fresh, store)  # a new connector: nothing carried over in memory

    assert [f.media_type for f in fetched.files] == ["text/html", "application/pdf", "text/plain; charset=utf-8"]
    assert store.files[fetched.files[1].sha256] == b"%PDF law"
    assert fetched.files[1].source_url == "https://bpk.test/Download/295189/UU.pdf"
    assert fetched.metadata["files"][0]["sha256"] == fetched.files[1].sha256
    assert fetched.metadata["files"][0]["role"] == item.metadata["files"][0]["role"] == "main"


@pytest.mark.parametrize("error", [Unavailable("HTTP 503"), Blocked("HTTP 403")])
def test_an_unavailable_or_blocking_source_becomes_source_unavailable(error: Exception) -> None:
    gateway = site()
    gateway.failure = error

    with pytest.raises(SourceUnavailable):
        connector(gateway).discover(None)


def test_a_record_gone_from_bpk_fails_that_item_for_good() -> None:
    item = connector(site()).discover(None).items[0]

    with pytest.raises(ItemFailed) as failure:
        connector(FakeGateway()).fetch(item, MemoryStore())
    assert failure.value.retryable is False


def test_a_file_over_the_size_cap_fails_that_item_until_it_changes() -> None:
    item = connector(site()).discover(None).items[0]
    gateway = site()
    gateway.download = lambda file, etag=None: (_ for _ in ()).throw(FileTooLarge("83 MB"))

    with pytest.raises(ItemFailed) as failure:
        connector(gateway).fetch(item, MemoryStore())
    assert failure.value.retryable is False


def test_name_and_concurrency_follow_the_contract() -> None:
    assert (BPKConnector.name, BPKConnector.max_concurrency) == ("bpk", 1)


def test_fetch_also_delivers_the_extracted_text_of_each_file() -> None:
    item = connector(site()).discover(None).items[0]
    store = MemoryStore()

    fetched = connector(site()).fetch(item, store)

    text = fetched.metadata["files"][0]["text"]
    assert store.files[text["sha256"]].decode().endswith("UNDANG-UNDANG NOMOR 4 TAHUN 2023")
    assert {k: text[k] for k in ("origin", "rights", "language", "method", "coverage")} == {
        "origin": "self_extracted", "rights": "public", "language": "id", "method": "text_layer", "coverage": 1.0
    }  # fmt: skip


def test_a_file_that_is_not_a_document_is_delivered_without_text() -> None:
    gateway = site()
    gateway.files[LAW.path] = b"PK\x03\x04 annex"
    item = connector(gateway).discover(None).items[0]

    fetched = connector(gateway).fetch(item, MemoryStore())

    assert fetched.metadata["files"][0]["text"] is None
    assert fetched.metadata["files"][0]["text_note"] == "not a PDF: zip"


def test_a_machine_without_the_ocr_tools_refuses_to_start(tmp_path) -> None:
    config = tmp_path / "pipeline.toml"
    root = Path(__file__).resolve().parents[1]
    config.write_text(
        f'[targets]\ntargets_csv = "{root}/config/targets.csv"\nwatch_toml = "{root}/config/watch.toml"\n'
        '[extraction]\nocr_languages = "ind+xxx"\n'
    )

    with pytest.raises(EnvironmentNotReady, match="xxx"):
        BPKConnector({"config": str(config)})
