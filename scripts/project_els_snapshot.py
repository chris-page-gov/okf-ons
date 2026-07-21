#!/usr/bin/env python3
"""Project a pinned Explore Local Statistics submodule into safe public metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.els import ELSProjectionError, canonical_json, project_els_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--submodule-dir",
        type=Path,
        default=ROOT / "vendor" / "explore-local-statistics-app",
        help="Pinned ELS application checkout to project",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--submodule-commit",
        help="Expected full Git commit; discovered from a clean checkout when omitted",
    )
    parser.add_argument(
        "--commit-as-of",
        help=(
            "ISO 8601 Git commit time evidence; verified against Git when available "
            "and required for a Git-less copied checkout"
        ),
    )
    parser.add_argument(
        "--retrieved-at",
        help=(
            "Actual ISO 8601 frozen acquisition/retrieval time; omitted by default "
            "and never inferred from the Git commit time"
        ),
    )
    parser.add_argument("--metadata-sha256", help="Expected indicator metadata SHA-256")
    parser.add_argument("--manifest-sha256", help="Expected indicator manifest SHA-256")
    parser.add_argument("--aliases-sha256", help="Expected indicator aliases SHA-256")
    arguments = parser.parse_args()

    expected_hashes = {
        key: value
        for key, value in {
            "indicatorMetadata": arguments.metadata_sha256,
            "indicatorManifest": arguments.manifest_sha256,
            "indicatorAliases": arguments.aliases_sha256,
        }.items()
        if value
    }
    try:
        result = project_els_snapshot(
            arguments.submodule_dir,
            submodule_commit=arguments.submodule_commit,
            commit_as_of=arguments.commit_as_of,
            retrieved_at=arguments.retrieved_at,
            expected_hashes=expected_hashes,
        )
    except ELSProjectionError as exc:
        parser.error(str(exc))

    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(result), encoding="utf-8", newline="\n")
    provenance = result["provenance"]
    print(
        f"{provenance['source']['id']}: {provenance['recordCount']} records "
        f"(reported {provenance['reportedTotal']}, "
        f"explained exclusions {provenance['explainedExclusionCount']}, "
        f"complete={provenance['coverageComplete']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
