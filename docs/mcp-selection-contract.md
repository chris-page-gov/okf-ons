# MCP selection contract

The metadata broker does not execute upstream requests. It emits a read-only,
non-authorising capability request for a separate trusted execution boundary to
inspect. That boundary must revalidate the current source, evaluate expiry and
policy, and compile its own executable request. The selection plan itself must
never be treated as a bearer token or command.

The example below is abbreviated. `plan_id` is the SHA-256 of the canonical JSON
plan body before `plan_id` is added. `snapshot_binding` identifies the exact
frozen snapshot and the hydrated broker record used to prepare the plan. The
record digest subject is the `/record` value in the `okf.get_record` response
named by `record_resource`; this includes the deterministic alternative summary
returned by that tool. The same `recordBinding` object is exposed alongside the
record so a downstream verifier does not need access to an internal broker
representation.

The `okf-ons.sorted-compact-json.v1` canonicalisation profile serialises JSON as
UTF-8 with recursively sorted object keys, no insignificant whitespace,
non-ASCII characters preserved, and non-finite numbers rejected. These digests
are not a digest of the generated bundle release, a publisher signature or
authorisation.

```json
{
  "plan_id": "sha256:…",
  "schema": "okf-ons-selection-plan.v1",
  "snapshotId": "monday-2026-07-17-r2",
  "snapshot_binding": {
    "snapshot_id": "monday-2026-07-17-r2",
    "snapshot_sha256": "…",
    "record_resource": "okf://ons/record/ons-data-api%3Adataset%3ARM154",
    "record_schema": "okf-ons.mcp-record.v1",
    "record_json_pointer": "/record",
    "canonicalization": "okf-ons.sorted-compact-json.v1",
    "record_sha256": "…"
  },
  "source_as_of": "2026-07-17T19:22:40.002615Z",
  "source_as_of_basis": "provenance.retrieved_at",
  "source": "ons-data-api",
  "record_id": "ons-data-api:dataset:RM154",
  "native_id": "RM154",
  "audience": "https://example.gov.uk/statistics-query-broker",
  "audience_declared": true,
  "purpose": "Compare regional population estimates for a research brief",
  "purpose_declared": true,
  "expires_at": "2030-01-01T12:00:00Z",
  "expiry": {
    "status": "requires-live-evaluation",
    "evaluated": false,
    "required_for_execution": true,
    "evaluation_boundary": "trusted-live-execution-broker"
  },
  "inspection_tool": "ons_data.dimensions",
  "query_tool": "ons_data.query",
  "arguments": {
    "dataset": "RM154",
    "edition": "2021",
    "version": "3"
  },
  "proposed_unvalidated_arguments": {},
  "selection_complete": false,
  "frozen_metadata_validated": true,
  "live_source_validated": false,
  "authorised": false,
  "executable": false,
  "executed": false,
  "complete": false,
  "unknown_dimensions": [
    {
      "dimension": "dataset-specific dimension options",
      "record_id": "ons-data-api:dataset:RM154",
      "json_pointer": "/selection/reason"
    }
  ],
  "invalid_options": [],
  "validation": {
    "status": "requires-live-inspection",
    "identity_binding_valid": true,
    "binding_available": true,
    "live_validation_performed": false,
    "reason": "Dataset-specific dimension options must be selected before querying."
  }
}
```

## Rules

- Dataset, edition and version must be native identifiers from the bundle.
- The plan binds the exact frozen snapshot and the public hydrated MCP record by
  SHA-256. A verifier must resolve `record_resource`, select
  `record_json_pointer` from the named `record_schema`, apply the declared
  canonicalisation profile and compare `record_sha256`. Checksums do not
  authenticate the publisher or authorise use.
- `source_as_of` records the best frozen temporal evidence available, and
  `source_as_of_basis` distinguishes an actual acquisition time from a pinned
  source-commit time. A commit time is never relabelled as retrieval evidence,
  and neither form claims that the live source is still unchanged.
- `audience`, `purpose` and `expires_at` are optional for compatibility with
  existing callers. Their absence remains explicit and cannot produce an
  executable plan. Their presence binds caller intent into the plan digest but
  still does not confer permission.
- Supplied expiries are normalised to UTC. This deterministic, network-free
  broker does not consult the wall clock; the trusted live boundary must
  evaluate expiry and reject stale or replayed requests.
- Dimension names and options must belong to that exact version.
- Missing required dimensions remain explicit.
- No credential fields are accepted.
- No live call is made from GitHub Pages.
- Tool names and argument types must validate against the current MCP-Geo tool
  schemas. The bundle currently has inspection/query bindings for ONS Data API
  records. Nomis structure inspection uses the record's direct
  `def.sdmx.json` metadata URL; only a completed selection is executed through
  MCP-Geo's `nomis_query`. A general Open Geography catalogue-item MCP binding
  is explicitly `planned`, not invented.
- Explore Local Statistics indicators retain their pinned metadata URL and
  source identity, but their application API is internal and undocumented.
  Their live binding is explicitly `planned`; no execution tool is inferred
  from submodule routes.
- The metadata broker may validate frozen identity bindings only. It always
  emits `live_source_validated: false`, `authorised: false`,
  `executable: false`, and `executed: false`.
- `complete` is retained as a backward-compatible alias of
  `selection_complete`.
- A separate trusted boundary must reject any plan with an invalid digest,
  missing or expired expiry, incomplete selection, source/version drift,
  failed policy decision, or ambiguous geography.
