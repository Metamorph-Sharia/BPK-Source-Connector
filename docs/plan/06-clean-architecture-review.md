# 06 — Clean Architecture review: the OJK baseline, and what the BPK connector keeps or changes

The BPK connector has to follow the OJK connector's architectural principles and standards. This review checks the OJK code (as of 2026-10-13, ~4,200 lines in `src/ojk_connector/`) against Clean Architecture's dependency rule, then sets out what the BPK design copies and where it is stricter. The evidence is the actual imports between OJK's modules.

# Clean Architecture Review Report

## Summary
- **Overall assessment: Good, with two structural gaps.**
- The core is clean:
  - `models` and `identity` are pure, with no I/O.
  - Sources sit behind one port (`sources/base.py: Source`) and know nothing about storage or the pipeline.
  - The orchestrator sees only one adapter (`OJKConnector`).
  - The team interface (`source_connector.py`) is standard-library only and shared unchanged.
- **Gap 1:** the use-case modules (`pipeline.py`, `dedup.py`, `export.py`, `monitoring/health.py`, `monitoring/manager.py`) import the **concrete SQLite `Store`**, so application logic depends on infrastructure.
- **Gap 2:** `pipeline.py` (581 lines) holds every stage. It is one module with many reasons to change.
- Neither gap is urgent in OJK; it works and is well tested. The BPK connector starts clean on both, because it's cheap at the start and expensive later.

## Dependency rule analysis

| # | Finding (OJK) | Evidence | Direction | Verdict |
|---|---|---|---|---|
| 1 | Domain is pure | `identity.py` imports only `models`; `models.py` imports nothing internal | inward only | ✅ Keep |
| 2 | Sources depend on the port, not on the pipeline | `sources/regalert/source.py` imports `sources.base` and `models` only | adapter → port | ✅ Keep |
| 3 | The orchestrator adapter is the only public entry | `__init__.py` exports `OJKConnector`; it imports the interface, config, models and the sources registry | outer → inner | ✅ Keep |
| 4 | **Use cases import the concrete store** | `pipeline.py`, `dedup.py`, `export.py`, `monitoring/health.py` and `monitoring/manager.py` each `from ojk_connector.store import Store, …` | application → infrastructure | ⚠️ Violation. Fix in BPK: use cases depend on `RecordRepository` / `EventLog` ports |
| 5 | **Use cases reach a concrete source through the registry** | `pipeline.py` imports `ojk_connector.sources`, whose `__init__` imports `RegAlertSource` | application → adapter (transitively) | ⚠️ Mild violation. Fix in BPK: only `wiring.py` (the composition root) knows concrete adapters |
| 6 | Infrastructure depends on domain | `store.py` imports `identity` and `models` | outer → inner | ✅ Allowed |
| 7 | Alert rules depend on config | `monitoring/alerts.py` imports `config.MonitoringConfig` (a plain dataclass) | rule → settings DTO | ✅ Acceptable. BPK passes thresholds in as a value object |
| 8 | Data crossing boundaries is plain | `DiscoveredDocument`, `DocumentContent`, `StatusCheck` are frozen dataclasses; raw payloads travel as bytes snapshots | — | ✅ Keep |

## Layer structure review

### Entities: **Good**
`models.py` + `identity.py` are framework-free and tested on real records. BPK mirrors this in `domain/`. It moves more rules here (targeting, change diffing, freshness, alert rules), so they're testable without I/O.

### Use cases: **Needs improvement**
One `Pipeline` class runs discover, fetch, check, dedupe, reparse, export and run. It is coupled to `Store`, so it can't be tested without SQLite. BPK has one class per use case in `application/use_cases/`, each taking narrow ports in its constructor.

### Interface adapters: **Good**
`sources/regalert/` (client, auth, source) and `OJKConnector` are clear adapters. One mixed concern: `sources/__init__.py` is both the port's package and a registry of concrete classes. BPK keeps ports in `application/ports.py` and registration in `wiring.py`.

### Infrastructure: **Good**
SQLite, blobs, httpx and notifiers are isolated in their modules, with migrations and a content-addressed raw store. BPK copies this as `adapters/storage`, `adapters/bpk`, `adapters/monitoring`.

## SOLID check (where it matters here)

| Principle | OJK | BPK plan |
|---|---|---|
| SRP | `pipeline.py` has many reasons to change | One use case per module |
| OCP | New source = new `Source` class + config; no pipeline change (tested) | Same: a faster source (Future F1) is a new gateway implementation |
| LSP | Any `Source` works in the pipeline (fallback test) | Any `BpkGateway` (real, fake, future second source) works in the use cases |
| ISP | `Store` is one wide class used by every stage | Narrow ports: `RecordRepository`, `EventLog`, `BlobStore`, `TargetCatalog` |
| DIP | Followed for sources; not for storage | Followed for sources and storage, checked by `test_architecture.py` |

## Recommendations

1. **High (BPK, from M1):**
   - Use cases depend on ports only.
   - `wiring.py` is the single composition root.
   - `tests/test_architecture.py` enforces the dependency rule.
2. **High (BPK, from M1):** split use cases, one per module; keep `RunPipeline` a thin sequence.
3. **Medium (OJK, optional, any time):** introduce a `Store` protocol for `pipeline.py` / `dedup.py` / `export.py`, and move the source registry out of `sources/__init__.py`. Both are mechanical changes, already covered by OJK's tests.
4. **Long term (team):** once both connectors have identity, dedup and corpus export in pure modules, those are candidates for a shared package used by every connector. The team interface already anticipates this.

## Pitfalls we deliberately avoid

From the Clean Architecture guidance: layers are a means, not the goal.
- **No interface without a reason.** Every port has a test fake now, and `BpkGateway` and `RecordRepository` each have a planned real second implementation: a faster source (F1), and orchestrator-owned storage. Parsers, the sitemap reader and the corpus writer are plain classes, not interfaces.
- **No extra layers for their own sake.** Four rings, one package, no DI framework: constructor injection in `wiring.py`.
- **No speculative generality.** No plug-in loader and no multi-agency profiles. OJK removed those in M1.6, and BPK doesn't reintroduce them.

## Practical verification (how we'll know it pays off)

- Renaming or replacing anything in `adapters/` (e.g. switching `beautifulsoup4` for another parser, or SQLite for the orchestrator's store) changes no file in `domain/` or `application/`.
- Every use case runs in tests with in-memory fakes and no network or disk.
- Adding the Future F1 source touches `adapters/` and `wiring.py` only.
