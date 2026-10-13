# BPK pilot extraction: initial target list

**Purpose:** decide which regulations the BPK connector extracts first. peraturan.bpk.go.id holds regulations from every ministry, agency and region, and most are unrelated to sharia multifinance or consumer lending. So this connector starts from a **curated seed list**. It does not crawl everything and filter afterwards.

**Researched:** 2026-10-13, against the live BPK database. Every record below was opened on BPK, and its status and amendment links come from its detail page.

## Summary

- **93 seed regulations** across 9 domains:

  | Tier | Count | Meaning |
  |---|---|---|
  | **P1** | 35 | Core. Directly governs the entry route or the day-to-day obligations of a sharia multifinance or lending company. Extract first. |
  | **P2** | 25 | Cross-cutting compliance that applies to any licensed lender (AML reporting, tax, disputes, credit programmes). |
  | **P3** | 33 | Lineage and context: revoked predecessors, revocation instruments, base laws. Small and cheap; kept so later phases can answer "what applied when". |

- **Not in this list, on purpose:**
  - OJK and BI regulations. BPK has 537 OJK and 640 BI records, but our OJK and BI connectors own them (see [Boundaries](#boundaries-what-the-bpk-pilot-does-not-collect)).
  - DSN-MUI fatwas. They aren't on BPK.
- **New since 2025** that the pilot must capture:
  - UU 4/2026, amending the P2SK Law
  - PP 28/2025 (risk-based licensing)
  - Permen Investasi 5/2025
  - Permenkum 49/2025 (PT establishment)
  - Permenkum 2/2025 (beneficial owners)
  - Permenko Ekon 1/2026 (new KUR guideline)
  - PP 41/2024 (OJK levies)
- **Lineage breaks found:**
  - Perpres 9/2009 on financing institutions was revoked in 2020.
  - PMK 23/PMK.010/2017 revoked the Ministry of Finance rules whose authority moved to OJK, including the old fiduciary-registration and KYC rules for financing companies.
  - Since then, the specific rules for financing companies are OJK's alone. Outside OJK, BPK holds the surrounding framework: collateral, company, licensing, AML, data, tax and disputes.

## How the list was built

1. **Started from the market-entry path** of a foreign fintech with a sharia lending model:
   1. Invest (foreign ownership, investment list)
   2. Form a PT
   3. Get licensed (OSS-RBA, then OJK)
   4. Run the business online (PSE registration, personal data)
   5. Take collateral (fiduciary)
   6. Report (AML, tax)
   7. Handle disputes (religious courts, sharia arbitration)
2. **Searched BPK** by subject facet, title keywords and issuer type, then read the results by hand.
3. **Resolved each candidate** to its BPK record by type, number and year, then **opened every detail page** for its status and "Status Peraturan" links (amended by, revoked by).
4. **Checked the web** for 2025–2026 changes that a search can miss. Sources are at the end.

### What we learned about BPK search (affects connector design)

| Finding | Implication |
|---|---|
| Subject facets (`tema`) are noisy. Of the 110 `tema=11` records ("Fidusia dan Lembaga Pembiayaan"), most are regional budget regulations. `tema=44` (banking and financial institutions) has 1,969 records. | Facets alone can't define the pilot. Combine them with central-government types (`jenis`), or use the seed list. |
| `jenis` accepts several values, combined with OR (`jenis=8&jenis=10` returns UU + PP). | One watch query can cover several regulation types. |
| `tentang` (title) and `keywords` (full text) **OR** the words together. "fatwa dewan syariah nasional" returns 71,201 records. | Treat result counts as unreliable. Use single distinctive words, or resolve exactly by `jenis` + `nomor` + `tahun`. |
| Exact lookup works: `/Search?jenis={id}&nomor={n}&tahun={y}`. For PMKs, `nomor` is the leading number (`69` for 69/PMK.03/2022). | This is how the seed list is resolved and re-checked. |
| Detail pages list typed links: *Diubah dengan, Dicabut dengan, Dicabut sebagian dengan, Mengubah, Mencabut*, each linking to `/Details/{id}`. | Lineage can be built automatically (see [Expansion rule](#expansion-rule)). |
| Status is "Berlaku" or "Tidak Berlaku". The "Berlaku mulai N tahun yang lalu" text in search results is relative. | Take dates and status from the detail page, never from search results. |
| Search results show 10 items per page (`&p={n}`). `sort=terbaru` does **not** follow upload order (see [watch-feasibility.md](watch-feasibility.md)). | Don't detect new records by polling search. Use the sitemap ID diff. |

## Target list

Columns: **Tier**, **Regulation** (short form), **Subject** (BPK title, in Indonesian), **BPK ID** (links to the record), **Status** (BPK status plus amendment and revocation links, as of 2026-10-13), and **Why it's in scope**.
"P2SK" = UU 4/2023, the financial-sector omnibus law. "LPBBTI" = OJK's term for P2P / fintech lending. "PSE" = electronic system operator. "KUR" = Kredit Usaha Rakyat, the subsidised people's business credit programme.

### A. Financial-sector framework and sharia legal basis

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P1 | UU 4/2026 | Perubahan atas Undang-Undang Nomor 4 Tahun 2023 tentang Pengembangan dan Penguatan Sektor Keuangan | [350166](https://peraturan.bpk.go.id/Details/350166) | In force | 2026 amendment to P2SK; expands financing-services and IT-based funding provisions |
| P1 | PP 41/2024 | Rencana Kerja dan Anggaran Otoritas Jasa Keuangan dan Pungutan di Sektor Jasa Keuangan | [304105](https://peraturan.bpk.go.id/Details/304105) | In force | OJK levies payable by every licensed financial institution (replaces PP 11/2014) |
| P1 | UU 4/2023 | Pengembangan dan Penguatan Sektor Keuangan | [240203](https://peraturan.bpk.go.id/Details/240203) | In force (amended by UU No. 4 Tahun 2026) | Omnibus financial-sector law; regulates financing companies, LPBBTI/fintech lending, ITSK and OJK powers; amends the Sharia Banking Law |
| P1 | UU 21/2011 | Otoritas Jasa Keuangan | [39257](https://peraturan.bpk.go.id/Details/39257) | In force (amended by UU No. 4 Tahun 2023) | OJK Law: OJK licensing and supervision mandate over non-bank financial institutions |
| P1 | UU 21/2008 | Perbankan Syariah | [39655](https://peraturan.bpk.go.id/Details/39655) | In force (amended by UU No. 6 Tahun 2023; amended by UU No. 4 Tahun 2023; amended by PERPU No. 2 Tahun 2022; +1 more) | Statutory definition of sharia principles and the DSN-MUI fatwa role, referenced by non-bank sharia rules |
| P3 | PP 5/2023 | Penyidikan Tindak Pidana di Sektor Jasa Keuangan | [241809](https://peraturan.bpk.go.id/Details/241809) | In force | Criminal investigation in the financial services sector (enforcement context) |
| P3 | PP 11/2014 | Pungutan Oleh Otoritas Jasa Keuangan | [5448](https://peraturan.bpk.go.id/Details/5448) | Revoked (revoked by PP No. 41 Tahun 2024) | Predecessor OJK levy regulation (lineage) |
| P3 | PP 89/2014 | Suku Bunga Pinjaman Atau Imbal Hasil Pembiyaan Dan Luas Cakupan Wilayah Usaha Lembaga Keuangan Mikro | [5534](https://peraturan.bpk.go.id/Details/5534) | In force | LKM financing margin and territory caps |
| P3 | UU 1/2013 | Lembaga Keuangan Mikro | [38813](https://peraturan.bpk.go.id/Details/38813) | In force (amended by UU No. 4 Tahun 2023) | Microfinance Institutions Law (alternative small-scale route, incl. sharia LKMS) |

### B. Financing institutions and collateral (fiduciary)

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P1 | Permenkumham 25/2021 | Tata Cara Pendaftaran, Perubahan, dan Penghapusan Jaminan Fidusia | [174164](https://peraturan.bpk.go.id/Details/174164) | In force | Online fiduciary registration, amendment and deletion (current procedure) |
| P1 | PP 21/2015 | Tata Cara Pendaftaran Jaminan Fidusia Dan Biaya Pembuatan Akta Jaminan Fidusia | [5585](https://peraturan.bpk.go.id/Details/5585) | In force | Fiduciary registration procedure and deed fees |
| P1 | UU 42/1999 | Jaminan Fidusia | [45374](https://peraturan.bpk.go.id/Details/45374) | In force | Fiduciary Security Law: collateral basis for vehicle and consumer-goods financing |
| P2 | Permenkumham 17/2020 | Tata Cara Permohonan Data Jaminan Fidusia | [174102](https://peraturan.bpk.go.id/Details/174102) | In force | Requests for fiduciary data |
| P2 | UU 1/2016 | Penjaminan | [37162](https://peraturan.bpk.go.id/Details/37162) | In force (amended by UU No. 4 Tahun 2023) | Guarantee Law: credit and financing guarantees (Jamkrindo/Askrindo, KUR guarantees) |
| P2 | UU 37/2004 | Kepailitan Dan Penundaan Kewajiban Pembayaran Utang | [40784](https://peraturan.bpk.go.id/Details/40784) | In force (partly revoked by UU No. 4 Tahun 2023) | Bankruptcy and PKPU: debtor insolvency and the creditor position of lenders |
| P3 | Perpres 110/2020 | Pencabutan Peraturan Presiden Nomor 9 Tahun 2009 tentang Lembaga Pembiayaan | [152710](https://peraturan.bpk.go.id/Details/152710) | In force | Revocation of Perpres 9/2009 (explains the lineage break) |
| P3 | PMK 23/PMK.010/2017 | Pencabutan Peraturan Menteri Keuangan/Keputusan Menteri Keuangan Yang Pengaturan Kewenangannya Beralih Dari Kementerian Keuangan Kepada Otoritas Jasa Keuangan | [112608](https://peraturan.bpk.go.id/Details/112608) | In force | Revocation of MoF regulations whose authority moved to OJK (explains gaps in the PMK lineage) |
| P3 | Permenkumham 10/2013 | Tata Cara Pendaftaran Jaminan Fidusia secara Elektronik | [174250](https://peraturan.bpk.go.id/Details/174250) | Revoked (revoked by Permenkumham No. 25 Tahun 2021) | Earlier e-fiduciary registration procedure (lineage) |
| P3 | Permenkumham 9/2013 | Pemberlakuan Pendaftaran Jaminan Fidusia Secara Elektronik | [133364](https://peraturan.bpk.go.id/Details/133364) | In force | Start of electronic fiduciary registration (lineage) |
| P3 | PMK 130/PMK.010/2012 | Pendaftaran Jaminan Fidusia Bagi Perusahaan Pembiayaan yang Melakukan Pembiayaan Konsumen untuk Kendaraan Bermotor dengan Pembebanan Jaminan Fidusia | [164278](https://peraturan.bpk.go.id/Details/164278) | Revoked (revoked by PMK No. 23/PMK.010/2017) | Former MoF rule requiring fiduciary registration for motor-vehicle consumer financing (revoked; lineage) |
| P3 | PMK 30/PMK.010/2010 | Penerapan Prinsip Mengenal Nasabah Bagi Lembaga Keuangan Non Bank | [174512](https://peraturan.bpk.go.id/Details/174512) | Revoked (revoked by PMK No. 23/PMK.010/2017) | Former MoF KYC rule for non-bank financial institutions (lineage) |
| P3 | Perpres 9/2009 | Lembaga Pembiayaan | [42292](https://peraturan.bpk.go.id/Details/42292) | Revoked (revoked by PERPRES No. 110 Tahun 2020) | Former Presidential regulation on Lembaga Pembiayaan, revoked in 2020: multifinance now rests on OJK/P2SK (lineage) |
| P3 | UU 4/1996 | Hak Tanggungan atas Tanah Beserta Benda-Benda yang Berkaitan dengan Tanah | [46093](https://peraturan.bpk.go.id/Details/46093) | In force | Mortgage over land, for property-backed financing |
| P3 | Keppres 61/1988 | Lembaga Pembiayaan | [64384](https://peraturan.bpk.go.id/Details/64384) | Revoked (revoked by PERPRES No. 9 Tahun 2009) | Original 1988 financing-institution decree (lineage) |

### C. Market entry: investment, company formation, business licensing

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P1 | PP 28/2025 | Penyelenggaraan Perizinan Berusaha Berbasis Risiko | [319773](https://peraturan.bpk.go.id/Details/319773) | In force | Risk-based business licensing (OSS-RBA), replacing PP 5/2021 |
| P1 | Permen Investasi 5/2025 | Pedoman dan Tata Cara Penyelenggaraan Perizinan Berusaha Berbasis Risiko dan Fasilitas Penanaman Modal Melalui Sistem Perizinan Berusaha Terintegrasi Secara Elektronik (Online Single Submission) | [332573](https://peraturan.bpk.go.id/Details/332573) | In force | Ministry of Investment guideline for risk-based licensing and investment facilities |
| P1 | Permenkum 49/2025 | Syarat dan Tata Cara Pendirian, Perubahan, dan Pembubaran Badan Hukum Perseroan Terbatas | [350901](https://peraturan.bpk.go.id/Details/350901) | In force | Establishing, amending and dissolving a PT (current Ministry of Law procedure) |
| P1 | UU 6/2023 | Penetapan Peraturan Pemerintah Pengganti Undang-Undang Nomor 2 Tahun 2022 tentang Cipta Kerja menjadi Undang-Undang | [246523](https://peraturan.bpk.go.id/Details/246523) | In force (amended by UU No. 5 Tahun 2026; amended by UU No. 1 Tahun 2026; amended by UU No. 2 Tahun 2025; +8 more) | Job Creation Law: amends the PT, investment and licensing laws |
| P1 | Perpres 10/2021 | Bidang Usaha Penanaman Modal | [161806](https://peraturan.bpk.go.id/Details/161806) | In force (amended by PERPRES No. 49 Tahun 2021) | Positive Investment List: foreign-ownership openness by business field |
| P1 | Perpres 49/2021 | Perubahan atas Peraturan Presiden Nomor 10 Tahun 2021 Tentang Bidang Usaha Penanaman Modal | [168534](https://peraturan.bpk.go.id/Details/168534) | In force | Amendment to the Positive Investment List |
| P1 | UU 25/2007 | Penanaman Modal | [39903](https://peraturan.bpk.go.id/Details/39903) | In force (amended by UU No. 6 Tahun 2023; amended by PERPU No. 2 Tahun 2022; amended by UU No. 11 Tahun 2020) | Investment Law: foreign direct investment (PMA) framework |
| P1 | UU 40/2007 | Perseroan Terbatas | [39965](https://peraturan.bpk.go.id/Details/39965) | In force (amended by UU No. 6 Tahun 2023; amended by PERPU No. 2 Tahun 2022; amended by UU No. 11 Tahun 2020) | Limited Liability Company Law: the legal-entity form required for financing companies and LPBBTI |
| P2 | Per. BKPM 5/2021 | Pedoman dan Tata Cara Pengawasan Perizinan Berusaha Berbasis Risiko | [169019](https://peraturan.bpk.go.id/Details/169019) | In force | BKPM supervision of risk-based licensing (investment activity reporting, LKPM) |
| P2 | PP 34/2021 | Penggunaan Tenaga Kerja Asing | [161898](https://peraturan.bpk.go.id/Details/161898) | In force | Foreign worker permits (expatriate directors and commissioners) |
| P2 | UU 7/2011 | Mata Uang | [39182](https://peraturan.bpk.go.id/Details/39182) | In force (partly revoked by UU No. 1 Tahun 2023; amended by UU No. 4 Tahun 2023) | Currency Law: mandatory Rupiah use for domestic transactions |
| P2 | UU 24/1999 | Lalu Lintas Devisa dan Sistem Nilai Tukar | [45335](https://peraturan.bpk.go.id/Details/45335) | In force | Foreign-exchange flows: offshore funding and capital movements |
| P3 | Perpu 2/2022 | Cipta Kerja | [234926](https://peraturan.bpk.go.id/Details/234926) | In force (amended by UU No. 4 Tahun 2023) | Job Creation Perppu (lineage) |
| P3 | PP 5/2021 | Penyelenggaraan Perizinan Berusaha Berbasis Risiko | [161835](https://peraturan.bpk.go.id/Details/161835) | Revoked (revoked by PP No. 28 Tahun 2025; partly revoked by PP No. 11 Tahun 2023) | Previous risk-based licensing PP (lineage) |
| P3 | Per. BKPM 4/2021 | Pedoman dan Tata Cara Pelayanan Perizinan Berusaha Berbasis Risiko dan Fasilitas Penanaman Modal | [168903](https://peraturan.bpk.go.id/Details/168903) | In force | Previous BKPM licensing guideline (lineage) |
| P3 | Permenkumham 21/2021 | Syarat dan Tata Cara Pendaftaran Pendirian, Perubahan, dan Pembubaran Badan Hukum Perseroan Terbatas | [174160](https://peraturan.bpk.go.id/Details/174160) | Revoked (revoked by Permenkum No. 49 Tahun 2025) | Previous PT registration procedure (lineage) |
| P3 | UU 11/2020 | Cipta Kerja | [149750](https://peraturan.bpk.go.id/Details/149750) | Revoked (revoked by UU No. 6 Tahun 2023; revoked by PERPU No. 2 Tahun 2022; partly revoked by UU No. 1 Tahun 2022; +10 more) | Original Job Creation Law (lineage; replaced) |
| P3 | UU 13/2003 | Ketenagakerjaan | [43013](https://peraturan.bpk.go.id/Details/43013) | In force (amended by UU No. 6 Tahun 2023; amended by PERPU No. 2 Tahun 2022; amended by UU No. 11 Tahun 2020) | Manpower Law (base for foreign-worker rules) |

### D. Digital operations: electronic systems and data protection

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P1 | UU 1/2024 | Perubahan Kedua atas Undang-Undang Nomor 11 Tahun 2008 tentang Informasi dan Transaksi Elektronik | [274494](https://peraturan.bpk.go.id/Details/274494) | In force | Second ITE amendment |
| P1 | UU 27/2022 | Pelindungan Data Pribadi | [229798](https://peraturan.bpk.go.id/Details/229798) | In force | Personal Data Protection Law: borrower data processing |
| P1 | Permenkominfo 10/2021 | Perubahan atas Peraturan Menteri Komunikasi dan Informatika Nomor 5 Tahun 2020 tentang Penyelenggara Sistem Elektronik Lingkup Privat | [203121](https://peraturan.bpk.go.id/Details/203121) | In force | Amendment to the private-scope PSE regulation |
| P1 | Permenkominfo 5/2020 | Penyelenggara Sistem Elektronik Lingkup Privat | [203049](https://peraturan.bpk.go.id/Details/203049) | In force (amended by Permenkominfo No. 10 Tahun 2021) | Private-scope PSE registration: required for lending apps |
| P1 | PP 71/2019 | Penyelenggaraan Sistem dan Transaksi Elektronik | [122030](https://peraturan.bpk.go.id/Details/122030) | In force | Electronic systems and transactions (PSE registration, e-signature, data localisation) |
| P1 | UU 19/2016 | Perubahan Atas Undang-Undang Nomor 11 Tahun 2008 Tentang Informasi Dan Transaksi Elektronik | [37582](https://peraturan.bpk.go.id/Details/37582) | In force (partly revoked by UU No. 1 Tahun 2023; amended by UU No. 1 Tahun 2024) | First ITE amendment |
| P1 | UU 11/2008 | Informasi dan Transaksi Elektronik | [37589](https://peraturan.bpk.go.id/Details/37589) | In force (partly revoked by UU No. 1 Tahun 2023; amended by UU No. 1 Tahun 2024; amended by UU No. 19 Tahun 2016) | Electronic Information and Transactions Law: e-contracts, e-signatures, electronic system operators |
| P2 | Permenkominfo 20/2016 | Perlindungan Data Pribadi Dalam Sistem Elektronik | [150543](https://peraturan.bpk.go.id/Details/150543) | In force | Personal data protection in electronic systems (pre-UU PDP ministerial rule) |
| P3 | PP 80/2019 | Perdagangan Melalui Sistem Elektronik | [126143](https://peraturan.bpk.go.id/Details/126143) | In force | E-commerce trading regulation (partner-merchant financing context) |

### E. AML/CFT and beneficial ownership

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P1 | Permenkum 2/2025 | Verifikasi dan Pengawasan Pemilik Manfaat Korporasi | [314767](https://peraturan.bpk.go.id/Details/314767) | In force | Verification and supervision of corporate beneficial ownership (current) |
| P1 | PP 61/2021 | Perubahan atas Peraturan Pemerintah Nomor 43 Tahun 2015 tentang Pihak Pelapor Dalam Pencegahan dan Pemberantasan Tindak Pidana Pencucian Uang | [165479](https://peraturan.bpk.go.id/Details/165479) | In force | Amendment adding fintech and other reporting parties |
| P1 | Perpres 13/2018 | Penerapan Prinsip Mengenali Pemilik Manfaat dari Korporasi dalam Rangka Pencegahan dan Pemberantasan Tindak Pidana Pencucian Uang dan Tindak Pidana Pendanaan Terorisme | [73583](https://peraturan.bpk.go.id/Details/73583) | In force | Beneficial ownership disclosure for corporations |
| P1 | PP 43/2015 | Pihak Pelapor Dalam Pencegahan Dan Pemberantasan Tindak Pidana Pencucian Uang | [5611](https://peraturan.bpk.go.id/Details/5611) | In force (amended by PP No. 61 Tahun 2021) | Reporting parties for AML, including financing companies |
| P1 | UU 9/2013 | Pencegahan dan Pemberantasan Tindak Pidana Pendanaan Terorisme | [38846](https://peraturan.bpk.go.id/Details/38846) | In force (partly revoked by UU No. 1 Tahun 2023) | Counter-terrorist-financing Law |
| P1 | UU 8/2010 | Pencegahan dan Pemberantasan Tindak Pidana Pencucian Uang | [38547](https://peraturan.bpk.go.id/Details/38547) | In force (partly revoked by UU No. 1 Tahun 2023) | AML Law: financing companies and LPBBTI are reporting parties |
| P2 | Per. PPATK 1/2024 | Tata Cara Pengenaan Sanksi Administratif Atas Pelanggaran Kewajiban Pelaporan | [301756](https://peraturan.bpk.go.id/Details/301756) | In force | Administrative sanctions for reporting failures |
| P2 | Per. PPATK 14/2023 | Pedoman Pencegahan Pendanaan Proliferasi Senjata Pemusnah Massal Dan Pemblokiran Secara Serta Merta Atas Dana Milik Orang Atau Korporasi Termasuk Yang Terkait Dengan Orang Atau Korporasi Dalam Daftar Pendanaan Proliferasi Senjata Pemusnah Massal Bagi Penyedia Barang Dan/Atau Jasa Lain Dan Profesi Serta Perposan Sebagai Penyedia Jasa Giro | [272064](https://peraturan.bpk.go.id/Details/272064) | In force | Counter-proliferation financing and immediate blocking |
| P2 | Per. PPATK 1/2021 | Tata Cara Penyampaian Laporan Transaksi Keuangan Mencurigakan, Transaksi Keuangan Tunai, Transaksi Keuangan Transfer Dana Dari Dan Ke Luar Negeri Melalui Aplikasi Goaml Bagi Penyedia Jasa Keuangan | [168891](https://peraturan.bpk.go.id/Details/168891) | In force | Filing STR, CTR and other reports to PPATK |
| P2 | Per. PPATK 2/2021 | Tata Cara Penyampaian Laporan Transaksi dan Laporan Transaksi Keuangan mencurigakan Melalui Aplikasi GOAML Bagi Penyedia Barang dan/ atau Jasa Lain | [168889](https://peraturan.bpk.go.id/Details/168889) | In force | Filing reports through goAML |
| P2 | Per. PPATK 14/2021 | Petunjuk Teknis Penggunaan Aplikasi goAML bagi Pihak Pelapor | [222254](https://peraturan.bpk.go.id/Details/222254) | In force | goAML technical guide for reporting parties |
| P2 | Per. PPATK 11/2021 | Sistem Informasi Terduga Pendanaan Terorisme | [222250](https://peraturan.bpk.go.id/Details/222250) | In force | Terrorist-financing suspect information system (SIPENDAR) |
| P2 | Per. PPATK 11/2020 | Tata Cara Pemanfaatan Aplikasi Politically Exposed Person | [172796](https://peraturan.bpk.go.id/Details/172796) | In force | PEP screening application |
| P3 | Perpres 88/2025 | Perubahan Kedua atas Peraturan Presiden Nomor 6 Tahun 2012 tentang Komite Koordinasi Nasional Pencegahan dan Pemberantasan Tindak Pidana Pencucian Uang | [327888](https://peraturan.bpk.go.id/Details/327888) | In force | Second amendment to the AML committee Perpres |
| P3 | UU 1/2023 | Kitab Undang-Undang Hukum Pidana | [234935](https://peraturan.bpk.go.id/Details/234935) | In force (amended by UU No. 1 Tahun 2026) | New Criminal Code: partially revokes criminal provisions of the AML and ITE laws; effective January 2026 |
| P3 | Permenkumham 15/2019 | Tata Cara Pelaksanaan Penerapan Prinsip Mengenali Pemilik Manfaat dari Korporasi | [133129](https://peraturan.bpk.go.id/Details/133129) | In force | Previous BO implementation rule (lineage) |
| P3 | Permenkumham 21/2019 | Tata Cara Pengawasan Penerapan Prinsip Mengenali Pemilik Manfaat dari Korporasi | [133134](https://peraturan.bpk.go.id/Details/133134) | Revoked (revoked by Permenkum No. 2 Tahun 2025) | Previous BO supervision rule (lineage) |
| P3 | Perpres 6/2012 | Komite Koordinasi Nasional Pencegahan dan Pemberantasan Tindak Pidana Pencucian Uang | [41249](https://peraturan.bpk.go.id/Details/41249) | In force (amended by Perpres No. 88 Tahun 2025; amended by PERPRES No. 117 Tahun 2016) | National AML coordination committee |

### F. Consumer protection and dispute resolution

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P1 | PERMA 14/2016 | Tata Cara Penyelesaian Ekonomi Syariah | [209692](https://peraturan.bpk.go.id/Details/209692) | In force | Procedure for sharia economic disputes in religious courts |
| P1 | UU 3/2006 | Perubahan atas Undang-Undang Nomor 7 Tahun 1989 tentang Peradilan Agama | [40154](https://peraturan.bpk.go.id/Details/40154) | In force | Gives religious courts jurisdiction over sharia economic disputes (Art. 49) |
| P1 | UU 8/1999 | Perlindungan Konsumen | [45288](https://peraturan.bpk.go.id/Details/45288) | In force | Consumer Protection Law: standard clauses and consumer rights in financing contracts |
| P2 | PERMA 4/2019 | Perubahan atas Peraturan Mahkamah Agung Nomor 2 Tahun 2015 tentang Tata Cara Penyelesaian Gugatan Sederhana | [206070](https://peraturan.bpk.go.id/Details/206070) | In force | Small-claims amendment (raises the ceiling, adds e-court) |
| P2 | PERMA 2/2015 | Tata Cara Penyelesaian Gugatan Sederhana | [209475](https://peraturan.bpk.go.id/Details/209475) | In force (amended by Perma No. 4 Tahun 2019) | Small-claims procedure (consumer debt recovery) |
| P2 | UU 50/2009 | Perubahan Kedua atas Undang-Undang Nomor 7 Tahun 1989 tentang Peradilan Agama | [38795](https://peraturan.bpk.go.id/Details/38795) | In force | Second amendment to the Religious Courts Law |
| P2 | UU 30/1999 | Arbitrase dan Alternatif Penyelesaian Sengketa | [45348](https://peraturan.bpk.go.id/Details/45348) | In force | Arbitration and ADR (Basyarnas, LAPS SJK) |
| P2 | UU 7/1989 | Peradilan Agama | [46804](https://peraturan.bpk.go.id/Details/46804) | In force (amended by UU No. 50 Tahun 2009; amended by UU No. 3 Tahun 2006) | Religious Courts Law (base) |
| P3 | PERMA 1/2016 | Prosedur Mediasi di Pengadilan | [209641](https://peraturan.bpk.go.id/Details/209641) | In force | Court-annexed mediation |
| P3 | PERMA 5/2016 | Sertifikasi Hakim Ekonomi Syariah | [209661](https://peraturan.bpk.go.id/Details/209661) | In force | Certification of sharia-economy judges |
| P3 | PP 58/2001 | Pembinaan Dan Pengawasan Penyelenggaraan Perlindungan Konsumen | [52959](https://peraturan.bpk.go.id/Details/52959) | In force | Guidance and supervision of consumer protection |

### G. Tax

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P1 | PMK 69/PMK.03/2022 | Pajak Penghasilan dan Pajak Pertambahan Nilai atas Penyelenggaraan Teknologi Finansial | [215543](https://peraturan.bpk.go.id/Details/215543) | In force | Income tax and VAT on fintech services, including lending interest and returns |
| P1 | PMK 137/PMK.03/2011 | Pengenaan Pajak Penghasilan untuk Kegiatan Usaha Pembiayaan Syariah | [173659](https://peraturan.bpk.go.id/Details/173659) | In force | Income tax for sharia financing businesses |
| P1 | PP 25/2009 | Pajak Penghasilan Kegiatan Usaha Berbasis Syariah | [4940](https://peraturan.bpk.go.id/Details/4940) | In force | Income tax on sharia-based business activities (tax-neutral treatment of sharia contracts) |
| P2 | PMK 81/2024 | Ketentuan Perpajakan dalam Rangka Pelaksanaan Sistem Inti Administrasi Perpajakan | [306614](https://peraturan.bpk.go.id/Details/306614) | In force (amended by PMK No. 1 Tahun 2026; amended by PMK No. 54 Tahun 2025; amended by PMK No. 53 Tahun 2025) | Core-tax consolidated provisions (may supersede earlier PMKs) |
| P2 | UU 7/2021 | Harmonisasi Peraturan Perpajakan | [185162](https://peraturan.bpk.go.id/Details/185162) | In force (amended by UU No. 6 Tahun 2023) | Tax harmonisation law (VAT and income-tax changes affecting financial services) |

### H. Government credit programmes and financial inclusion

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P2 | Permenko Ekon 1/2026 | Pedoman Pelaksanaan Kredit Usaha Rakyat | [342969](https://peraturan.bpk.go.id/Details/342969) | In force | Current KUR guideline (channel for financing companies and sharia lenders) |
| P2 | Perpres 114/2020 | Strategi Nasional Keuangan Inklusif | [154566](https://peraturan.bpk.go.id/Details/154566) | In force | National financial inclusion strategy |
| P3 | Permenko Ekon 7/2025 | Perubahan Ketiga Atas Peraturan Menteri Koordinator Bidang Perekonomian Republik Indonesia Nomor 1 Tahun 2022 Tentang Pedoman Pelaksanaan Kredit Usaha Rakyat | [323494](https://peraturan.bpk.go.id/Details/323494) | In force | Third amendment to the 2022 KUR guideline (lineage) |
| P3 | Permenko Ekon 13/2024 | Pedoman Relaksasi Restrukturisasi Kredit Usaha Rakyat | [347826](https://peraturan.bpk.go.id/Details/347826) | In force | KUR restructuring relaxation |
| P3 | Permenko Ekon 1/2022 | Pedoman Pelaksanaan Kredit Usaha Rakyat | [198380](https://peraturan.bpk.go.id/Details/198380) | Revoked (revoked by Permenko Perekonomian No. 1 Tahun 2026; amended by Permenko Perekonomian No. 7 Tahun 2025; amended by Permenko Perekonomian No. 12 Tahun 2025; +1 more) | Previous KUR guideline (lineage) |
| P3 | Keppres 14/2015 | Komite Kebijakan Pembiayaan Bagi Usaha Mikro, Kecil, Dan Menengah | [54415](https://peraturan.bpk.go.id/Details/54415) | In force (amended by Keppres No. 19 Tahun 2015) | MSME financing policy committee |

### I. Sharia-economy institutions

| Tier | Regulation | Subject (BPK title) | BPK ID | Status | Why it's in scope |
|---|---|---|---|---|---|
| P2 | Perpres 28/2020 | Komite Nasional Ekonomi dan Keuangan Syariah | [132021](https://peraturan.bpk.go.id/Details/132021) | In force | National Committee for Sharia Economy and Finance (KNEKS) |
| P3 | Perpres 91/2016 | Komite Nasional Keuangan Syariah | [40995](https://peraturan.bpk.go.id/Details/40995) | Revoked (revoked by PERPRES No. 28 Tahun 2020) | Predecessor committee KNKS (lineage) |

## Keeping the list current

A fixed list goes stale. Two mechanisms keep it current while keeping the pilot targeted.

### Expansion rule

On every run, re-open the detail page of each seed and follow its "Status Peraturan" links:

| Link on a seed | Action |
|---|---|
| *Diubah dengan* (amended by), *Dicabut dengan* (revoked by), *Dicabut sebagian dengan* (partly revoked by) | **Auto-add** the target with the seed's tier. This is how a new amendment, such as UU 4/2026 for P2SK, gets in without anyone acting. Mark the seed revoked or amended. |
| *Mencabut* (revokes), *Mengubah* (amends), pointing at an older regulation | Add the target as **P3 lineage**, but only if it is a central-government type (UU, Perpu, PP, Perpres, ministerial or agency regulation, PERMA). |
| *Mengubah* from an omnibus law (UU 4/2023, UU 6/2023, UU 11/2020) | **Do not auto-follow.** UU 4/2023 amends about 25 laws, including pensions, capital markets and commodity futures, and UU 6/2023 amends dozens more. Following them would undo the targeting, so those targets go to the review queue. |

### Watch queries (find new regulations)

These rules define *what* to watch. Matches go to a **review queue**, and a person adds them to the seed list. This is scoping by issuer and title, with no AI classification and nothing auto-ingested.

*How* new records are detected is covered in [watch-feasibility.md](watch-feasibility.md). In short, the connector does not poll these searches. It diffs BPK's daily sitemaps for new record IDs, reads each new record's detail page, and applies these rules to the detail fields. `sort=terbaru` turned out not to follow upload order, so polling the first page can miss records. The queries below were used for sizing; W6 stays as a secondary exact-lookup check.

| # | Query | What it catches | Size measured 2026-10-13 |
|---|---|---|---|
| W1 | `tema=44&jenis=8&jenis=9&jenis=10&jenis=11` | New financial-sector UU, Perpu, PP, Perpres | 228 |
| W2 | `tema=11&jenis=8&jenis=10&jenis=11&jenis=42&jenis=46&jenis=272` | Fiduciary and financing-institution rules, without regional noise | 19 (vs 110 unfiltered) |
| W3 | `tema=29` | AML/CFT (includes BI/OJK records, which are skipped) | 31 |
| W4 | `tentang=syariah` + central `jenis` | Anything with "syariah" in the title (SBSN items are filtered by the exclusions below) | 76 central (387 incl. regional) |
| W5 | Per issuer, newest first: `jenis=272` (Permenkum), `278` (Permenkomdigi), `280` (Permen Investasi), `221` and `81` (PPATK), `208` (Permenko Ekon), `42` (PMK), `95` (PERMA) | New ministerial rules. A title keyword list sends matches to review: *fidusia, perseroan, pemilik manfaat, pengguna jasa, sistem elektronik, data pribadi, perizinan berusaha, penanaman modal, kredit usaha rakyat, teknologi finansial, syariah, pembiayaan* | small: 16–156 per issuer |
| W6 | Exact lookups for expected regulations | Implementing PP for the PDP Law (none found yet); the Perpres replacing the 2021 investment list (in drafting) | — |

## Boundaries: what the BPK pilot does not collect

| Excluded | Why | Where it comes from instead |
|---|---|---|
| POJK, SEOJK, OJK board regulations (`jenis=80`, `212`; `entitas=584`; 537 records) | Owned by the **OJK connector**. Its roadmap (M2) already plans BPK as a *metadata* source for POJK. | OJK connector. Open question 2 asks whether this repo should provide that BPK metadata. |
| PBI, SEBI (`jenis=78`, `79`; `entitas=583`; 640 records) | Owned by the **BI connector** (payments, Rupiah use, foreign-debt reporting) | BI connector |
| DSN-MUI fatwas | Not on BPK: MUI is not an issuer there | DSN-MUI connector |
| PERMA 2/2008, Kompilasi Hukum Ekonomi Syariah (KHES) | **Not found on BPK**, although it is the main codification of sharia contract law used by religious courts | Gap: source it from JDIH Mahkamah Agung (open question 4) |
| Regional regulations (Perda, Pergub, Perbup, Perwali, Qanun) | Not relevant to national licensing and compliance; they are the main noise in the subject facets | — |
| State sukuk (SBSN): about 60 PP/PMK | Government financing, not private lending | — |
| Sharia insurance, sharia banks, LPS bank resolution, hajj funds (BPKH), housing savings (Tapera), export financing (LPEI) | Other sectors or routes | — |
| Savings-and-loan cooperatives (KSP/KSPPS) | Not a realistic route for a foreign-owned lender | Revisit if the team wants to compare routes |

## Data-quality notes

- **Slugs are not identifiers.** The OJK team found a wrong slug (POJK 26/2019 at `/permenag-no-20-tahun-2019`). Key records on the numeric ID.
- **Relationship errors.** ~~PMK 81/2024 "amended by PMK 53/2025" looked wrong from PMK 53/2025's title~~; *corrected 2026-10-13:* PMK 53/2025's own page does list "Mengubah PMK 81/2024", so the links agree. The connector's one-sided-link check found a real case instead: Permenkumham 1/2016 lists Permenkumham 21/2021 as both "revoked by" and "amended by", while 21/2021 only says it revokes 1/2016.
- **Status may lag.** Peraturan BKPM 4/2021 still shows "Berlaku" (in force), with no link to Permen Investasi 5/2025, which covers the same ground. Permenkumham 9/2013 still shows in force although the procedure it started was replaced in 2021. Treat BPK status as a claim to check against the issuer.
- **PMK 69/PMK.03/2022** (fintech tax) shows in force with no links. Later core-tax PMKs (81/2024 and its amendments) may have absorbed parts of it. Check.
- **Old records lack status.** Several pre-1970 laws show no "Berlaku" text in results. That doesn't affect this list, but the parser must allow missing fields.

## Open questions for the team

1. **Include P3 lineage in the pilot?** Recommendation: yes. It is 33 small records, and it lets later phases explain *why* a rule changed (the MoF-to-OJK transfer, the 2020 revocation).
answer: Yes include it
2. **POJK metadata from BPK:** should this connector also provide BPK metadata and links for OJK records, for the OJK connector's M2? Doing so adds 537 metadata-only records, but no extra documents to download.
answer: no. OJK connector will do it 
3. ~~**Is automatic watching feasible?**~~ **Answered in [watch-feasibility.md](watch-feasibility.md): yes.** Daily sitemap diff for new records, daily detail-page re-checks for seed updates, about 5 minutes and 150–250 requests a day. The limit is BPK's publishing lag: median 41 days, and months for Permenkum and PERMA. Still for the team: who reviews the queue (about 1 candidate a day), and whether to add a faster second source for slow issuers.
4. **KHES source:** does someone own PERMA 2/2008 (Mahkamah Agung JDIH)?
answer: nobody "owns" PERMA 2/2008 in terms of private copyright or intellectual property. The regulation was issued by the Supreme Court of Indonesia
5. **Route coverage:** the list assumes two routes, a sharia multifinance company (PP Syariah / UUS) and sharia LPBBTI. Confirm before going wider (e.g. sharia BPRS or a bank partnership).
answer: both

## Sources

BPK database (primary):
- Search and facets: https://peraturan.bpk.go.id/Search
- Each record is linked in the tables above (`https://peraturan.bpk.go.id/Details/{id}`).
- Earlier BPK notes from the OJK connector: `../OJK-Source-Connector/docs/plan/01-sources.md`

Web checks for 2025–2026 changes:
- Investment list still Perpres 10/2021 + 49/2021, replacement in drafting: [DDTC News](https://news.ddtc.co.id/berita/nasional/1817066/pemerintah-akan-perbarui-perpres-terkait-bidang-usaha-penanaman-modal)
- Permenkomdigi 5/2025 covers *public*-scope PSE only; private scope is still Permenkominfo 5/2020 + 10/2021: [Crowe regulatory brief](https://www.crowe.com/id/news/regulatory-brief-permenkomdigi-no-5-tahun-2025-lingkup-publik), [Prolegal](https://prolegal.id/?p=35734)
- PDP Law implementing PP not yet enacted (latest reports are drafts): [Hukumonline](https://www.hukumonline.com/berita/a/pemerintah-libatkan-publik-dalam-penyusunan-aturan-turunan-uu-pdp-lt64f55ed284320), [Bisnis](https://teknologi.bisnis.com/read/20240131/84/1737003/pp-perlindungan-data-pribadi-rampung-pertengahan-2024-termasuk-soal-wasit)
- UU 4/2026 (P2SK amendment) scope: [Investortrust](https://www.investortrust.id/macro/107243/uu-p2sk-resmi-direvisi-ini-deretan-pembaruan-krusial-sektor-keuangan-indonesia), [SIP Law Firm](https://siplawfirm.id/resources/uu-p2sk-resmi-diubah), [IKPI](https://ikpi.or.id/uu-p2sk-revisi-buka-peluang-pembiayaan-lebih-besar-bagi-umkm/)
- PMK 69/PMK.03/2022 content: [DDTC News](https://news.ddtc.co.id/berita/nasional/38668/pinjam-dari-pinjol-ilegal-peminjam-potong-dan-setor-pph-23-sendiri)
- KUR guideline changes: [Kemenko Perekonomian](https://ekon.go.id/unduh/publikasi/6114/resmi-target-kur-2025-naik-menjadi-rp300-triliun), [BPK record of Permenko 7/2025](https://peraturan.bpk.go.id/Details/323494)
