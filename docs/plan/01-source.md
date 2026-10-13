# 01 — The source: BPK legal database

`https://peraturan.bpk.go.id`, run by BPK's legal documentation network (JDIH BPK). Server-rendered HTML behind Cloudflare. No API, no RSS. Everything below was verified live on 2026-10-13. Details and measurements are in [pilot-target-list.md](../research/pilot-target-list.md) and [watch-feasibility.md](../research/watch-feasibility.md).

## Endpoints we use

| Purpose | URL | Notes |
|---|---|---|
| Sitemap index | `/sitemap.xml` | 82 yearly files + `sitemap-static.xml`. Each has a `lastmod`, updated daily |
| Yearly sitemap | `/sitemap-peraturan-{year}.xml` | One `<url>` per record: `loc` = `/Details/{id}/{slug}`, `lastmod`. The year is the regulation's year, not the upload year. 310,638 URLs in total; the 2025 file is 2.5 MB |
| Detail page | `/Details/{id}` | Redirects (301) to `/Details/{id}/{slug}`. Holds metadata, status, relations, files and the abstract |
| File download | `/Download/{fileId}/{name}.pdf` | Returns `ETag`, `Last-Modified`, `Content-Length`. Some files are very large (UU 4/2023: 82 MB) |
| Exact lookup | `/Search?jenis={id}&nomor={n}&tahun={y}` | Resolves a known regulation to its record. For PMKs, `nomor` is the leading number |
| Search (secondary only) | `/Search?...&p={page}` | 10 results per page. `sort=terbaru` **does not follow upload order**, so it isn't used for detection |

`robots.txt` disallows only `/Admin/`, `/Identity/`, `/Account/`, `/Manage/`, `/health` and `/Error`. Requests without cookies worked throughout the research (Cloudflare plus an F5 `TS…` cookie, no challenge seen at ≤ 3 requests/s).

## Identifiers

- **`id`** (the number in `/Details/{id}`) is BPK's record ID. It is stable and only increases, and is our `source_id`.
- **The slug is not an identifier.** Some slugs are wrong (POJK 26/2019 sits at `.../permenag-no-20-tahun-2019`).
- **`fileId`** identifies a file. A replaced file is expected to get a new `fileId` or a new `ETag`; the connector checks both.

## Detail page: fields

Labels as BPK shows them. They are passed through **unchanged** in `metadata["fields"]` (team interface rule 3); the mapping only says how *we* read them.

| BPK label | Meaning | Example (Permenkum 49/2025) | Used for |
|---|---|---|---|
| Tipe Dokumen | Document class | Peraturan Perundang-undangan | — |
| Judul | Full title | Peraturan Menteri Hukum Nomor 49 Tahun 2025 tentang … | title, subject |
| T.E.U. | Issuing body | Indonesia, Kementerian Hukum | issuer, watch rules |
| Nomor | Number (old PMKs: `130/PMK.010/2012`) | 49 | citation, exact lookup |
| Bentuk / Bentuk Singkat | Form / short form | Peraturan Menteri Hukum / Permenkum | citation, watch rules |
| Tahun | Year | 2025 | citation, exact lookup |
| Tempat Penetapan | Place of enactment | Jakarta | — |
| Tanggal Penetapan / Pengundangan / Berlaku | Enacted / promulgated / effective dates (Indonesian month names) | | dates, **lag measurement** |
| Sumber | Gazette reference | BN.2025 … | provenance |
| Subjek | BPK subject tags | e.g. `PERBANKAN, LEMBAGA KEUANGAN` (UU 4/2023) | watch rules |
| Status | In force or not | Berlaku / Tidak Berlaku | status |
| Bahasa, Lokasi, Bidang | Language, location, field of law | | — |
| Alias | Alternative citations | | search aid |
| STATUS PERATURAN | Typed relations, each linking `/Details/{id}` | *Diubah dengan*, *Dicabut dengan*, *Dicabut sebagian dengan*, *Mengubah*, *Mencabut*, … | relations, change detection, expansion |
| ABSTRAK | Summary written by BPK's editors | | kept in the raw snapshot only, never exported (it is BPK's text, not the regulation) |
| Files | `/Download/{fileId}/{name}` links | | file download |

The section headings contain markup (`STATUS <span>PERATURAN</span>`), so the parser must match on structure, not on literal heading text.

## Behaviour that shapes the design

| Finding | Design consequence |
|---|---|
| A record's sitemap `lastmod` **doesn't change** when a newer regulation amends or revokes it (UU 4/2023 still shows 2023-01-16 although "amended by UU 4/2026") | Re-check every target's detail page each run. The sitemap is only for new records and for edits to a record's own data |
| `lastmod` does change for edits to a record's own data (177–878 older records a month) | A `lastmod` change on a target triggers a re-fetch of its files |
| About 40–60 new records a day, ~90% regional | Fetch the detail page of every new ID (cheap) and classify it from detail fields, not the slug |
| Relations are bidirectional and link to records | The expansion rule and lineage are built from typed edges |
| Search parameters `tentang` / `keywords` OR the words together | Never use search counts. Use exact lookups only |
| Data errors exist (wrong slugs, a promulgation date in the future, possibly wrong relation links, status that lags) | Validate dates, record provenance, flag anomalies for review; never auto-correct |
| Publishing lag: median 41 days, Permenkum ~259 | Accepted under D2; measured and reported ([00-overview.md](00-overview.md#the-accepted-consequence-of-d2-bpk-publishing-lag)) |

## Not on BPK (known gaps)

- **PERMA 2/2008 (Kompilasi Hukum Ekonomi Syariah, the sharia economic law compilation).** Under D2 it stays a known gap; a source for it is in the roadmap's Future section.
- **DSN-MUI fatwas.** Owned by the DSN-MUI connector.
- **PMK 84/PMK.012/2006.** Not found; its successor rules sit with OJK.

## Terms of use

The research found no terms-of-use page restricting automated access, and `robots.txt` allows everything we fetch. The site's disclaimer says documents come from the issuing agencies and should be checked against them. M0 confirms there are no terms elsewhere, such as in the mobile app or on JDIH BPK.
