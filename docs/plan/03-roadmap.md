# 03 — Roadmap

Each milestone ends with something that can be shown working, and has exit criteria. The order puts the target list in the corpus first (M2), then keeps it current (M4–M5), then extracts text (M6). Research already done stands in for most of M0.

## M0 — Source spikes *(mostly done 2026-10-13)*

Done in [pilot-target-list.md](../research/pilot-target-list.md) and [watch-feasibility.md](../research/watch-feasibility.md):
- [x] Facets, exact lookup and relation links on detail pages
- [x] Sitemaps with per-URL `lastmod`, and what that `lastmod` does and doesn't track
- [x] `sort=terbaru` is not usable for detection
- [x] Publishing lag per issuer
- [x] Request rate tolerance
- [x] `ETag` on files
- [x] Resolved 93 seeds to record IDs, with status and relations

Remaining:
- [x] Save one detail-page fixture per seed form (UU, Perpu, PP, Perpres, Keppres, PMK old and new numbering, Permenkumham, Permenkum, Permenkominfo, Permen Investasi, Peraturan BKPM, Permenko, Peraturan PPATK, PERMA). Confirm every field in [01-source.md](01-source.md) parses.
- [ ] Count files per seed and their total size; find seeds with several files or no file.
- [ ] Sample 20 seed PDFs: how many have a usable text layer versus need OCR.
- [ ] Confirm the numbering assumption: numbers are unique per family and year (Permenkum and Permenkumham separately; PPATK old-style numbers).
- [ ] Look for terms of use beyond `robots.txt` (JDIH BPK site, mobile app).
- [ ] Watch a replaced file once if we can find one: does it get a new `fileId`, a new `ETag`, or both?

**Exit criteria:** a fixture set in `tests/fixtures/bpk/` and a short spike note in `docs/research/`. The data model is adjusted if needed.

## M1 — Skeleton, domain and contract *(done 2026-10-13)*

- [x] Project skeleton (`uv`, `pyproject.toml`, `bpk_connector` package, `bpk-connector` CLI, `config/pipeline.toml`), mirroring the OJK repo.
- [x] `contract/CONNECTOR_INTERFACE.md` and `src/bpk_connector/source_connector.py` copied unmodified; `test_contract_copy.py` fails if they differ.
- [x] `tests/test_architecture.py`: the dependency rule, enforced from the first commit.
- [x] `config/targets.csv` generated from the 93 seeds in the target list; `config/watch.toml` with the watch rules and exclusions.
- [x] Domain:
  - [x] `models`
  - [x] `targeting`: expansion and watch rules (refined after the first live run: partial links go to review; history never expands)
  - [x] `changes`
  - [ ] `freshness`, with date validation (moved to M3, with the freshness report)
  - [x] Unit tests on real seed data
- [x] Ports and DTOs; in-memory fakes for every port.

**Exit criteria:** `uv run pytest` passes offline. Every seed fixture parses into a `Regulation` with form, number, year, dates, status, relations and file refs. The architecture test passes.

## M2 — BPK gateway and the seed backfill *(done 2026-10-13)*

- [x] `adapters/bpk`:
  - [x] Client: pacing, User-Agent, backoff, `Blocked` / `Unavailable` / `NotFound`
  - [x] Sitemap parser
  - [x] Detail parser, on M0 fixtures
  - [x] Streaming, size-capped file downloads with `ETag`
- [x] `adapters/storage`: SQLite schema v1, blob store, corpus writer.
- [x] Use cases `CheckTargets` (first run = backfill), `FetchFiles`, `ExportCorpus`, `Reparse` *(Reparse not built yet: moved to M4)*; `RunPipeline` wiring these.
- [x] CLI: `run`, `check`, `fetch`, `export`, `status`, `events`.
- [x] First live run on all 93 seeds.

**Exit criteria:**
- Every seed has its detail HTML, its parsed metadata, its relations and every official file stored with sha256. Any seed BPK lacks is listed.
- `data/corpus/` has `metadata.json` + `original.pdf` per seed.
- A second run downloads no file again (`ETag` 304s) and changes nothing.
- `reparse` on stored HTML reproduces the same records offline.

**Result (2026-10-13):**
- **Live backfill:** 130 targets, i.e. 93 seeds + 37 lineage (after refining the rules: partial links → review; history never expands). 191 review candidates from omnibus and partial links.
- **Files:** 194 official files (163 regulations + 31 Constitutional Court rulings), 1.03 GB, 0 failures; about 5.5 minutes.
- **Idempotency:** the second run changed nothing, and all 194 files answered 304. Judicial-review files have no ETag, so they are conditional on `Last-Modified`.

## M3 — Team interface and monitoring basics *(done 2026-10-13)*

- [x] `BPKConnector` ([05](05-connector-contract.md)): `discover(cursor)`, `fetch(item, store)`, error translation; tests for a fresh-process fetch and every error path. The cursor stays `None`: targets are re-listed every time, because BPK can't signal relation changes.
- [x] `ReportRun`:
  - [x] JSON and markdown run reports (`data/reports/latest.{json,md}`, one file per run)
  - [x] Alert rules (`domain/alerts.py`), from a table of rule data plus a few rules with their own logic
  - [x] File notifier (`data/alerts.jsonl`)
  - [x] `health` (exit 0/1/2)
  - [x] **Freshness report** (`data/reports/freshness.md`). Records found by the initial backfill are "baseline": we can't know when BPK published them. Lag is measured from the first record found *after* monitoring began.
  - [x] Field fill rates per run; `parse_fill_drop` when a field is parsed ≥ 20 points less often than last run (layout drift)
- [x] Date checks: `data_anomaly` for impossible dates (e.g. a promulgation date after the day we saw it)
- **Deferred, on purpose:**
  - Alert *state* (de-duplicating repeats, reminders, resolution) and the Slack, email and webhook channels. They only matter once alerts are pushed somewhere. As with OJK, they wait for the orchestration phase. Until then, every run's alerts are in the report and in `alerts.jsonl`.

## M4 — Change detection on targets and lineage *(done 2026-10-13)*

- [x] `CheckTargets` diffs (status, relations, files, metadata) into events, with fingerprints. *(built in M2)*
- [x] The expansion rule auto-adds lineage targets, including their files; omnibus links go to candidates. *(built in M2)*
- [x] `reparse`: re-apply parsers to stored HTML with no network. Live check: 130 records reparsed, 0 changed.
- [x] Consistency check: a link BPK shows on one record but not, reversed, on the other → `link_inconsistency` (info). First live finding: Permenkumham 1/2016 lists 21/2021 as both "revoked by" and "amended by".
- [x] Replaced files: covered without a separate rule. Every target's file list is re-read daily, and every file is re-requested conditionally (`ETag` / `Last-Modified`), so a replaced file is caught whether or not BPK moves the sitemap `lastmod`.
- [x] CLI: `events --since`.

## M5 — New-record discovery and the review queue *(built 2026-10-13; 7-day exit check pending scheduled runs)*

- [x] `SyncSitemaps`:
  - The first sync records a baseline: 82 year files, about 310,000 records, none treated as new.
  - After that, only year files whose `lastmod` changed are read, plus a full sweep every 7 days.
  - New and removed IDs are reported.
  - A year that suddenly lists nothing stops the run instead of "removing" thousands of records.
- [x] `TriageNewRecords`: a detail fetch for every new ID, then the `targeting` decision. Every decision, including `ignore`, is logged as a `new_record_triaged` event, so "why didn't we collect X?" has an answer. Raw HTML of ignored records is not kept (Q7).
- [x] `ReviewCandidates` + CLI `review list | approve | reject`. Approval writes a row to `targets.csv` for a pull request. Candidates carry the link that proposed them (kind, citation, subject).
- [x] Alerts `no_new_records` (no new BPK record for 7 days) and `review_backlog` (candidates open more than 14 days).
- [ ] `sitemap_drop` as an alert. Removed IDs are reported in the run's `sync` summary. Targets that disappear are already caught as `target_missing`.

**Exit criteria (pending):** 7 consecutive daily runs in which every new BPK record is triaged. This needs scheduled runs (M7).

## M6 — Text extraction *(done 2026-10-13)*

- [x] `ExtractTexts` with `pymupdf`:
  - Text layer page by page, with `<!-- page N -->` markers.
  - Coverage and method recorded per file, keyed by the file's sha256, so each file is extracted once.
  - Corpus output: `texts/{category}-{file_id}.id.md` per file, plus `text.id.md` for the regulation.
- [x] **OCR** (`OcrTextExtractor`, ocrmypdf + Tesseract `ind+eng`):
  - Only pages without a text layer are OCR'd. They are rendered to images at 300 dpi, recognised, and merged back by page number.
  - The original file is never altered. This also handles the Constitutional Court's **digitally signed** rulings, which ocrmypdf refuses to modify directly.
  - Texts extracted before OCR existed get one upgrade.
- [x] **Zip annexes** (`ArchiveTextExtractor`): each PDF inside is extracted in name order, read in memory, with an unpacked-size cap. Perpres 10/2021's investment list is 4 PDFs, 104 pages.
- [x] Startup checks: `health`, `run`, `extract` and `BPKConnector` fail loudly when OCR tools are missing (README: system requirements).
- [x] Live result: **every one of the 193 distinct files has text**: 174 from the text layer, 18 OCR'd (2,587 pages, done in about 2 minutes), 1 archive. 3 pages remain under the text threshold (blank or signature pages). Permenko 13/2024, fully scanned, now reads cleanly.
- [x] Large files: UU 4/2023 (82 MB) and UU 6/2023 (85 MB) extract page by page.
- [x] `BPKConnector.fetch` delivers the extracted text too, so the orchestrator gets the same artifacts as the standalone pipeline.

## M7 — Scheduled operation and hand-off to the orchestrator

The connector is developed and backfilled locally now. In the deployment phase it runs on a server under the team's orchestrator (probably Airflow), which fetches updates and new documents unattended.

- [ ] Daily scheduled run (cron locally until the orchestrator exists), to complete M5's 7-day exit check.
- [ ] Runbook: for each alert code, what it means and what a person does.
- [ ] Server provisioning: Python ≥ 3.11 + uv; Tesseract with `ind` and `eng`; Ghostscript (README: system requirements). `bpk-connector health` exits 0 on a correctly provisioned worker.
- [ ] Hand `BPKConnector` to the orchestration phase (same as OJK M5). Agree with the team on storage (the orchestrator's `FileStore`), schedule and alert channels; alert state and Slack/email/webhook channels come in then.

**Exit criteria:**
- 14 consecutive scheduled daily runs with no one intervening.
- Every new target-related BPK record is picked up within 24 hours of BPK publishing it.
- The freshness report has 14 days of history.

## Future: addressing the consequences of D2

Decision D2 ([00-overview.md](00-overview.md#decisions-this-plan-is-built-on)) keeps this phase to one source, BPK. **The resulting delays are a known consequence of that decision, not defects.** The items below address them when the team chooses. None of them is built in this phase.

| # | Consequence of D2 | Measured impact | Future work | Fits the architecture as |
|---|---|---|---|---|
| F1 | **Publishing lag:** new rules reach the corpus weeks to months after enactment | Median 41 days; 90th percentile 198. Permenkum ~259 days, PERMA ~149, Permenko Ekon ~72 | Evaluate and add a faster discovery source for slow issuers: peraturan.go.id, JDIH Kemenkum (Permenkum), JDIH MA (PERMA), JDIH Kemenko Perekonomian (KUR) | A second `BpkGateway`-style implementation behind the same port. Records are matched by citation until the team schema exists; use cases are unchanged |
| F2 | **KHES not on BPK:** PERMA 2/2008 is missing although sharia contract disputes rely on it | 1 key document | Fetch it from JDIH MA, or add it once by hand with provenance | A manual-import adapter, or part of F1 |
| F3 | **No completeness check against issuers:** BPK may lack or misdate a target | Data errors seen (a future promulgation date; status lagging) | Reconcile targets against the issuers' JDIH sites | A reconciliation use case, like OJK M4 |
| F4 | **Candidates can't reach the orchestrator:** interface v1.0 has no channel for "needs review" | About 1 candidate a day | Propose interface v1.1 with an optional review/candidate channel, together with the team | A contract change for all connectors |

**When to revisit D2:** the freshness report (M3) gives the evidence. Proposed triggers:
- a P1 target is in force more than 60 days before it appears on BPK; or
- product needs answers on "rules in force today" for company formation, fiduciary or beneficial ownership (the Permenkum-heavy domains).
