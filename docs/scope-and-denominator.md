# Scope and denominator

## Coverage claim

“All public ONS metadata” means every discoverable metadata object from each
registered, in-scope official source at a named snapshot date, reconciled as a
record, alias, redirect, tombstone, duplicate representation, or explained
exclusion.

The release gate is:

```text
unexplained_omissions = 0
```

Counts from different source surfaces are not additive because the same
statistical product may appear in the ONS Data API, Nomis, the ONS website,
Open Geography and data.gov.uk.

## Included

- ONS Data API datasets, editions, versions, dimensions and option metadata.
- Nomis dataset definitions, concepts, codelists, coverage and update metadata.
- ONS Open Geography Portal dataset records, spatial extents, vintages,
  variants, services and downloads.
- ONS website time-series, dataset and download metadata when it identifies or
  describes a data asset.
- Cross-source identities, succession, methodology, quality and publication
  links.

## Excluded

- Observation values and statistical cells.
- Secure or controlled microdata.
- Personal information.
- Binary data payloads already available from the source.
- Text-only publications that neither describe nor link a data asset.
- Guessed equivalence or quality claims without evidence.

## Release states

- `census`: the source universe is still being measured.
- `demonstrator`: usable end-to-end subset with explicit gaps.
- `coverage-candidate`: every source denominator is known.
- `complete-snapshot`: zero unexplained omissions for the stated snapshot.

The Monday release is a demonstrator until the ledger proves otherwise.

## Planned reconciliation lanes

The registered acquisition adapters currently cover the ONS Data API, Nomis
dataset definitions and ONS Open Geography catalogue. The top-level
`reconciliationSourceLedger` in
[`source/source-register.json`](../source/source-register.json) separately
records planned official cross-reference lanes for:

- ONS website dataset pages;
- ONS release-calendar and release pages;
- ONS Quality and Methodology Information;
- ONS time-series pages and identifiers; and
- ONS records represented on data.gov.uk.

These are reconciliation lanes, not implemented adapters. They do not
contribute to a completeness claim until an acquisition method, denominator,
stopping rule, frozen snapshot and unrepresented-record count have all been
implemented and evaluated. Their purpose is to preserve alternative
identifiers, versions, release and revision context, quality evidence,
methodology links and conflicts between official surfaces without silently
overwriting one source with another.
