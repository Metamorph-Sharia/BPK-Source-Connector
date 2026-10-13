# Can the BPK connector pick up new and updated regulations automatically?

**Question:** with peraturan.bpk.go.id as it is today, can the connector detect new or updated regulations in our [pilot scope](pilot-target-list.md) and fetch them without a person checking the site?

**Researched:** 2026-10-13, against the live site:
- all 83 sitemaps (310,638 records)
- 93 seed detail pages
- a sample of 64 central-government records from 2025–2026
- HTTP headers and a request-rate test

## Answer

**Yes, it's feasible. Detection is cheap and reliable. BPK's own publishing lag is the real limit on freshness.**

| Need | Feasible? | How |
|---|---|---|
| Detect **new** regulations | Yes, reliably | Diff the daily sitemaps for new record IDs, then fetch each new record's detail page and apply the watch rules |
| Detect **updates** to regulations we hold (amended, revoked, status change) | Yes, but not through the sitemap | Re-fetch every seed's detail page on each run (about 2 minutes for 93 seeds) and diff the metadata and links |
| Detect **replaced PDFs** | Yes | Conditional `GET` with `ETag` / `Last-Modified` |
| Detect **removed** records | Yes | A weekly full sitemap sweep: an ID that disappears means a removal |
| Get regulations **soon after enactment** | **Only as soon as BPK publishes them** | Median 41 days after promulgation; 90th percentile 198 days. Varies widely by issuer (table below) |

Fetching happens within a day of BPK publishing a record. Whether the corpus is current depends on BPK. For PMK, BPK is usually within 3 weeks. For Ministry of Law regulations (Permenkum) and Supreme Court regulations (PERMA), it is often 5–9 months behind.

## What BPK offers for change detection

| Surface | Exists? | Useful for | Finding |
|---|---|---|---|
| RSS / Atom feed | No | — | `/rss`, `/feed` and similar return 404 |
| Public API | No | — | `/api`, `/swagger` return 404. The site is server-rendered HTML. |
| **Sitemap index** `/sitemap.xml` | Yes | Which year files changed | 82 yearly files + 1 static. Each has a `lastmod`, updated daily (2026 and 2025 changed on 2026-10-12/13). |
| **Yearly sitemaps** `/sitemap-peraturan-{year}.xml` | Yes | **New records**, edits, removals | Every URL has its own `lastmod`. 310,638 URLs, only 11 without `lastmod`. The year is the regulation's year, not the upload year. |
| Search `sort=terbaru` ("newest") | Yes | **Not** for detecting new records | It doesn't sort by upload time. PMK 65/2026 (promulgated 8 Sep 2026, ID 357338) ranks below PMK 63/2026 (ID 353754), and Permenkum comes back in ascending order. Polling the first page can miss records. |
| Detail page `/Details/{id}` | Yes | Status, dates, amendment and revocation links, file IDs | Gives the authoritative status and links. No "last updated" field. |
| PDF `/Download/{fileId}/{name}` | Yes | Detecting file changes | Returns `ETag`, `Last-Modified`, `Content-Length`, `cache-control: max-age=86400`. |

### The sitemap's `lastmod` doesn't move when a regulation is amended or revoked

The *amended by* and *revoked by* links on an older record seem to be computed from the newer record. Adding them doesn't touch the older record's `lastmod`:

| Seed | Sitemap `lastmod` | What its detail page says now |
|---|---|---|
| UU 4/2023 (P2SK) | 2023-01-16 | Amended by UU 4/2026 (promulgated 2026-06-17) |
| PP 5/2021 | 2022-03-28 | Revoked by PP 28/2025 |
| Permenkumham 21/2021 | 2021-08-05 | Revoked by Permenkum 49/2025 |
| Permenko Ekon 1/2022 | 2022-02-18 | Revoked by Permenko Ekon 1/2026 |

So the sitemap is good for **new records**, but **updates to seeds must be checked on their detail pages**. `lastmod` does move for edits to a record's own data: 177–878 older records a month get a new `lastmod` (corrections, re-uploads). Those are worth re-fetching when they are seeds.

Amendments are caught twice: on the seed's detail page, and as a new record whose own page says *Mengubah* (amends) or *Mencabut* (revokes) a seed.

## BPK's publishing lag (enactment → on BPK)

Measured on 63 central-government records from 2025–2026, sampled across 10 issuer types. Lag runs from the promulgation date (*Tanggal Pengundangan*) to an upper bound on the upload date. Record IDs only increase, so a record was uploaded no later than the earliest `lastmod` among itself and all higher IDs.

| | Days |
|---|---|
| Median | **41** |
| 25th percentile | 21 |
| 75th percentile | 108 |
| 90th percentile | 198 |
| Max | 350 |
| Within 30 days | 21 of 63 (33%) |
| Within 60 days | 38 of 63 (60%) |
| Over 90 days | 18 of 63 (29%) |

By issuer (n = 6–7 each, except PPATK with 2):

| Issuer type | Median lag (days) | Max | Our watch scope |
|---|---|---|---|
| PMK (Minister of Finance) | 19 | 96 | Tax, fintech tax |
| PPATK | 27 | 50 | AML reporting |
| Permenkomdigi | 33 | 67 | Electronic systems |
| UU (laws) | 37 | 98 | Core laws |
| PP | 39 | 61 | Licensing, AML, levies |
| Perpres | 43 | 65 | Investment list, beneficial owners |
| Permenko Perekonomian | 72 | 198 | KUR |
| POJK (for comparison) | 120 | 350 | OJK connector's scope |
| PERMA (Supreme Court) | 149 | 220 | Sharia dispute procedure |
| **Permenkum (Ministry of Law)** | **259** | 302 | **PT formation, fiduciary, beneficial owners** |

Notes:
- The upper bound overstates the lag when a record was edited soon after upload. The per-issuer pattern is still clear: Permenkum and PERMA arrive in large batches (four Permenkum 2025 regulations all appeared on 2026-07-09; four PERMA 2025 regulations on 2026-05-28).
- UU 4/2026 was fast (5 days), so high-profile laws can arrive quickly.
- One data error turned up: POJK 8/2026 has a promulgation date of **2026-12-06**, which is in the future (probably 2026-06-12). The parser should flag impossible dates.

## Volume and cost of a daily run

New records per month, counted with the same ID ordering:

| Month (2026) | New records | Regional | Central | From our watch issuers (by slug) |
|---|---|---|---|---|
| July | 1,166 | 1,004 | 162 | 36 |
| August | 1,551 | 1,424 | 127 | 17 |
| September | 1,827 | 1,770 | 57 | 24 |

So BPK adds about 40–60 records a day. About 2–5 are central-government, and about 1 a day comes from a watch issuer.

| Step | Requests per run | Data |
|---|---|---|
| Sitemap index | 1 | ~6 KB |
| Year sitemaps whose `lastmod` changed (usually the current year plus a few back) | 3–10 | 2–15 MB |
| Detail page for **every** new ID, so the filter doesn't depend on slugs (known to be wrong sometimes) | 40–60 | ~200 KB each |
| Re-check every seed's detail page | ~93 now, growing slowly | ~200 KB each |
| PDF conditional `GET` for seeds whose file list changed | usually 0–5 | 304 when unchanged. Full PDFs can be large: UU 4/2023 is **82 MB**. |
| **Total** | **~150–250 requests, ~5 min at 1 request/s** | — |
| Weekly full sweep (detects removals) | 83 sitemaps | 57 MB, 214 s at 1 file/s |

**Access:**
- `robots.txt` allows `/Details`, `/Download`, `/Search` and the sitemaps.
- The site sits behind Cloudflare and sets an F5 cookie (`TS…`), but requests without cookies worked throughout this research.
- A burst of 40 detail pages at ~3 requests/s returned 200 every time. About 600 requests at 1/s earlier in the research had no failures.

## Recommended design

1. **New-record path (daily):**
   1. Fetch `/sitemap.xml`.
   2. Re-fetch the yearly files whose `lastmod` changed.
   3. Diff against the stored ID set.
   4. Fetch the detail page of every new ID.
   5. Classify it from the detail page's own fields (`Bentuk`, `T.E.U.`, `Subjek`, title), not from the slug.
   6. Match the [watch rules](pilot-target-list.md#watch-queries-find-new-regulations):
      - a central-government issuer in the watch list, plus a title keyword or subject; or
      - an *amends* or *revokes* link pointing at a seed.
   7. Auto-add amendments and revocations of seeds, following the [expansion rule](pilot-target-list.md#expansion-rule). Everything else goes to the review queue.
2. **Seed path (daily):** re-fetch each seed's detail page and hash its status, dates, links and file IDs. When the hash changes:
   - record a change event (amended, revoked, status flip, new file);
   - download any new or changed files with conditional `GET`.
3. **Weekly full sweep:** fetch all 83 sitemaps to find removed IDs and anything the daily diff missed.
4. **Search is secondary:** use exact lookups (`jenis` + `nomor` + `tahun`) for regulations we expect (the PDP Law's implementing PP, the next investment-list Perpres). Don't use `sort=terbaru` for detection.
5. **Monitor freshness:** alert when no new IDs have appeared for N days (a sign the source broke or BPK stopped publishing). Track each seed's lag (promulgated → first seen) so we know which issuers BPK is slow for.
6. **Be polite:** 1 request/s, an identifying User-Agent, exponential backoff on 403/429/5xx, and a health alert if Cloudflare starts serving challenges.

## Risks

| Risk | Likelihood | Effect | Mitigation |
|---|---|---|---|
| **Publishing lag** for Permenkum and PERMA (months) | High (measured) | The corpus misses rules in force: PT formation, fiduciary, beneficial owners, sharia dispute procedure | Accept for the pilot and show "first seen" dates. Evaluate a faster second source for those issuers (open question below). |
| Bot protection tightens (Cloudflare challenge, F5 rules) | Low–medium | The connector stops | Rate limit, backoff, health alerts. The sitemap path needs few requests. |
| Sitemap stops updating or changes format | Low | New records missed | Freshness alert, weekly full sweep, and exact lookups as a cross-check |
| Wrong data (slugs, future dates, missing links) | Medium (seen) | Misclassified or wrongly dated records | Classify from detail fields, validate dates, flag oddities for review |
| Large PDFs (80+ MB) | Medium | Slow or failed downloads | Streaming downloads, size limits per run, conditional GET |

## Open questions

1. **Faster source for slow issuers:** is a second discovery source worth adding for Permenkum and PERMA? Candidates are peraturan.go.id (Ministry of Law's national database) and JDIH Kemenkum / JDIH MA. *Not evaluated here.*
2. **Review queue owner and cadence:** about 1 candidate a day from watch issuers, plus auto-added amendments. Who reviews it, and how often? (This was question 3 in the target list. It is now a team decision, not a feasibility question.)
3. **Freshness target:** what does "current" mean for the product? The median lag of 41 days may be fine for a market-entry overview, but not for "rules in force today" on PT formation or fiduciary.
