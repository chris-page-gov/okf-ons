"""Compare the portable core Reader graph with an independent source import."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(projection: Path, bundle: Path = ROOT / "bundle") -> dict:
    if projection.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("independent source projection exceeds its budget")
    imported = json.loads(projection.read_bytes())
    descriptor = bundle / "okf-core-explorer.json"
    published = json.loads(descriptor.read_bytes())
    if set(published["nodes"]) != set(imported["nodes"]):
        raise ValueError("published core concept coverage differs from source")
    for route, node in published["nodes"].items():
        source = imported["nodes"][route]
        if node["frontmatter"] != source["frontmatter"] or node["body"] != source["body"]:
            raise ValueError(f"published frontmatter or body differs from source: {route}")
        path = bundle / node["source_path"]
        if not path.resolve().is_relative_to(bundle.resolve()) or path.is_symlink():
            raise ValueError(f"source path escapes the bundle: {route}")
        data = path.read_bytes()
        if (len(data) != node["source_bytes"]
                or hashlib.sha256(data).hexdigest() != node["source_sha256"]):
            raise ValueError(f"published source-byte identity differs: {route}")
    actual = {(row["source"], row["target"]) for row in published["edges"]}
    expected = {(row["source"], row["target"]) for row in imported["edges"]}
    if actual != expected:
        raise ValueError("published core reference graph differs from source")
    return {
        "schema": "okf-core-projection-parity.v1", "status": "passed",
        "concepts": len(published["nodes"]), "directed_core_reference_pairs": len(expected),
        "source_projection_sha256": hashlib.sha256(projection.read_bytes()).hexdigest(),
        "descriptor_sha256": hashlib.sha256(descriptor.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projection", type=Path)
    parser.add_argument("--bundle", type=Path, default=ROOT / "bundle")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.bundle.resolve()):
        parser.error("Write the receipt outside the published bundle")
    result = check(args.projection, args.bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(f"Independent core parity passed: {result['concepts']} concepts and "
          f"{result['directed_core_reference_pairs']} reference pairs")
