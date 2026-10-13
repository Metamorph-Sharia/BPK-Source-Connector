# 04 — Risks and Open Questions

## Accepted consequences (decided, not open)

| # | Consequence | Decision | Handled by |
|---|---|---|---|
| A1 | BPK publishing lag: median 41 days after promulgation; Permenkum ~259 days, PERMA ~149 | D2: BPK is the only source for now (2026-10-13) | Measured in every run (freshness report, M3); future work F1 in [03](03-roadmap.md#future-addressing-the-consequences-of-d2) |
| A2 | PERMA 2/2008 (KHES) is not collected, because it isn't on BPK | D2 | Future F2 |
| A4 | No canonical ID or cross-record dedup this phase; BPK's record ID is the key | D4: schema deferred to a later phase (2026-10-13) | Raw HTML kept, so everything re-derives offline once the schema exists |
| A3 | Relevance is decided when the list is curated, so a relevant regulation outside the targets and watch rules is missed until someone adds it | D1: targeted extraction | Watch rules + review queue (M5); targets are a reviewed file in git |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Bot protection tightens (Cloudflare challenge, F5 rules) and blocks the connector | Low–medium | High | 1 request/s, identifiable User-Agent, backoff; `source_blocked` alert. The sitemap path needs few requests. Never get around a challenge: escalate to BPK instead |
| Detail-page layout changes and the parser silently loses fields | Medium | High | Fixtures per form, `parse_fill_drop` alert, raw HTML kept so `reparse` repairs history offline |
| Sitemap stops updating or changes format | Low | High | `sitemap_empty` / `sitemap_drop` / `no_new_records` alerts; weekly full sweep; exact lookups as a cross-check |
| BPK data errors: wrong slugs, impossible dates, possibly wrong relation links, status that lags | Confirmed | Medium | Classify from detail fields, not slugs; `data_anomaly` events; keep BPK's value *and* our flag; never auto-correct |
| Relation changes are invisible in the sitemap (`lastmod` doesn't move) | Confirmed | High if not handled | `CheckTargets` re-reads every target daily (~2 minutes for 93) |
| Expansion runs away (omnibus laws link to dozens of unrelated laws) | Medium | Medium | Omnibus sources configured in `watch.toml` go to review, not auto-add; lineage capped to central forms; `lineage_added` reported every run |
| Very large PDFs (82 MB) slow or break runs | Medium | Medium | Streaming downloads, size cap and per-run budget, page-streamed extraction |
| The review queue isn't worked, and candidates pile up | Medium | Medium | `review_backlog` alert after 14 days; approvals are small PRs to `targets.csv` |
| Interface drift from the team contract | Low | Medium | Unmodified `source_connector.py` + `test_contract_copy.py`, as in OJK |
| Architecture erodes (use cases start importing SQLite or httpx) | Medium | Medium | `test_architecture.py` from M1 |
| BPK holds the same regulation twice, so two records are stored | Low | Low | Both kept (D4: no dedup this phase); `data_anomaly` when two targets share form, number and year |

## Open questions

| # | Question | Who answers | When |
|---|---|---|---|
| Q1 | ~~Include the 33 P3 lineage records in the first backfill?~~ **Answered 2026-10-13: yes** | Team | Done |
| Q2 | ~~Provide BPK metadata for OJK records?~~ **Answered 2026-10-13: no.** The OJK connector does it itself | Team | Done |
| Q3 | Who reviews the candidate queue (about 1 a day), and how often? Proposal: the BPK owner, weekly, as PRs to `targets.csv` | Team | Before M5 |
| Q4 | ~~Which route coverage does the target list assume?~~ **Answered 2026-10-13: both** routes, a sharia multifinance company and sharia P2P lending (LPBBTI) | Product | Done |
| Q5 | ~~Canonical ID format?~~ **Decided 2026-10-13: not in this phase** (D4). Only the interface is agreed; a schema that fits every agency comes after all data is collected | Team | Later phase |
| Q6 | Interface v1.1 with a candidate channel (future F4): wanted? | Team | After M5 |
| Q7 | ~~How long do we keep raw HTML of ignored records?~~ **Built as proposed: not kept.** Only the triage decision is logged (`new_record_triaged`) | Team | Done (revisit if needed) |
| Q9 | ~~Install OCR tools?~~ **Answered 2026-10-13: yes, the connector must have OCR.** `ocrmypdf` is pinned as a Python dependency; Tesseract (`ind`, `eng`) and Ghostscript are system requirements (README). Startup checks fail loudly where they're missing | Team | Done |
| Q8 | What does "current" mean for the product, and does it change D2? (Freshness target per domain) | Product | After 14 days of freshness reports (M7) |
