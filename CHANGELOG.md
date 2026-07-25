# Changelog

All notable release changes are recorded here. This project follows semantic
versioning while it remains experimental; before `1.0.0`, a minor version may
include consumer migrations that would be breaking in a stable release.

## Unreleased

### Added

- Add a canonical OKF 0.2 Markdown layer rooted at `index.md`, with typed
  concepts for the catalogue, governed snapshot, source lanes, provider state,
  governance, standards and non-executing MCP selection.
- Add a dependency-free producer conformance checker and a machine-readable
  conformance report with concept, lifecycle and derived trust-tier counts.
- Register the pinned OKF 0.2 specification as a separately evaluated
  technical recommendation.

### Changed

- Preserve the large-corpus Explorer profile, YAML-LD, JSON-LD, federation,
  facets, provider datapacks and integrity metadata as additive extensions.
- Emit `generated` and `sources` while retaining legacy `timestamp` and
  `# Citations` fallbacks for v0.1 consumers.
- Keep verification and freshness honest: no human `verified` event and no
  `stale_after` date are emitted without governed evidence.
- Validate the fully assembled Pages Markdown tree before publication.

## [0.2.0] - 2026-07-21

First tagged OKF-ONS release and the second public bundle identity.

### Added

- Add a deterministic, metadata-only Explore Local Statistics lane from the
  pinned ONSdigital submodule: 108 indicators, 12 explained exclusions, 46
  historical aliases and attribution across 24 producers.
- Add qualified source, operator, bundle and semantic authority, explicit
  non-endorsement, record-level rights, digest-bound JSON-LD contexts and an
  experimental governed-release envelope.
- Add producer, statistical, geography, time, unit, derivation and binding
  facets to deterministic search and comparison.
- Add snapshot and record digest bindings, audience, purpose and expiry to the
  non-executing MCP selection plan.

### Changed

- Publish snapshot `monday-2026-07-17-r2` with 5,097 records across four source
  lanes, 24 source-producer facets and 19,735 relationships.
- Negotiate MCP protocol `2025-11-25`, retaining `2025-06-18` compatibility.
- Replace the descriptor's blanket licence and single-publisher assumptions
  with mixed record-level rights and qualified authority.
- Keep ELS Git commit time distinct from acquisition time and leave its live
  execution binding explicitly planned.

### Integrity and release engineering

- Recompute and fail closed on frozen acquisition, record-set and page-receipt
  digest mismatches.
- Pin GitHub Actions by commit, verify the ELS projection byte-for-byte in CI,
  and scope workflow concurrency per branch or pull request.

### Consumer migration

- Read descriptor `rights` and record-level `license_id`, `license_source_id`
  and `rights_status` instead of assuming a scalar bundle `license`.
- Treat publisher facets as non-additive source attribution; use the qualified
  authority fields for source, operational, bundle and semantic roles.
- Verify `snapshot_binding` against the exact public `okf.get_record` digest
  subject. MCP plan consumers can adopt `selection_complete`; the existing
  `complete` field remains as a compatibility alias.

### Assurance boundary

The bundle remains a bounded metadata demonstrator. Statistical accuracy is
not certified, source attribution does not imply endorsement, ELS rights are
not yet evaluated, and checksums are not an authenticated signature.
