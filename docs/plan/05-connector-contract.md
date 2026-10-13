# 05 — Connector interface

> **Status:** planned for M3. Implements the team interface **version 1.0** (2026-10-13), the same version as `OJKConnector`.

The interface is in [contract/CONNECTOR_INTERFACE.md](../../contract/CONNECTOR_INTERFACE.md), a copy of the OJK repository's file, unmodified. The code copy will be `src/bpk_connector/source_connector.py`, and `tests/test_contract_copy.py` fails if the two ever differ.

## How `BPKConnector` implements it

| Interface | BPK implementation |
|---|---|
| `name` | `"bpk"` |
| `version` | the package version |
| `max_concurrency` | `1`: one polite client, 1 request/s |
| `discover(None)` | Every **target**: the seeds and approved targets from `config/targets.csv`, plus lineage derived from BPK's relations by the expansion rule. One detail-page request per target |
| `discover(cursor)` | The same target set, plus new targets found since the cursor: new sitemap IDs whose triage says `auto_add`. The cursor is JSON: `{"max_record_id": …, "sitemap_lastmod": {"2026": "2026-10-13", …}}` |
| `Discovered.source_id` | `"bpk:{record_id}"`, e.g. `bpk:240203`. Stable: BPK's record ID never changes. The slug is never used |
| `Discovered.source_url` | `https://peraturan.bpk.go.id/Details/{record_id}` |
| `Discovered.version` | Fingerprint of the detail page's status, relations, file refs (ID + `ETag` when known) and key fields. It changes exactly when the orchestrator should fetch again, including when BPK adds an *amended by* link (which the sitemap doesn't show) |
| `Discovered.metadata` | `record_id`; `fields`, BPK's labels unchanged; `relations`; `files` (file ID, name, URL); `target` (tier, domain, origin). It holds everything `fetch` needs to run in a fresh process |
| `fetch(item, store)` | Fetches the detail page and saves the HTML through `store.put()` (`text/html`), then every file through `store.put()` (`application/pdf`). Returns `Fetched.metadata` with the parsed fields and relations, and each file's sha256 and source URL. Also saves the Indonesian text extracted from each file (`text/plain; charset=utf-8`; OCR for scanned pages; zip annexes unpacked). Each file's entry in `Fetched.metadata["files"]` carries a `text` object (sha256, method, pages, coverage, `origin: self_extracted`, `rights: public`, `language: id`), or `text_note` when the file isn't a document |
| Construction | `BPKConnector({"config": …})` raises `EnvironmentNotReady` when the machine lacks the OCR tools the config asks for, so a misprovisioned worker fails at once, not by quietly skipping scanned pages |
| Errors | 403, a Cloudflare challenge or repeated resets → `SourceUnavailable` ("blocked"). Timeouts, 5xx, 429 → `SourceUnavailable`. Detail page 404 → `ItemFailed(retryable=False)`. One file fails → `ItemFailed`. `AuthFailed` is never raised (BPK needs no sign-in) |

### What `BPKConnector` deliberately does not do

- **It does not emit review candidates.** Interface v1.0 has no "needs a person" channel. Candidates are produced by the standalone pipeline (`bpk-connector review`), and future F4 proposes interface v1.1 to the team.
- **It doesn't use the local SQLite store.** Under the orchestrator, the orchestrator owns storage and cursors. `BPKConnector` depends on the gateway port, the domain rules and the catalog only. This is why the targets file and the expansion rule must be re-derivable without our database.
- **It doesn't assign canonical IDs or merge duplicates** in what it returns; it passes BPK's fields through (rule 3). There is no canonical ID scheme in this phase at all (D4): the team designs one after every agency's data is collected.

## Rules checklist (from the contract), and how each is met

- [ ] Unmodified `source_connector.py` v1.0: copy plus `test_contract_copy.py`
- [ ] `name` unique: `"bpk"`
- [ ] `discover(None)` lists everything in scope (all targets); `discover(cursor)` lists the targets plus new ones since the cursor. Target checks are cheap, and BPK can't signal relation changes, so targets are always re-listed
- [ ] Stable `source_id`: BPK record ID
- [ ] Every file through `store.put()`: detail HTML and every PDF, unchanged, before parsing
- [ ] `fetch()` stands alone: uses `item.metadata` and `self.config` only; tested in a fresh process
- [ ] Errors are `ItemFailed`, `SourceUnavailable` or `AuthFailed` only
- [ ] Paced (1 request/s), identified (User-Agent with contact), no secrets needed
- [ ] Tests run offline against recorded fixtures
