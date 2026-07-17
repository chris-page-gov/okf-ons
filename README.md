# ONS Open Knowledge Format

`okf-ons` is a metadata-only discovery layer for public Office for National
Statistics data. It is designed to help a person or an agent find the exact
dataset, see easily confused alternatives, understand the statistical-quality
evidence that is available, and hand a validated selection to MCP for live
retrieval.

The project deliberately separates three jobs:

1. **OKF discovers and explains** datasets, versions, dimensions, provenance,
   standards evidence, and alternatives.
2. **OKF Explorer narrows and compares** a large static corpus without an LLM
   or a hosted search service.
3. **MCP executes** a live ONS or Nomis query only after the required
   dataset-specific choices are complete.

No observations, API keys, or private data are stored in the bundle.

## Monday demonstrator

The first demonstrator publishes:

- a source and coverage ledger that makes incompleteness explicit;
- a frozen 4,989-record metadata snapshot from ONS Data API (337), Nomis
  (1,617), and ONS Open Geography (3,035);
- deterministic search and first-class filter postings;
- evidence-backed alternative/contrast relationships;
- exact Census table-code reconciliation across ONS Data API and Nomis;
- statistical-quality and standards evidence without false assurance claims;
- an MCP selection-plan contract; and
- a reproducible retrieval and metadata-quality evaluation report.

The public descriptor is designed to be:

```text
https://chris-page-gov.github.io/okf-ons/okf-explorer.json
```

and to open in OKF Explorer using:

```text
https://chris-page-gov.github.io/okf-explorer/?bundle=https%3A%2F%2Fchris-page-gov.github.io%2Fokf-ons%2Fokf-explorer.json
```

## Build

```bash
python scripts/acquire_snapshot.py \
  --cache-dir /path/to/raw-cache \
  --output-dir /path/to/public-snapshots \
  --snapshot-id monday-2026-07-17
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle \
  --check
```

Acquisition is resumable and external. `bundle/` is deterministic from a
frozen snapshot.

The sendable [ONS hackathon brief](docs/ONS-HACKATHON-BRIEF.md) explains the
work package, demo route and questions for ONS. See also the
[standards register](docs/standards-register.md),
[evaluation method](docs/evaluation.md), and
[scope and denominator](docs/scope-and-denominator.md).

## What “all” means

The repository may describe itself as covering **all public ONS metadata** only
when every in-scope source in `source/source-register.json` has a measured
denominator and the generated coverage ledger reports
`unexplained_omissions = 0`.

Observation cells, secure microdata, and duplicate binary payloads are
intentionally out of scope. See
[scope and denominator](docs/scope-and-denominator.md).

## Licensing

Code is MIT licensed. Source metadata remains subject to its stated upstream
licence, normally the Open Government Licence v3.0. Generated records preserve
source and licence evidence.
