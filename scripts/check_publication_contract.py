#!/usr/bin/env python3
"""Validate local references in the OKF publication contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "okf.publication.json"


def validate_document(document: dict[str, object], root: Path = ROOT) -> list[str]:
    """Return deterministic cross-reference, path and plane-DAG errors."""
    errors: list[str] = []
    expected = {
        "schema", "modified", "locale", "time_zone", "repository",
        "semantic_contract", "source_families", "boundaries", "planes",
        "tooling", "lockstep", "ci", "publication", "verification", "limitations",
    }
    missing = sorted(expected - document.keys())
    if missing:
        return [f"missing top-level keys: {', '.join(missing)}"]
    if document.get("schema") != "okf-repository-publication-contract.v1":
        errors.append("schema must be okf-repository-publication-contract.v1")
    if (document.get("locale"), document.get("time_zone")) != ("en-GB", "Europe/London"):
        errors.append("locale and time zone must be en-GB and Europe/London")

    family_ids = [row["id"] for row in document["source_families"]]
    commands = document["tooling"]["commands"]
    command_ids = [row["id"] for row in commands]
    planes = document["planes"]
    plane_ids = [row["id"] for row in planes]
    identifiers = (
        ("source-family", family_ids),
        ("command", command_ids),
        ("plane", plane_ids),
    )
    for label, values in identifiers:
        if len(values) != len(set(values)):
            errors.append(f"{label} IDs must be unique")
    known_commands = set(command_ids)
    known_planes = set(plane_ids)
    dependencies = {row["id"]: row["depends_on"] for row in planes}
    for plane in planes:
        for dependency in plane["depends_on"]:
            if dependency not in known_planes:
                errors.append(f"plane {plane['id']} refers to unknown dependency {dependency}")
        for command_id in plane["command_ids"]:
            if command_id not in known_commands:
                errors.append(f"plane {plane['id']} refers to unknown command {command_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(plane_id: str) -> None:
        if plane_id in visiting:
            errors.append(f"plane dependency cycle includes {plane_id}")
            return
        if plane_id in visited:
            return
        visiting.add(plane_id)
        for dependency in dependencies.get(plane_id, []):
            visit(dependency)
        visiting.remove(plane_id)
        visited.add(plane_id)

    for plane_id in plane_ids:
        visit(plane_id)

    for row in document["boundaries"]["authored"]:
        family_id = row.get("source_family_id")
        if family_id is not None and family_id not in family_ids:
            errors.append(f"authored boundary {row['path']} has unknown source family {family_id}")
    for row in document["boundaries"]["generated"]:
        if row["plane"] not in known_planes:
            errors.append(f"generated boundary {row['path']} has unknown plane {row['plane']}")
        for key in ("build_command_ids", "check_command_ids"):
            for command_id in row[key]:
                if command_id not in known_commands:
                    errors.append(
                        f"generated boundary {row['path']} has unknown command {command_id}"
                    )

    lockstep = document["lockstep"]
    if lockstep.get("changelog_path") != "CHANGELOG.md":
        errors.append("lockstep changelog path must be CHANGELOG.md")
    if lockstep.get("unknown_path_policy") != "fail-closed":
        errors.append("lockstep unknown paths must fail closed")
    if lockstep.get("check_command_id") not in known_commands:
        errors.append("lockstep check command is not declared")

    fixed_paths = {
        document["repository"]["root_index"], document["semantic_contract"]["path"],
        lockstep["changelog_path"], *document["ci"]["workflow_paths"],
        *document["publication"]["authority"]["evidence_paths"],
    }
    fixed_paths.update(row["workflow_path"] for row in document["publication"]["targets"])
    for relative in sorted(fixed_paths):
        if not (root / relative).is_file():
            errors.append(f"declared local file does not exist: {relative}")
    for target in document["publication"]["targets"]:
        exact_commit = target.get("exact_commit_required") is True
        no_rebuild = target.get("promote_without_rebuild") is True
        if not exact_commit or not no_rebuild:
            errors.append(
                f"publication target {target['id']} must promote exact bytes without rebuilding"
            )
    return errors


def main() -> int:
    try:
        document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"publication contract validation failed: {exc}", file=sys.stderr)
        return 1
    errors = validate_document(document)
    if errors:
        print("publication contract validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("publication contract validated: local paths, references and plane DAG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
