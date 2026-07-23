### Added

- Publish a selector-scoped Explore Local Statistics provider datapack that
  labels the governed `795eaf2` snapshot separately from the dated, external
  `d5f0ac9` reviewed reference.
- Record the non-exhaustive average-house-price coverage example (April 2026
  in the snapshot, May 2026 in the reviewed reference) as `known-drift`, while
  requiring live validation before execution or current-value claims.
- Validate source expectations fail-closed and expose snapshot-consistent
  provider manifest and pack entrypoints to OKF Explorer.
- Bind the provider manifest from the descriptor and each public pack from its
  manifest row with SHA-256 digests.
- Align producer validation with the Explorer contract for safe identifiers,
  RFC 3339 dates, credential-free HTTPS actions and path-segment templates.
