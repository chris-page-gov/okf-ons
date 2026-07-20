# MCP selection contract

The bundle does not execute upstream requests. It emits a read-only plan that a
trusted MCP-Geo server can validate and run.

```json
{
  "schema": "okf-ons-selection-plan.v1",
  "source": "ons-data-api",
  "record_id": "ons-data-api:version:cpih01:time-series:42",
  "tool": "ons_data.query",
  "arguments": {
    "dataset": "cpih01",
    "edition": "time-series",
    "version": "42",
    "geography": "K02000001",
    "filters": {
      "time": "latest",
      "aggregate": "cpih1dim1G100000"
    }
  },
  "validation": {
    "complete": true,
    "unknown_dimensions": [],
    "invalid_options": []
  }
}
```

## Rules

- Dataset, edition and version must be native identifiers from the bundle.
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
- A plan with unknown dimensions, invalid options or an ambiguous geography is
  not executable.
