import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_uv_bootstrap_version_and_linux_archive_digest_are_locked() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert project["tool"]["uv"]["required-version"] == "==0.13.4"
    assert (
        "https://github.com/astral-sh/uv/releases/download/0.13.4/uv-x86_64-unknown-linux-gnu.tar.gz"
        in workflow
    )
    assert "2b428396f12572d4429cf210ca234dd599a33b3af0958a4d5ed569d63e3f344f" in workflow
    assert '"uv 0.13.4 "*)' in workflow
    assert 'Expected uv 0.13.4, got:' in workflow
    assert "uv 0.13.4" in readme
    assert "uv==0.12.2" not in workflow


def test_pages_acceptance_uses_the_uv_0134_compatible_explorer_main() -> None:
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "ref: cce6e68d95c2946bb425effbaab48fbf04281a09" in workflow
    assert "ref: 21a6b1be874eca4019770b15bd1c31ca41872f85" not in workflow
