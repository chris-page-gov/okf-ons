"""Dependency-free OKF v0.2 Markdown rendering and producer validation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

OKF_VERSION = "0.2"
OKF_SPECIFICATION = (
    "https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/"
    "3fcbb9f828c2f23d109c855ee403c3a4c81f3a96/okf/SPEC.md"
)
_DATE_HEADING = re.compile(r"^## \d{4}-\d{2}-\d{2}$", re.MULTILINE)
_ACTOR = re.compile(
    r"^(?:(?:human|process):[^\s:]+|[^/\s:]+/[^/\s]+)$"
)


class OKFConformanceError(ValueError):
    """Raised when generated Markdown violates the repository's OKF contract."""


@dataclass(frozen=True)
class ParsedDocument:
    """A parsed generated Markdown document."""

    frontmatter: dict[str, Any] | None
    body: str


def render_frontmatter(fields: Mapping[str, Any]) -> str:
    """Render a deterministic YAML 1.2 frontmatter subset.

    JSON values are valid YAML 1.2 values. Keeping one JSON value per YAML key
    makes the public documents dependency-free to build while remaining
    readable by general YAML parsers.
    """

    rows = ["---"]
    for key, value in fields.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            raise OKFConformanceError(f"unsafe frontmatter key: {key}")
        rows.append(
            f"{key}: "
            + json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    rows.append("---")
    return "\n".join(rows) + "\n"


def render_concept(fields: Mapping[str, Any], body: str) -> str:
    """Render one OKF concept document."""

    return render_frontmatter(fields) + "\n" + body.strip() + "\n"


def parse_generated_document(path: Path) -> ParsedDocument:
    """Parse the dependency-free YAML subset emitted by this repository."""

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ParsedDocument(frontmatter=None, body=text)
    closing = text.find("---\n", 4)
    if closing < 0:
        raise OKFConformanceError(f"{path}: frontmatter is not closed")
    frontmatter: dict[str, Any] = {}
    for line_number, line in enumerate(text[4:closing].splitlines(), start=2):
        key, separator, encoded = line.partition(":")
        if not separator or not key or not encoded.strip():
            raise OKFConformanceError(
                f"{path}:{line_number}: frontmatter must be one key and JSON value"
            )
        try:
            value = json.loads(encoded.strip())
        except json.JSONDecodeError as exc:
            raise OKFConformanceError(
                f"{path}:{line_number}: frontmatter value is not valid YAML 1.2 JSON"
            ) from exc
        if key in frontmatter:
            raise OKFConformanceError(
                f"{path}:{line_number}: duplicate frontmatter key {key!r}"
            )
        frontmatter[key] = value
    return ParsedDocument(frontmatter=frontmatter, body=text[closing + 4 :])


def _datetime(value: Any, label: str) -> None:
    if not isinstance(value, str) or "T" not in value:
        raise OKFConformanceError(f"{label} must be a non-empty ISO 8601 datetime")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OKFConformanceError(f"{label} must be an ISO 8601 datetime") from exc


def _date(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise OKFConformanceError(f"{label} must be an ISO 8601 date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise OKFConformanceError(f"{label} must be an ISO 8601 date") from exc


def _actor(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _ACTOR.fullmatch(value):
        raise OKFConformanceError(f"{label} must use the OKF actor convention")


def _usage_window(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        raise OKFConformanceError(f"{label} must be a mapping")
    for key in ("from", "to"):
        if value.get(key) is not None:
            _date(value[key], f"{label}.{key}")
    if value.get("from") and value.get("to") and value["from"] > value["to"]:
        raise OKFConformanceError(f"{label}.from must not be after {label}.to")


def _validate_optional_families(
    path: Path,
    fields: Mapping[str, Any],
    body: str,
) -> None:
    generated = fields.get("generated")
    if generated is not None:
        if not isinstance(generated, Mapping) or not generated.get("by"):
            raise OKFConformanceError(f"{path}: generated.by is required")
        _actor(generated["by"], f"{path}: generated.by")
        if generated.get("at") is not None:
            _datetime(generated["at"], f"{path}: generated.at")
    if "timestamp" in fields:
        _datetime(fields["timestamp"], f"{path}: timestamp")

    sources = fields.get("sources")
    if sources is not None:
        if not isinstance(sources, list):
            raise OKFConformanceError(f"{path}: sources must be a list")
        for index, source in enumerate(sources):
            if not isinstance(source, Mapping) or not source.get("resource"):
                raise OKFConformanceError(
                    f"{path}: sources[{index}].resource is required"
                )
            last_modified = source.get("last_modified")
            if last_modified is not None:
                _date(last_modified, f"{path}: sources[{index}].last_modified")
            if source.get("author") is not None:
                _actor(source["author"], f"{path}: sources[{index}].author")
            usage_count = source.get("usage_count")
            if usage_count is not None and (
                isinstance(usage_count, bool)
                or not isinstance(usage_count, int)
                or usage_count < 0
            ):
                raise OKFConformanceError(
                    f"{path}: sources[{index}].usage_count must be a non-negative integer"
                )
            if source.get("usage_window") is not None:
                _usage_window(
                    source["usage_window"],
                    f"{path}: sources[{index}].usage_window",
                )
    if fields.get("usage_window") is not None:
        _usage_window(fields["usage_window"], f"{path}: usage_window")

    verified = fields.get("verified")
    if verified is not None:
        events = verified if isinstance(verified, list) else [verified]
        if not events:
            raise OKFConformanceError(f"{path}: verified must not be empty")
        for index, event in enumerate(events):
            if not isinstance(event, Mapping) or not event.get("by"):
                raise OKFConformanceError(f"{path}: verified[{index}].by is required")
            _actor(event["by"], f"{path}: verified[{index}].by")
            _datetime(event.get("at"), f"{path}: verified[{index}].at")

    status = fields.get("status")
    if status is not None and status not in {"draft", "stable", "deprecated"}:
        raise OKFConformanceError(f"{path}: unsupported lifecycle status {status!r}")
    if "stale_after" in fields:
        _date(fields["stale_after"], f"{path}: stale_after")

    if fields.get("type") == "Attested Computation":
        if not fields.get("runtime"):
            raise OKFConformanceError(
                f"{path}: Attested Computation requires a runtime"
            )
        parameters = fields.get("parameters", [])
        if not isinstance(parameters, list):
            raise OKFConformanceError(f"{path}: parameters must be a list")
        for index, parameter in enumerate(parameters):
            if (
                not isinstance(parameter, Mapping)
                or not isinstance(parameter.get("name"), str)
                or not parameter["name"]
                or not isinstance(parameter.get("type"), str)
                or not parameter["type"]
                or not isinstance(parameter.get("required"), bool)
            ):
                raise OKFConformanceError(
                    f"{path}: parameters[{index}] requires non-empty name/type and boolean required"
                )
        computation = fields.get("computation")
        inline = bool(
            re.search(r"(?ims)^#\s+Computation\s*$.*?```.+?```", body)
        )
        if not computation and not inline:
            raise OKFConformanceError(
                f"{path}: Attested Computation requires a computation path or inline fence"
            )
        if computation and inline:
            raise OKFConformanceError(
                f"{path}: Attested Computation must use a computation path "
                "or inline fence, not both"
            )
        executor = fields.get("executor")
        if (
            not isinstance(executor, Mapping)
            or not executor.get("resource")
            or not isinstance(executor.get("receipt"), list)
            or not executor["receipt"]
            or any(not isinstance(value, str) or not value for value in executor["receipt"])
        ):
            raise OKFConformanceError(
                f"{path}: Attested Computation requires executor.resource "
                "and non-empty receipt fields"
            )
        attester = fields.get("attester")
        if not isinstance(attester, Mapping) or not attester.get("resource"):
            raise OKFConformanceError(
                f"{path}: Attested Computation requires attester.resource"
            )


def validate_okf_bundle(root: Path) -> dict[str, Any]:
    """Validate the generated bundle against the structural OKF v0.2 rules."""

    root = root.resolve()
    root_index = root / "index.md"
    if not root_index.is_file():
        raise OKFConformanceError("bundle root index.md is required by this profile")

    concept_paths: list[str] = []
    verified_human = 0
    verified_machine = 0
    unverified = 0
    legacy_fallbacks = 0
    lifecycle_counts = {"draft": 0, "stable": 0, "deprecated": 0}

    markdown_paths = sorted(root.rglob("*.md"))
    for path in markdown_paths:
        relative = path.relative_to(root).as_posix()
        document = parse_generated_document(path)
        if path.name == "index.md":
            if path == root_index:
                if document.frontmatter != {"okf_version": OKF_VERSION}:
                    raise OKFConformanceError(
                        "root index.md must declare only okf_version 0.2"
                    )
            elif document.frontmatter is not None:
                raise OKFConformanceError(
                    f"{relative}: subordinate index.md must not have frontmatter"
                )
            continue
        if path.name == "log.md":
            if document.frontmatter is not None:
                raise OKFConformanceError(
                    f"{relative}: log.md must not have frontmatter"
                )
            if not _DATE_HEADING.search(document.body):
                raise OKFConformanceError(
                    f"{relative}: log.md requires an ISO date heading"
                )
            continue

        fields = document.frontmatter
        if fields is None:
            raise OKFConformanceError(f"{relative}: concept frontmatter is required")
        concept_type = fields.get("type")
        if not isinstance(concept_type, str) or not concept_type.strip():
            raise OKFConformanceError(f"{relative}: non-empty type is required")
        _validate_optional_families(path, fields, document.body)
        concept_paths.append(relative)

        verified = fields.get("verified")
        if verified is None:
            unverified += 1
        else:
            events = verified if isinstance(verified, list) else [verified]
            if any(str(event["by"]).startswith("human:") for event in events):
                verified_human += 1
            else:
                verified_machine += 1

        status = fields.get("status", "stable")
        lifecycle_counts[status] += 1
        if "timestamp" in fields and re.search(
            r"^# Citations\s*$", document.body, re.MULTILINE
        ):
            legacy_fallbacks += 1

    return {
        "schema": "okf-ons-okf-conformance.v1",
        "specification": {
            "version": OKF_VERSION,
            "resource": OKF_SPECIFICATION,
        },
        "entrypoint": "index.md",
        "status": "aligned",
        "markdownDocumentCount": len(markdown_paths),
        "conceptCount": len(concept_paths),
        "conceptPaths": concept_paths,
        "trustTiers": {
            "humanReviewed": verified_human,
            "machineConfirmed": verified_machine,
            "unverified": unverified,
        },
        "lifecycle": lifecycle_counts,
        "legacyV01FallbackCount": legacy_fallbacks,
        "unknownExtensionFieldsAllowed": True,
        "observationValuesIncluded": False,
    }
