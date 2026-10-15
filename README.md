# BPK Source Connector (`bpk-connector`)

Collects a **targeted** set of Indonesian regulations from the **BPK legal database** ([peraturan.bpk.go.id](https://peraturan.bpk.go.id)): the national laws, government and presidential regulations, and ministerial rules that frame entry into Indonesia's **sharia multifinance and consumer lending** market. It discovers, downloads, monitors and stores them locally.

This repository covers **BPK only**. Each other source has its own connector repository (OJK, BI, DSN-MUI). Every connector implements the same [team interface](contract/CONNECTOR_INTERFACE.md), so the orchestrator in the next phase (probably Airflow) runs them all the same way.

> **Status (2026-10-13):** M1–M6 done; M5's 7-day check waits for scheduled runs. Live:
> - 130 targets (93 seeds + 37 lineage)
> - 194 official files (1.03 GB), every one with Indonesian text: 31,093 pages, 18 files OCR'd, 1 zip annex unpacked
> - a sitemap baseline of ~310,000 BPK records
>
> Next: scheduled operation, then the hand-off to the orchestrator (M7). See the [roadmap](docs/plan/03-roadmap.md).

## What it collects, and why only that

BPK holds ~310,000 records from every ministry, agency and region, and most are unrelated to sharia financing. So this connector starts from a **curated target list**: 93 regulations in [config/targets.csv](config/targets.csv), from the research in [docs/research/pilot-target-list.md](docs/research/pilot-target-list.md). It also follows BPK's own links between regulations:
- **Newer versions** of a target join automatically (e.g. UU 4/2026 amends UU 4/2023).
- **Older versions** a curated target amends or revokes join as history.
- **Links from omnibus laws** and **partial revocations** go to a review queue instead, because they mostly point at other sectors.

**Known, accepted limits** (decisions in [docs/plan/00-overview.md](docs/plan/00-overview.md)):
- BPK is the only source for now (D2). BPK publishes most regulations weeks to months after enactment (median 41 days; Ministry of Law rules ~8.5 months). The connector picks a record up within a day of BPK publishing it.
- There is no cross-agency canonical ID yet (D4). Everything is keyed by BPK's record ID, and BPK's fields pass through unchanged.

## System requirements

Besides Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/), OCR needs three system tools. 18 target files have scanned pages, and one regulation (Permenko 13/2024) is fully scanned:

| Tool | Why | macOS (development) | Debian / Ubuntu (server) |
|---|---|---|---|
| Tesseract ≥ 4.1 | OCR engine | `brew install tesseract` | `apt-get install tesseract-ocr` |
| Indonesian + English language data | `ocr_languages = "ind+eng"` | `brew install tesseract-lang` | `apt-get install tesseract-ocr-ind tesseract-ocr-eng` |
| Ghostscript | used by ocrmypdf | `brew install ghostscript` | `apt-get install ghostscript` |

`ocrmypdf` itself is a Python dependency, pinned in `uv.lock`, so `uv sync` installs the same version everywhere.

**Check a machine:** `uv run bpk-connector health` exits `2` and names anything missing. `run` and `extract` refuse to start without it, and so does `BPKConnector(...)` (it raises `EnvironmentNotReady`). A server can't silently leave scanned regulations without text. To run without OCR on purpose, set `[extraction] ocr = false`.

## Quick start

```bash
uv sync                          # Python >= 3.11; installs httpx, beautifulsoup4, pymupdf, ocrmypdf (+ pytest)
uv run pytest                    # offline: recorded BPK pages, fakes for every port

uv run bpk-connector run         # the scheduled job (daily): sync sitemaps, triage new records, check targets,
                                 #   fetch new/changed files, extract text, export, report and alert
uv run bpk-connector health      # for schedulers: exit 0 ok / 1 warning / 2 critical
uv run bpk-connector review list # records proposed for the target list; then `review approve|reject`
uv run bpk-connector status      # counts: records, targets found, candidates, files, last run
uv run bpk-connector events --since 2026-10-01   # what changed: new, amended, revoked, files, triage decisions
```

Other commands, each one stage on its own: `check`, `fetch` (`--max-mb` budget), `extract` (`--retry-unsupported`), `export` and `reparse` (re-apply the parser to stored pages). The last three need no network.

**Reports:**
- `data/reports/latest.md` and `latest.json`: each run's stages and alerts.
- `data/reports/freshness.md`: BPK's publishing lag, measured from records first seen after monitoring began.
- `data/alerts.jsonl`: every alert, appended run by run.

**Approving a candidate** (`review approve <id> --tier P2 --domain B --note "…"`) adds a row to `config/targets.csv`. Commit it as a pull request; the next run collects it.

**Exit code of `run`:** `2` when the run raised an error or critical alert. Examples: BPK blocks us (HTTP 403 or a bot challenge), a target or file is gone. An outage only pauses the run (a warning); the next run resumes.

## For the orchestrator

```python
from bpk_connector import BPKConnector

connector = BPKConnector({"config": "config/pipeline.toml"})
discovery = connector.discover(cursor=None)          # every target, every time (see 05-connector-contract.md)
fetched = connector.fetch(discovery.items[0], store)  # detail page + every official file through store.put()
```

`source_id` is `bpk:{record_id}`. `version` changes whenever BPK changes the record's fields, status, links or files. `max_concurrency = 1`. Errors arrive as the interface's `SourceUnavailable` (outage or blocked) or `ItemFailed`.

`fetch` saves, through `store.put()`:
- the detail page,
- every official file,
- the Indonesian text extracted from each file, with OCR where pages are scanned and zip annexes unpacked.

So the orchestrator gets the same artifacts as the standalone pipeline.

**Deployment (later phase):** the orchestrator (probably Airflow) runs `BPKConnector` on a server. Install the [system requirements](#system-requirements) on every worker that runs it; construction fails fast if they're missing. Until then, `bpk-connector run` collects and backfills locally.

## For the platform (contract v2)

```bash
uv run bpk-connector export --format v2 --out data/exports/v2/RUN   # no network; prints counts as JSON
```

Writes every target we hold as one [contract v2 bundle](../Metamorph-Knowledge-Platform/packages/metamorph-contract/CONTRACT_V2.md), a full snapshot that `metamorph load` reads into the platform's PostgreSQL.

- **Keys:** `source_id` is `bpk:{record_id}`, the same as `BPKConnector`.
- **IDs:** `id:{family}:{year}:{n}`, e.g. `id:uu:2023:4` or `id:pmk:2012:130` ([domain/identity.py](src/bpk_connector/domain/identity.py)). OJK's "Mengingat" citations name the same IDs, so they link up in the platform.
- **Citations:** what a regulation does to others, from BPK's "Status Peraturan" (`Mengubah` → amends, `Mencabut` → revokes, `Mencabut sebagian` → partly_revokes). The other side's labels (`Diubah dengan` …) set the regulation's own status: amended, partly revoked, revoked ([domain/standing.py](src/bpk_connector/domain/standing.py)).
- **Files and texts:** the official file (`main`), judicial-review rulings (`other`), and the text extracted from each. BPK's abstract stays out, as in the corpus.

**As a container:** the platform's Airflow runs this connector from [Dockerfile](Dockerfile), built from the workspace root, the directory holding every repository: `docker build -f BPK-Source-Connector/Dockerfile -t metamorph/bpk-connector:dev .` (or `docker compose --profile connectors build` in Metamorph-Knowledge-Platform). `data/` is bind-mounted, not copied, so scheduled runs and your own CLI runs share one store. Don't run both at once. The image includes Tesseract (`ind`, `eng`) and Ghostscript for OCR.

## How it fits together

Clean Architecture: dependencies point inward only, and `tests/test_architecture.py` enforces it.

```
cli.py · connector.py (BPKConnector) · wiring.py          entry points; wiring is the only place that knows concrete classes
  └─ adapters/   bpk/ (httpx, sitemap XML, detail HTML) · storage/ (SQLite, blobs, corpus, v2 bundle) · catalog/ (targets.csv, watch.toml)
       └─ application/   use_cases/ (sync_sitemaps, triage_new_records, check_targets, fetch_files, extract_texts,
                         export_corpus, export_bundle, report_run, review_candidates, reparse, run_pipeline)
                         · walk · ports · dto
            └─ domain/   models · targeting · changes (diff, fingerprint, one-sided links) · freshness · alerts · health
                         · identity (canonical IDs) · standing (status, outgoing relations)
```

### The corpus (`data/corpus/`)

```
regulations.jsonl                         one line per target
documents/bpk/{record_id}/
  metadata.json                           BPK fields (unchanged), status, dates, relations, files + texts, target tier
  text.id.md                              Indonesian text of the regulation (extracted from its official PDF)
  files/{category}-{file_id}.{ext}        official files, byte-for-byte (regulation, annexes, judicial-review rulings)
  texts/{category}-{file_id}.id.md        extracted text of each file, with page markers
```

## Plan and research

| Document | Contents |
|---|---|
| [00 — Overview](docs/plan/00-overview.md) | Goal, decisions D1–D4, scope, definition of done |
| [01 — Source](docs/plan/01-source.md) | BPK endpoints, fields, quirks |
| [02 — Architecture](docs/plan/02-architecture.md) | Layers, ports, use cases, data model, storage, change detection, monitoring |
| [03 — Roadmap](docs/plan/03-roadmap.md) | Milestones, and the Future section on D2's consequences |
| [04 — Risks and open questions](docs/plan/04-risks-and-open-questions.md) | |
| [05 — Connector contract](docs/plan/05-connector-contract.md) | How `BPKConnector` implements the team interface |
| [06 — Clean Architecture review](docs/plan/06-clean-architecture-review.md) | The OJK baseline reviewed; what this repo keeps or changes |
| [Pilot target list](docs/research/pilot-target-list.md) | The 93 seeds and how they were chosen |
| [Watch feasibility](docs/research/watch-feasibility.md) | Detecting new and changed records on BPK; publishing lag |
