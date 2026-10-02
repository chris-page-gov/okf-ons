# Changelog

All notable release changes are recorded here. This project follows semantic
versioning while it remains experimental; before `1.0.0`, a minor version may
include consumer migrations that would be breaking in a stable release.

## Unreleased

### Added

- Mirror the canonical Explorer v0.6.0 Bundle Wiki v1 profile byte for byte
  with its vendor lock and refresh the semantic schema pins to that release.
- Add `okf.publication.json` as the machine-readable publication-method v1
  contract, with local cross-reference, path, plane-DAG and documentation
  lockstep tests.
- Vendor and SHA-256 pin the exact Explorer Draft 2020-12 semantic-assertion
  schema, exhaustively validate every semantic assertion and semantic-mapped
  runtime row offline, and publish a digest-bound conformance receipt.
- Add negative schema-conformance fixtures and a cross-version canonical gzip
  regression vector.

- Add one deterministic relationship compiler that emits absolute semantic
  identities and predicates, local Explorer routes, matching direct triples,
  evidence-bearing `rdf:Statement`/`okf:RelationshipAssertion` nodes and rich
  `okf-relationship-assertion.v2` runtime rows.
- Add fail-closed parity checks across the semantic and runtime relationship
  planes, including stable assertion identities, authority, derivation,
  source-specific evidence, observation time and mixed record-level rights.
- Publish the complete semantic graph as digest-bound gzip JSON-LD entity and
  assertion shards behind compact YAML-LD/JSON-LD descriptors, with a
  whole-manifest triple-set reconciliation digest and a per-file size gate.
- Add a canonical OKF 0.2 Markdown layer rooted at `index.md`, with typed
  concepts for the catalogue, governed snapshot, source lanes, provider state,
  governance, standards and non-executing MCP selection.
- Add a dependency-free producer conformance checker and a machine-readable
  conformance report with concept, lifecycle and derived trust-tier counts.
- Register the pinned OKF 0.2 specification as a separately evaluated
  technical recommendation.

### Changed

- Ignore local Obsidian settings without deleting them.
- Build the ignored Pages bundle once and reuse the same workspace bytes for
  validation, assembly and upload, removing a duplicate post-build comparison.
  The contract records that a clean pre-build `--check` needs a future
  immutable baseline or release artefact because `bundle/` is not tracked.
- Make semantic gzip shards byte-identical across supported Python versions by
  fixing the full RFC 1952 header, including mtime and OS bytes.
- Standardise local, contract and CI commands on `uv sync --locked --extra test`
  followed by the repository `.venv/bin/python` interpreter.

- Classify deterministic similarity as an inferred, discovery-only
  relationship rather than equivalence, while keeping shared-table-code
  reconciliation normalised and explicitly non-equivalent.
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
