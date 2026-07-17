# OKF ONS Repository Guide

## Purpose

This repository publishes a metadata-only Open Knowledge Format bundle for
discovering Office for National Statistics data. It must support both people
and agents in finding the exact dataset, understanding nearby alternatives,
and producing a structurally valid MCP selection plan.

## Non-negotiable contracts

- Never store observation values, secrets, credentials, or machine-specific
  cache paths in the public bundle.
- Never claim complete ONS coverage without a source-by-source coverage ledger
  whose unexplained omission count is zero.
- Preserve source identifiers, dataset editions, versions, release dates,
  geography vintages, derivation modes, and provenance.
- Treat metadata completeness as evidence availability, not as proof that
  statistics are accurate or methodologically sound.
- Similar datasets must expose evidence-backed differences before selection.
- Standards claims must be one of `aligned`, `partial`, `not-evaluated`, or
  `not-applicable`; do not imply certification.

## Source and build boundaries

- Raw and frozen acquisitions belong in an external cache selected with
  `--cache-dir`. EXTSSD is an acquisition cache, not a publication source of
  truth.
- Checked-in source material is limited to source registers, frozen manifests,
  reconciliation evidence, evaluation fixtures, and bounded projected
  metadata snapshots. Raw response pages remain external.
- Generated public output lives under `bundle/`.
- Make generation deterministic from a frozen snapshot. Live acquisition and
  bundle compilation are separate commands.

## Validation

Run before publishing:

```bash
python -m pytest -q
python -m ruff check .
python scripts/build_bundle.py --snapshot-dir source/demo-snapshot --output bundle
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle \
  --check
node --check pages/app.js
```

The Pages workflow must validate before uploading `bundle/`.
