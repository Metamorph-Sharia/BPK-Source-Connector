# 00 — Overview

## Goal

Build a reliable, maintainable, automated ingestion pipeline that **discovers, downloads, extracts, normalizes and monitors** a targeted set of Indonesian regulations published on the **BPK legal database** (peraturan.bpk.go.id).

This repository covers **BPK only**. Each other regulator or source has its own repository (OJK, BI, DSN-MUI). All of them implement the same [team connector interface](../../contract/CONNECTOR_INTERFACE.md), so the orchestrator in the next phase (probably Airflow) runs them alike.

The pipeline is part of the data foundation for a later AI-powered market-entry and compliance platform for international businesses entering Indonesia's sharia multifinance and consumer lending markets.

## Decisions this plan is built on

| # | Decision | Date | Consequence |
|---|---|---|---|
| D1 | **Targeted extraction from the start.** BPK holds about 310,000 records from every ministry, agency and region, and most are unrelated to sharia financing. We collect a curated [target list](../research/pilot-target-list.md) (93 seeds) plus their amendment lineage, and not everything. | 2026-10-13 | Differs from the OJK connector, which collects broadly. Relevance is decided once, by people, when the list is curated. There is no classifier (rule-based or AI) at run time. |
| D2 | **BPK is the only source for now.** Development focuses on collecting from BPK with the target list. No second source. | 2026-10-13 | **We accept BPK's publishing lag** (below) as a known consequence of this decision. It's tracked in [03-roadmap.md § Future](03-roadmap.md#future-addressing-the-consequences-of-d2) and [04](04-risks-and-open-questions.md). |
| D4 | **No canonical ID scheme yet.** The team has agreed only on the connector interface. A common document schema and ID format will be designed in a later phase, once every agency's data is collected, so it fits all of them. | 2026-10-13 | Everything is keyed by BPK's record ID (`bpk:{record_id}`). There is no cross-record deduplication. Fields are passed through unchanged. |
| D3 | **Same architecture and standards as the OJK connector**, with the dependency rule enforced more strictly (see [06-clean-architecture-review.md](06-clean-architecture-review.md)). | 2026-10-13 | Each team member can read either repository. Shared stages (identity, dedup, extraction) can later move into a common package. |

### The accepted consequence of D2: BPK publishing lag

The connector picks up a record **within a day of BPK publishing it**. BPK publishes most regulations weeks or months after they are enacted. Measured on 63 central-government records from 2025–2026 ([watch-feasibility.md](../research/watch-feasibility.md)):

| | Days from promulgation to appearing on BPK |
|---|---|
| Median | 41 |
| 75th percentile | 108 |
| 90th percentile | 198 |
| Slowest issuers in our scope | Permenkum (Ministry of Law): median 259 days. PERMA (Supreme Court): median 149 days |

So the corpus will lack newly enacted rules for weeks to months, especially on company formation, fiduciary registration, beneficial ownership and sharia dispute procedure. Under D2 this is **expected behaviour, not a defect**. The connector **measures and reports it** for every target (enacted date vs first seen), so a future decision to add a faster source is based on data.

## Scope

### In scope
- **The target list:**
  - 93 seed regulations in 9 domains, tiers P1/P2/P3 ([pilot-target-list.md](../research/pilot-target-list.md))
  - seeds added later through review
  - regulations automatically added by the [expansion rule](../research/pilot-target-list.md#expansion-rule): amendments and revocations of targets
- **Discovery** of new BPK records (daily sitemap diff) and **watch rules** that put matching new records in a review queue.
- **Change detection** on every target: amended, revoked, status changed, metadata changed, file replaced, removed.
- **Download** of BPK's detail page and every official file (PDF), kept byte-for-byte.
- **Extraction** of Indonesian text from the PDFs, with OCR for scanned files.
- **Normalization within BPK:** typed dates, status and relations between regulations, with provenance, keyed by BPK's own record ID. BPK's fields are always kept unchanged beside them. **No cross-agency canonical ID or schema in this phase** (D4).
- **Local storage** as a self-contained, rights-labelled corpus: the input for the knowledge database in a later phase.
- **Monitoring:** run reports, alerts, health check, freshness and lag report.
- **The team interface** (`BPKConnector`), so the orchestrator can run this connector like the others.

### Out of scope for this phase
- Any source other than peraturan.bpk.go.id (D2). Candidates are listed in the roadmap's Future section.
- OJK and BI regulations (`jenis` 80, 212, 78, 79). The OJK and BI connectors own them.
- DSN-MUI fatwas (not on BPK; the DSN-MUI connector owns them).
- Relevance classification at run time, rule-based or AI. The watch rules only *propose* candidates; people decide.
- Legal interpretation, compliance advice, extracting obligations, Q&A or RAG, a user-facing app, dashboards beyond the run report.

## Plan documents

| File | Contents |
|---|---|
| [01-source.md](01-source.md) | BPK as a source: endpoints, fields, mappings, quirks |
| [02-architecture.md](02-architecture.md) | Layers, ports, use cases, data model, storage, change detection, monitoring, repository layout |
| [03-roadmap.md](03-roadmap.md) | Milestones with exit criteria, and the Future section for D2's consequences |
| [04-risks-and-open-questions.md](04-risks-and-open-questions.md) | Risks, mitigations, decisions still needed |
| [05-connector-contract.md](05-connector-contract.md) | How `BPKConnector` implements the team interface v1.0 |
| [06-clean-architecture-review.md](06-clean-architecture-review.md) | The OJK baseline reviewed against Clean Architecture, and what this repo keeps or changes |

Research behind the plan: [pilot-target-list.md](../research/pilot-target-list.md), [watch-feasibility.md](../research/watch-feasibility.md).

## Definition of done for this phase

1. Every target has a record with BPK's metadata, status, relations and every official file stored with its sha256. Any target BPK lacks is listed with a reason.
2. Every stored PDF has extracted Indonesian text with a quality score. Scanned files are OCR'd.
3. A new BPK record that **amends or revokes a target** is added automatically. A new record that matches a watch rule appears in the review queue. Both happen **within 24 hours of BPK publishing it**, with no one intervening. (Not within 24 hours of enactment: see D2.)
4. A change to a target (status, relations, files, metadata) is recorded as an event within 24 hours of BPK showing it.
5. Every run writes a machine-readable health report. When the source breaks (empty sitemap, falling parse rate, blocked requests), the run fails loudly instead of quietly ingesting nothing.
6. Reruns are idempotent: unchanged pages and files are not downloaded again or duplicated.
7. `data/corpus/` holds, for every target, its official PDF, its Indonesian text and its metadata. It is readable offline and holds only exportable content.
8. Every run reports **freshness**: for each target, enacted date, first seen on BPK, and the lag. This is the evidence base for revisiting D2.
9. `BPKConnector` implements the team interface v1.0 and passes the interface checklist.
