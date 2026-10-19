# 02 — Architecture

Status: **planned.** Tech choices match the OJK connector unless stated. Where this design differs from OJK, the reason is in [06-clean-architecture-review.md](06-clean-architecture-review.md).

## Principles (shared with the OJK connector)

1. **One connector per source repository.** This one is BPK only, and implements the team interface ([05](05-connector-contract.md)). The orchestrator imports only `BPKConnector`.
2. **Where documents come from is kept apart from what they are.** The BPK gateway knows HTTP, HTML and sitemaps. The domain knows regulations, targets and changes.
3. **Dependencies point inward**, toward the parts that change least. *Stricter than OJK:* use cases depend on **ports**, never on SQLite, httpx or HTML. A test enforces this.
4. **Keep the original bytes.** Every detail page and file is stored unchanged before parsing, so parser fixes are re-applied offline (`reparse`).
5. **Pass the source's fields through unchanged** in `metadata`; our interpretation sits beside them, never in place of them.
6. **Be polite and identifiable.** 1 request/s, a named User-Agent, backoff, `robots.txt`, no getting around bot checks.
7. **Small and boring.** Standard library where possible, SQLite + files, one TOML config, `argparse`. No abstraction without a second implementation or a test fake that needs it.

## Layers and the dependency rule

```
┌────────────────────────────────────────────────────────────────────────┐
│ Entry points & wiring   cli · connector (BPKConnector) · wiring        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Adapters      bpk/ (httpx, sitemap XML, detail HTML)             │  │
│  │               storage/ (SQLite, blobs, corpus files)             │  │
│  │               catalog/ (targets.csv, watch.toml)                 │  │
│  │               extraction/ (pymupdf, ocrmypdf)                    │  │
│  │               monitoring/ (notifier channels)                    │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │ Application   use_cases/ · ports.py · dto.py               │  │  │
│  │  │  ┌──────────────────────────────────────────────────────┐  │  │  │
│  │  │  │ Domain   models · targeting · changes ·              │  │  │  │
│  │  │  │          freshness · alerts                          │  │  │  │
│  │  │  └──────────────────────────────────────────────────────┘  │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
               source-code dependencies point inward only
```

| Layer | May import | Must not import | Changes when |
|---|---|---|---|
| **Domain** (`bpk_connector.domain`) | standard library, other domain modules | anything else in the package; third-party libraries | Our rules change (expansion rule, watch rules, what counts as a change) |
| **Application** (`bpk_connector.application`) | domain | adapters, `httpx`, `sqlite3`, HTML or PDF libraries | The workflow changes (stages, ordering, budgets) |
| **Adapters** (`bpk_connector.adapters`) | application (ports, DTOs), domain, third-party libraries | entry points | BPK's site, storage or a library changes |
| **Entry points** (`cli.py`, `connector.py`, `wiring.py`) | everything | — | How we're run (CLI, orchestrator) |

`tests/test_architecture.py` parses every module's imports with `ast` and fails on a violation. No extra dependency is needed. This is the guard the OJK repository doesn't yet have.

## Domain (pure rules, no I/O)

| Module | Holds | Tested on |
|---|---|---|
| `models.py` | Entities and value objects: `Regulation` (one BPK record: form, number, year, dates, status, issuer, subjects, raw `fields`), `Relation` (kind, target record ID, label), `FileRef` (file ID, name, ETag), `Target` (record ID, tier, domain, origin: `seed` / `lineage` / `approved`), `Candidate`, `ChangeEvent`, `Origin`, `Rights` | — |
| `targeting.py` | **The targeting policy:** the expansion rule (which relations auto-add a target) and the watch rules (which new records become review candidates). Returns a `Decision` (`auto_add` / `candidate` / `ignore`) and a reason | Seed records + recorded new records |
| `changes.py` | Diffs two observations of a record into `ChangeEvent`s: status, relations, files, metadata, `lastmod` | Pairs of saved detail pages |
| `freshness.py` | Lag per target (promulgated → first seen), per-issuer summaries, date sanity checks (e.g. a date in the future) | Measured cases from the research |
| `alerts.py` | Alert rules: run facts in, alerts with severity out (same shape as OJK's `monitoring/alerts.py`) | Synthetic run facts |
| `file_roles.py` | What each file is to its regulation: `main`, `annex` (BPK files annex volumes under "Peraturan" too, and names them "Lampiran") or `other` (judicial-review rulings). A regulation always keeps a main file | Every file name BPK uses for one |
| `text_quality.py` | How well a text's `Pasal` headings survived OCR: clean and damaged headings (`Pasa122`, `Pasal 1O`). Any damaged heading marks the text damaged; one reading is better than another only on both counts | Damaged headings from BPK text layers |

Domain objects carry no HTML labels, URLs or SQL. The gateway translates BPK's labels ("Bentuk Singkat", "T.E.U.") into typed fields, and keeps the raw labels in `fields` for pass-through.

## Application (use cases and ports)

### Ports

Defined in `application/ports.py` as `typing.Protocol`s. Each exists because it has a second implementation: a test fake now, and a planned real alternative. Each is as narrow as its users need (ISP).

```python
class BpkGateway(Protocol):                       # adapters/bpk; fake: tests/fakes/bpk.py
    def sitemap_index(self) -> list[SitemapFile]: ...                 # (year, url, lastmod)
    def sitemap(self, year: str) -> list[SitemapEntry]: ...           # (record_id, slug, lastmod)
    def detail(self, record_id: str) -> DetailPage: ...               # raw HTML bytes + parsed DetailFields
    def download(self, file: FileRef, etag: str | None) -> Download: ...  # bytes, or not_modified
    # raises SourceUnavailable-like port errors: Blocked, Unavailable, NotFound

class RecordRepository(Protocol): ...   # records, relations, files, sitemap state; adapters/storage (SQLite)
class EventLog(Protocol): ...           # append events, read since; adapters/storage
class BlobStore(Protocol):              # content-addressed, write-once; adapters/storage (files)
    def put(self, data: bytes, media_type: str) -> str: ...           # sha256
class TargetCatalog(Protocol): ...      # seeds + approved targets, review queue; adapters/catalog (CSV + TOML)
class TextExtractor(Protocol): ...      # PDF bytes → text + quality + method; adapters/extraction
class Notifier(Protocol): ...           # alerts out; adapters/monitoring
class Clock(Protocol): ...              # today/now, so time-based rules are testable
```

`BpkGateway` is also the seam where a faster second source (roadmap Future F1) would plug in. That is a real expected second implementation, not speculation.

### DTOs crossing the boundary

`application/dto.py` holds plain frozen dataclasses: `SitemapFile`, `SitemapEntry`, `DetailFields` (typed fields + raw `fields` dict + relations + file refs), `DetailPage` (`html: bytes`, `fields: DetailFields`), `Download`. Adapters produce DTOs. Use cases turn DTOs into domain objects (`Regulation.from_detail(...)`). No `httpx.Response`, `sqlite3.Row` or parsed HTML crosses inward.

### Use cases

One module each in `application/use_cases/`. Each takes its ports in its constructor and does one job (SRP), unlike OJK's single `pipeline.py`.

| Use case | Does | Ports |
|---|---|---|
| `SyncSitemaps` | Fetch the index; re-fetch only yearly files whose `lastmod` changed (all 83 on a **full sweep**, weekly). Output: new IDs, IDs whose `lastmod` changed, IDs no longer listed | gateway, repository, clock |
| `TriageNewRecords` | For each new ID: fetch the detail page, store the raw HTML, build the `Regulation`, ask `targeting` for a decision. `auto_add` → becomes a target (lineage). `candidate` → review queue. `ignore` → a minimal row so it's never fetched again | gateway, blobs, repository, catalog, events |
| `CheckTargets` | Re-fetch every target's detail page (BPK's `lastmod` misses relation changes); diff with `changes`; apply the expansion rule to new relations; record events | gateway, blobs, repository, catalog, events |
| `FetchFiles` | For targets with new or changed file refs: conditional download (`ETag`), store bytes, record the file. Respects a per-run size budget | gateway, blobs, repository, events |
| `ExtractTexts` | PDF → Indonesian text, with text layer first and OCR where it can't be trusted; heading quality stored and damage reported | blobs, repository, extractor |
| `ExportCorpus` | Rebuild `data/corpus/` from the store, exportable rights only | repository, blobs, corpus writer |
| `ReportRun` | Evaluate alert rules, the freshness report, notify, write the run report | repository, events, notifier, clock |
| `ReviewCandidates` | List, approve or reject candidates; approval adds a target to the catalog | catalog, repository, events |
| `Reparse` | Re-apply parsers and rules to stored HTML, with no network | blobs, repository |
| `RunPipeline` | Calls the use cases above in order, stopping cleanly on `Unavailable` / `Blocked` | the use cases |

## Adapters

| Adapter | Implements | Notes |
|---|---|---|
| `adapters/bpk/client.py` | HTTP for the gateway | `httpx`, 1 request/s, User-Agent `bpk-connector/0.x (+contact)`, backoff on 5xx, `Retry-After` on 429, 403 or challenge page → `Blocked`, streaming downloads with a size cap |
| `adapters/bpk/sitemap.py` | Sitemap XML → `SitemapFile` / `SitemapEntry` | Standard-library `xml.etree` |
| `adapters/bpk/detail_parser.py` | Detail HTML → `DetailFields` | Matches structure, not literal headings (`STATUS <span>PERATURAN</span>`). Indonesian month names → ISO dates. Fixtures for every seed form |
| `adapters/bpk/gateway.py` | `BpkGateway` | Composes the three above |
| `adapters/storage/sqlite.py` | `RecordRepository`, `EventLog` | Schema below; in-place migrations |
| `adapters/storage/blobs.py` | `BlobStore` | `data/raw/{sha[:2]}/{sha}` |
| `adapters/storage/corpus.py` | Corpus writer used by `ExportCorpus` | Layout below |
| `adapters/catalog/files.py` | `TargetCatalog` | `config/targets.csv` (curated, versioned in git) + `config/watch.toml` (watch rules) + review queue in SQLite |
| `adapters/extraction/pdf.py` | `TextExtractor` | `pymupdf` text layer |
| `adapters/extraction/ocr.py` | `TextExtractor` | `ocrmypdf` + Tesseract `ind+eng`, single-column layout (`--psm 4`). OCRs pages without a text layer; when the text layer has damaged headings (the publisher's own OCR), every page, keeping the cleaner reading |
| `adapters/monitoring/notifiers.py` | `Notifier` | File channel always on; Slack, webhook and email deferred to the orchestration phase, as in OJK |

## Entry points and wiring

- **`wiring.py`** is the composition root. It reads config, builds the adapters and hands them to the use cases. It's the only module that knows every concrete class.
- **`cli.py`:** `bpk-connector run | sync | triage | check | fetch | extract | export | review | events | health | reparse | status | freshness`.
- **`connector.py` → `BPKConnector`:** the team interface ([05](05-connector-contract.md)). It uses the gateway, the domain rules and the catalog, never the SQLite store, because under the orchestrator the orchestrator owns storage.

## Pipeline stages (`bpk-connector run`)

```
 targets.csv ─┐
              ▼
 sitemaps ─► SyncSitemaps ─► new IDs ─► TriageNewRecords ─┬─ auto_add ──► target (lineage)
              │                                            ├─ candidate ─► review queue ─► (person) ─► targets.csv
              │                                            └─ ignore ────► minimal row
              ▼
          CheckTargets (every target's detail page) ─► events ─► FetchFiles ─► ExtractTexts
                                                                                   │
                          ExportCorpus ◄───────────────────────────────────────────┘
                               │
                          data/corpus/                        ReportRun ─► reports, alerts, freshness
```

Daily cost (measured): ~150–250 requests, ~5 minutes at 1 request/s; a weekly full sweep adds 83 sitemaps (57 MB, ~4 minutes). File downloads come on top, and are budgeted per run.

## Targets

| Source of truth | Holds | Changed by |
|---|---|---|
| `config/targets.csv` (git) | Seeds and approved targets: `record_id, tier, domain, short_name, rationale, origin, added_on, added_by` | A person, through a PR. **Approving a candidate is a reviewed change to this file** |
| `config/watch.toml` (git) | Watch rules: central-government forms (`Bentuk Singkat`), issuers (`T.E.U.`), title keywords, subjects, excluded forms (OJK/BI/regional) | A person, through a PR |
| SQLite | Lineage targets (derived), candidates and decisions | The pipeline. Lineage is **re-derivable** from seeds + BPK's relations, so no state is lost if the DB is rebuilt |

The expansion rule (from [pilot-target-list.md](../research/pilot-target-list.md#expansion-rule)) as a domain rule (`domain/targeting.py`), refined by the first live run (2026-10-13):

| Link on a target's page | Action | Why |
|---|---|---|
| *Diubah dengan*, *Dicabut dengan* (a newer version) | Auto-add with the target's tier. Followed from lineage targets too, so targets stay current | UU 4/2023 → UU 4/2026 |
| *Mengubah*, *Mencabut* (an older version), from a curated target only | Auto-add as P3 **history**. History is never expanded further | Otherwise every revocation chain is walked: UU 25/2007 → UU 12/1970 → the income-tax law |
| *Dicabut sebagian dengan*, *Mencabut sebagian* (partial) | Review candidate | Usually another sector's law: PP 5/2021 (licensing) is partly revoked by PP 11/2023 (fishing quotas) |
| More than `max_auto_links` (5) version links in one direction | Review candidates | Omnibus laws: UU 6/2023, UU 4/2023, the Criminal Code, PMK 81/2024 |

`application/walk.py` applies this rule while visiting targets. `CheckTargets` (which records what it sees) and `BPKConnector` (which only lists) share it, so both always see the same target set.

## Identity: BPK's record ID, no canonical scheme (D4)

The team has agreed only on the connector interface. A cross-agency ID format and document schema come in a later phase, once every agency's data is collected. So in this phase:

- **Every record is keyed by BPK's record ID** (`/Details/{id}`): `bpk:{record_id}` in the interface, `{record_id}` in the store and the corpus.
- **BPK's fields are kept unchanged** (`fields`, with BPK's labels). Beside them, the parser adds a few typed values we need ourselves: form (`Bentuk Singkat`), number, year, dates, status. These are BPK's values typed, not a new identity.
- **A human-readable citation** (e.g. "Permenkum 49/2025") is derived for reports only. It is not an identifier.
- **No cross-record deduplication.** If BPK holds the same regulation twice, both records are kept, and the rare case is reported as a `data_anomaly` when two targets share form, number and year.
- When the later schema is designed, the stored raw HTML lets everything be re-derived offline (`reparse`).

## Data model (SQLite, schema v1)

```text
records          one row per BPK record we've seen
  record_id (PK), fields_json (raw labels, unchanged), title, form_short, number, year,
  enacted_on, promulgated_on, effective_on, issuer, subjects_json, status,
  fingerprint (status + relations + file refs + key fields), sitemap_year, sitemap_lastmod,
  role (target | candidate | ignored), first_seen_at, last_checked_at, missing_since
targets          record_id, tier, domain, origin (seed | lineage | approved), via_record, added_at
candidates       record_id, matched_rules_json, state (open | approved | rejected), decided_by, decided_at
relations        from_record, kind (raw label), to_record, label, first_seen_at, last_seen_at
files            record_id, file_id, name, etag, last_modified, size, sha256, fetched_at, state
texts            sha256 (of the PDF), origin (self_extracted), method (text_layer | ocr), rights,
                 blob_sha256, chars, extracted_at,
                 clean_headings, damaged_headings (NULL: extracted before quality was assessed; re-extracted once)
snapshots        record_id, kind (detail_html), blob_sha256, fetched_at
sitemap_state    year, lastmod, url_count, fetched_at
events           run_id, at, record_id, kind, detail_json
alert_state      open/resolved alerts (as in OJK)
runs             run log + report
```

## Storage

```
data/                                      # git-ignored; back it up
  raw/{sha256[:2]}/{sha256}                # immutable blobs: detail HTML, PDFs
  db/bpk_connector.sqlite
  reports/run-{timestamp}.{json,md}, latest.{json,md}, freshness.md
  alerts.jsonl
  corpus/                                  # the knowledge-database hand-off (rebuilt by `export`)
    regulations.jsonl                      # one line per target
    documents/bpk/{record_id}/
      metadata.json                        # BPK fields (unchanged) + typed values, status, relations, target, provenance, freshness
      files/{file_id}.pdf                  # official files, byte-for-byte
      text.id.md                           # extracted Indonesian text
```

The same shape as OJK's corpus (`regulations.jsonl` + one folder per document), keyed by BPK's record ID because no cross-agency ID exists yet (D4).

### Rights

| Artifact | `origin` | `rights` | Exported |
|---|---|---|---|
| Official file (PDF) | `official_file` | `public` | Yes |
| Text we extract from it | `self_extracted` | `public` | Yes |
| BPK metadata fields (facts: numbers, dates, status, relations) | — | `public` | Yes, in `metadata.json` |
| BPK's abstract (*Abstrak*), written by its editors | — | `restricted` | No: kept only in the raw HTML snapshot |

## Change detection

| Change | Detected by | Event |
|---|---|---|
| New BPK record (any) | `SyncSitemaps` ID diff | `new_record` |
| New record amends or revokes a target | `TriageNewRecords` + expansion rule | `target_added` (origin `lineage`) |
| New record matches a watch rule | `TriageNewRecords` + watch rules | `candidate_queued` |
| Target amended, revoked or partly revoked | `CheckTargets` relation diff | `relation_added`, `status_changed` |
| Status flips (Berlaku ↔ Tidak Berlaku) | `CheckTargets` | `status_changed` |
| Metadata edited | `CheckTargets` field diff; sitemap `lastmod` change | `metadata_changed` (with fields) |
| File added, replaced or removed | `CheckTargets` file-ref diff + `ETag` | `file_added`, `file_changed`, `file_removed` |
| Record removed | Missing from a weekly full sweep, or 404 | `missing_from_source`, `reappeared` |
| Impossible or inconsistent data | `freshness` date checks, relation sanity | `data_anomaly` |

Signals are recorded, not interpreted. Whether a change matters to a business is out of scope.

## Monitoring and alerts

Rules are pure (`domain/alerts.py`); `ReportRun` gathers each run's facts; `health` exits 0/1/2. `run` exits 2 when it raised an error or critical alert. Alert *state* (de-duplication, reminders) and push channels wait for the orchestration phase, as in OJK; until then alerts go to the run report and `data/alerts.jsonl`.

| Alert | Severity | When |
|---|---|---|
| `source_blocked` | critical | 403 or a Cloudflare challenge: a person must look; never worked around |
| `run_failed` | error | A run ended in error for another reason |
| `source_unavailable` | warning | Outage, 5xx or 429 after retries: the run pauses and the next one resumes |
| `target_missing` | error | A target's detail page is gone (404) |
| `file_missing` | error | A target's file is gone |
| `file_deferred` | warning | A file over the size cap, or over the run's download budget |
| `target_changed` | info | Targets amended, revoked, or with files added or removed |
| `lineage_added` | info | Targets added by the expansion rule |
| `candidates_queued` | info | Records queued for review |
| `data_anomaly` | warning | Impossible dates (e.g. promulgated after the day we saw it) |
| `text_incomplete` | warning | Extracted files with pages that need OCR |
| `text_damaged` | warning | Extracted files whose `Pasal` headings are still OCR-damaged (no OCR here, or OCR read no better) |
| `link_inconsistency` | info | A link BPK shows on one record but not, reversed, on the other |
| `review_backlog` | warning | Candidates open for more than 14 days |
| `no_new_records` | warning | No new BPK record for 7 days (BPK normally adds 40–60 a day) |
| `parse_fill_drop` | warning | A field parsed ≥ 20 points less often than last run (layout drift) |
| `stale_run` (via `health`) | critical | No successful run within `max_hours_between_runs` (36) |
