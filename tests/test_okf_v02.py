from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.okf import (  # noqa: E402
    OKFConformanceError,
    parse_generated_document,
    render_concept,
    render_frontmatter,
    validate_okf_bundle,
)


def _root(bundle: Path) -> None:
    bundle.mkdir()
    (bundle / "index.md").write_text(
        render_frontmatter({"okf_version": "0.2"}) + "\n# Test bundle\n",
        encoding="utf-8",
    )


def test_unknown_types_and_extension_fields_remain_conformant(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _root(bundle)
    concept = {
        "type": "Provider-specific knowledge card",
        "title": "Example",
        "generated": {
            "by": "process:test-producer",
            "at": "2026-07-25T11:08:21Z",
        },
        "timestamp": "2026-07-25T11:08:21Z",
        "status": "draft",
        "sources": [{"resource": "https://example.test/source"}],
        "provider_extension": {"kept": True},
    }
    (bundle / "example.md").write_text(
        render_concept(
            concept,
            "# Notes\n\nUnknown fields are additive.\n\n"
            "# Citations\n\n- [Source](https://example.test/source)",
        ),
        encoding="utf-8",
    )

    report = validate_okf_bundle(bundle)

    assert report["status"] == "aligned"
    assert report["conceptCount"] == 1
    assert report["legacyV01FallbackCount"] == 1
    parsed = parse_generated_document(bundle / "example.md")
    assert parsed.frontmatter is not None
    assert parsed.frontmatter["provider_extension"] == {"kept": True}


def test_bare_verified_mapping_is_one_machine_confirmation(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _root(bundle)
    fields = {
        "type": "Reference",
        "verified": {
            "by": "process:nightly-validation",
            "at": "2026-07-25T02:00:00Z",
        },
    }
    (bundle / "verified.md").write_text(
        render_concept(fields, "# Evidence\n\nChecked."),
        encoding="utf-8",
    )

    report = validate_okf_bundle(bundle)

    assert report["trustTiers"]["machineConfirmed"] == 1


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({}, "non-empty type"),
        ({"type": "Attested Computation"}, "requires a runtime"),
        (
            {"type": "Reference", "sources": [{"title": "Missing resource"}]},
            r"sources\[0\]\.resource",
        ),
        (
            {
                "type": "Reference",
                "verified": {"by": "human:reviewer", "at": "not-a-date"},
            },
            r"verified\[0\]\.at",
        ),
        (
            {
                "type": "Reference",
                "generated": {"by": "unknown-actor", "at": "2026-07-25T00:00:00Z"},
            },
            r"generated\.by",
        ),
        (
            {
                "type": "Reference",
                "sources": [{
                    "resource": "scope descriptor",
                    "usage_count": -1,
                }],
            },
            r"usage_count",
        ),
        (
            {
                "type": "Attested Computation",
                "runtime": "python",
            },
            r"computation path or inline fence",
        ),
    ],
)
def test_invalid_concepts_fail_closed(
    tmp_path: Path,
    fields: dict[str, object],
    message: str,
) -> None:
    bundle = tmp_path / "bundle"
    _root(bundle)
    (bundle / "invalid.md").write_text(
        render_concept(fields, "# Notes\n\nInvalid."),
        encoding="utf-8",
    )

    with pytest.raises(OKFConformanceError, match=message):
        validate_okf_bundle(bundle)


def test_frontmatter_values_are_valid_json_and_yaml_12_subset() -> None:
    document = render_frontmatter(
        {
            "type": "Reference",
            "sources": [{"resource": "../source.json", "title": "Source"}],
            "unknown": {"nested": [True, False, None]},
        }
    )
    lines = document.splitlines()[1:-1]

    parsed = {
        key: json.loads(value.strip())
        for line in lines
        for key, _, value in [line.partition(":")]
    }

    assert parsed["type"] == "Reference"
    assert parsed["unknown"] == {"nested": [True, False, None]}
