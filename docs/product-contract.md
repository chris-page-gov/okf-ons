# Product contract

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
