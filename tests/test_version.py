from __future__ import annotations

import tomllib
from pathlib import Path

from okf_ons import __version__
from okf_ons.mcp_broker import SERVER_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_package_and_lockfile() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_project = next(
        package for package in lock["package"] if package["name"] == "okf-ons"
    )

    assert project["project"]["version"] == __version__
    assert locked_project["version"] == __version__
    assert SERVER_VERSION == __version__
