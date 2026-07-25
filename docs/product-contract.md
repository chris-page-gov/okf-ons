# Product contract

## Format contract

The public bundle has a canonical OKF 0.2 Markdown entrypoint at `index.md`.
The typed concepts carry structured provenance, generation and lifecycle
metadata while the large-corpus descriptor, shards, YAML-LD, federation,
facets, checksums and provider datapacks remain additive Explorer extensions.
Consumers must tolerate unknown types and fields.

The producer preserves the v0.1 `timestamp` and `# Citations` fallbacks during
migration. It does not emit `verified` or `stale_after` without an evidenced
verification event or governed freshness date. Structural conformance and
checksum validation are not human review, statistical assurance or runtime
attestation.

## Outcome

A user should be able to start with an intent such as “local authority
population estimates by age” and finish with:

- the correct source-qualified statistical product and version where available;
- visible alternatives that a careful statistician would consider;
- the differences that make those alternatives unsuitable or preferable;
- available methodology, quality, revisions, comparability and provenance
  evidence;
- the exact dimensions and option identifiers still required; and
- a validated, read-only MCP request plan.

## Core interaction

The interaction is **browse → reduce → compare → configure → execute**.

1. Search and facets create a reduced candidate set.
2. Near-duplicate and easily confused records remain visible.
3. A contrast view explains differences using source metadata.
4. The selected dataset version supplies its real dimensions and options.
5. A complete selection plan is emitted for MCP; OKF never silently chooses
   the first value for an unknown dimension.

## Contrast contract

Every alternative relationship records:

- a deterministic similarity score and the fields that caused it;
- shared subject concepts;
- source surface and native identifier;
- differences in population, measure, unit, geography, time, frequency,
  edition/version, release state and methodology evidence;
- relationship type such as `alternative`, `successor`, `different-grain`,
  `different-population`, `different-measure`, or `cross-source-representation`;
- provenance and confidence; and
- an explicit `not_enough_evidence` marker when metadata cannot support a
  stronger distinction.

Title similarity alone is never evidence that datasets are equivalent.

## Statistical-quality contract

The bundle preserves evidence relevant to Trustworthiness, Quality and Value,
including producer, release and revision status, methodology, quality and
methodology information, collection mode, population, units, uncertainty,
comparability, coherence, geography, time coverage and known limitations.

The bundle evaluates whether this evidence is present and internally
consistent. It does **not** certify the accuracy of observations.

## Snapshot and provider-state contract

The Explorer must label governed snapshot evidence separately from dated
references to an external provider. A provider datapack is accepted only when
its manifest, pack and bundle declare the same snapshot identity and its
manifest and pack bytes satisfy their SHA-256 bindings. Snapshot facts are
derived from the frozen corpus; a reviewed live reference remains
`reviewed-reference-not-live-validated`, identifies its last-checked date and
external network boundary, and never authorises execution.

A `known-drift` statement is scoped to its reviewed examples. Unless an
evidenced full comparison says otherwise, it remains explicitly
non-exhaustive and requires live validation before a current-value or
execution claim. See the [provider datapack contract](provider-datapacks.md).

## Agent contract

Agents receive stable identifiers, typed relationships, field-level
provenance, selection constraints and executable MCP bindings. Search
explanations and contrast reasons are deterministic and inspectable. Agents
must be able to distinguish:

- no result;
- an incomplete metadata record;
- an ambiguous candidate set;
- a complete selection plan; and
- a live upstream execution error.
