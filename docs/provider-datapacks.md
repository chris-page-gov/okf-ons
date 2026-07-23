# Provider datapacks

Provider datapacks let an OKF bundle distinguish the governed metadata it
contains from a separately reviewed external service state. They are
presentation and evidence sidecars: they do not replace record metadata, fetch
live data or authorise execution.

## Published contract

The bundle descriptor exposes `entrypoints.provider_datapacks`, while
`data/manifest.json` exposes the same path as
`indexes.provider_datapacks`. It resolves to `data/providers/manifest.json`,
whose schema is
`okf-explorer-provider-datapack-manifest.v1`. The manifest carries the same
top-level `snapshot` string as the bundle and lists selector-scoped packs.
Every listed pack also carries that top-level `snapshot` string, allowing a
consumer to reject a sidecar from another governed snapshot. The descriptor's
`entrypoint_integrity.provider_datapacks.sha256` binds the manifest bytes, and
each manifest row's `sha256` binds the exact canonical pack bytes. This keeps
dated review evidence from being replaced under an unchanged snapshot ID.

Each `okf-explorer-provider-datapack.v1` pack has:

- `selector`: an explicit record-field equality selector;
- `governedSnapshot`: facts derived and validated from the selected frozen
  records, including snapshot identity, pinned source commit, source-as-of
  evidence, record count and the metadata-only boundary;
- `reviewedLiveReference`: a dated, content-addressed reference with status
  `reviewed-reference-not-live-validated` and `network: external`;
- `comparison`: a bounded `known-drift` statement, its comparison date,
  changed fields and `executionRequiresLiveValidation: true`; and
- `presentation`: provider labels, last-checked wording, a user notice and
  explicitly external link actions.

Review and comparison dates use RFC 3339 full-date values; source revision
times use RFC 3339 date-times. Provider, pack and action IDs use the v1 safe
identifier syntax, and selectors use a bounded normalized record-field name.

The comparison uses `evidenceScope: reviewed-record-examples` and
`exhaustive: false`. A known difference therefore means that at least one
reviewed example differs. It is not a claim that every selected record was
compared with the live service or that the listed differences are complete.

## Explore Local Statistics pack

The source declaration is
`source/provider-datapacks/ons-explore-local-statistics.json`. During the
bundle build it is checked against the frozen ELS projection before the public
pack is emitted:

| Evidence | Governed snapshot | Reviewed live reference |
| --- | --- | --- |
| Source commit | `795eaf204f47986f6be248a63f857a42afe4fdf2` | `d5f0ac948f8f2f5da2dacd0011ef4e4778918b01` |
| Source date | 17 July 2026 | 22 July 2026 |
| Average house price coverage end | April 2026 | May 2026 |
| Validation meaning | Reproducible bundle input | Last checked 23 July 2026; not live-validated |

The build fails closed if the selected frozen source is no longer the pinned
108-record cohort or if the frozen average-house-price record no longer ends
at `2026-04-01/P1M`. The reviewed reference records the upstream metadata-file
digest and the later `2026-05-01/P1M` value; it is not refreshed over the
network during a deterministic build.

The `Open live indicator` action uses:

```text
https://www.ons.gov.uk/explore-local-statistics/indicators/{native_id}
```

Consumers must replace only the documented flat `{native_id}` placeholder,
which must occupy a complete path segment. They must URL-encode the replacement
as one path segment, reject unresolved placeholders and present the navigation
as external. Loading the provider service may disclose the user's network
request to that service.

The pack also supplies an `Open live service` action for bundle-level use and
a separate reviewed-commit action, so the current external destination is
never confused with the dated source evidence.

## Updating a reviewed reference

1. Review a named upstream commit and record its commit time.
2. Hash the reviewed `json-stat-metadata.json`.
3. Compare named record examples with the governed frozen projection.
4. Update the source datapack's last-checked evidence and examples.
5. If the governed snapshot itself changes, use a new immutable snapshot
   identity and update its expectations rather than overwriting an old
   snapshot.
6. Rebuild so the pack, manifest-row and descriptor-entrypoint digests change
   together.
7. Run the provider-datapack tests, the full test suite and deterministic
   bundle verification.

A normal page load must not silently turn this dated review into a live check.
Execution and current-value claims still require a separate trusted service to
validate the live provider.
