"""FetchFiles: download every file of every target once, and again only when BPK's copy changes."""

from __future__ import annotations

from fakes.memory import FakeGateway, FixedClock, MemoryBlobs, MemoryEventLog, MemoryRepository

from bpk_connector.application.ports import FileTooLarge
from bpk_connector.application.use_cases.fetch_files import FetchFiles
from bpk_connector.domain.models import FileRef, Regulation

LAW = FileRef("295189", "UU Nomor 4 Tahun 2023.pdf", "/Download/295189/UU.pdf")
RULING = FileRef("242", "putusan.pdf", "/DownloadUjiMateri/242/putusan.pdf", category="UjiMateri")


class World:
    def __init__(self, files: dict[str, bytes], *refs: FileRef) -> None:
        self.gateway = FakeGateway(files=files)
        self.repository = MemoryRepository()
        self.repository.observations["240203"] = Regulation("240203", "P2SK", "UU", "4", "2023", files=refs)
        self.events = MemoryEventLog()
        self.blobs = MemoryBlobs()
        self.use_case = FetchFiles(self.gateway, self.repository, self.events, self.blobs, FixedClock())

    def run(self, **kwargs):
        return self.use_case.run("run-1", ["240203"], **kwargs)


def test_every_file_of_a_target_is_stored_with_its_hash_and_etag() -> None:
    world = World({LAW.path: b"%PDF law", RULING.path: b"%PDF ruling"}, LAW, RULING)

    summary = world.run()

    assert summary.stored == 2
    stored = world.repository.file_state("240203", LAW.path)
    assert world.blobs.get(stored.sha256) == b"%PDF law" and stored.etag
    assert world.events.kinds() == ["file_stored", "file_stored"]


def test_an_unchanged_file_is_not_downloaded_again() -> None:
    world = World({LAW.path: b"%PDF law"}, LAW)
    world.run()

    summary = world.run()

    assert summary.stored == 0 and summary.unchanged == 1


def test_a_replaced_file_is_stored_again_and_reported_as_changed() -> None:
    world = World({LAW.path: b"%PDF law"}, LAW)
    world.run()
    world.gateway.files[LAW.path] = b"%PDF corrected law"

    world.run()

    assert world.events.kinds()[-1] == "file_changed"
    assert world.blobs.get(world.repository.file_state("240203", LAW.path).sha256) == b"%PDF corrected law"


def test_a_missing_file_is_reported_and_the_others_still_download() -> None:
    world = World({RULING.path: b"%PDF ruling"}, LAW, RULING)

    summary = world.run()

    assert summary.failed == [LAW.path] and summary.stored == 1
    assert "file_missing" in world.events.kinds()


def test_files_over_the_byte_budget_wait_for_the_next_run() -> None:
    world = World({LAW.path: b"x" * 10, RULING.path: b"y" * 10}, LAW, RULING)

    summary = world.run(max_bytes=10)  # spent once the first file is in

    assert summary.stored == 1 and summary.deferred == [RULING.path]


def test_a_file_over_the_size_cap_is_deferred_not_failed() -> None:
    world = World({LAW.path: b"%PDF"}, LAW)
    world.gateway.failure = FileTooLarge("83 MB")

    summary = world.run()

    assert summary.deferred == [LAW.path] and summary.failed == []
