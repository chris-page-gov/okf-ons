from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
INDEX = PAGES / "index.html"
APP = PAGES / "app.js"
STYLES = PAGES / "styles.css"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.labels_for: set[str] = set()
        self.references: list[tuple[str, str]] = []
        self.tabs: set[str] = set()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        attrs = {key: value or "" for key, value in attributes}
        self.tags.append((tag, attrs))
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "label" and attrs.get("for"):
            self.labels_for.add(attrs["for"])
        if attrs.get("role") == "tab" and attrs.get("data-tab"):
            self.tabs.add(attrs["data-tab"])
        for attribute in ("href", "src"):
            if attrs.get(attribute):
                self.references.append((attribute, attrs[attribute]))


def parse(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def relative_path(reference: str) -> Path | None:
    split = urlsplit(reference)
    if split.scheme or split.netloc or reference.startswith("#"):
        return None
    clean = split.path.removeprefix("./")
    return PAGES / clean


def luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(left: str, right: str) -> float:
    light, dark = sorted((luminance(left), luminance(right)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_main_page_has_progressive_accessible_discovery_structure() -> None:
    html = INDEX.read_text(encoding="utf-8")
    parser = parse(INDEX)

    assert 'lang="en-GB"' in html
    assert ("main", {"id": "main-content"}) in [
        (tag, {key: value for key, value in attrs.items() if key == "id"})
        for tag, attrs in parser.tags
        if tag == "main"
    ]
    assert '<a class="skip-link" href="#main-content">' in html
    assert "<noscript>" in html
    assert any(tag == "form" and attrs.get("role") == "search" for tag, attrs in parser.tags)
    assert {
        "search-input",
        "source-filter",
        "type-filter",
        "topic-filter",
        "frequency-filter",
        "evidence-filter",
        "sort-select",
    }.issubset(parser.labels_for)
    assert parser.tabs == {
        "overview",
        "compare",
        "quality",
        "production",
        "versions",
        "dimensions",
        "geography",
        "mcp",
        "standards",
    }
    assert 'aria-live="polite"' in html
    assert "Open in OKF Explorer" in html
    assert "searches all 4,989 frozen records" in html
    assert "No API key is requested or retained." in html


def test_static_page_assets_are_project_relative_and_present() -> None:
    for page in PAGES.glob("*.html"):
        parser = parse(page)
        for attribute, reference in parser.references:
            if reference.startswith(("mailto:", "tel:", "data:")):
                continue
            local = relative_path(reference)
            if local is None:
                continue
            if local.parts[-2:-1] == ("data",) or "data/" in reference:
                # Generated bundle assets are produced by the build workflow.
                continue
            if local.name == "okf-explorer.json":
                continue
            assert local.exists(), f"{page.name} {attribute} target missing: {reference}"


def test_javascript_uses_canonical_generated_entrypoints_and_safe_dom() -> None:
    script = APP.read_text(encoding="utf-8")

    for path in (
        "data/demo/contrast-records.json",
        "data/coverage/ledger.json",
        "data/standards/evaluation.json",
        "data/evaluation/report.json",
        "data/ons/mcp-bindings.json",
        "data/ons/spatial-index.json",
    ):
        assert path in script
    assert "innerHTML" not in script
    assert "outerHTML" not in script
    assert "document.write" not in script
    assert "eval(" not in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "indexedDB" not in script
    assert "safeUrl(" not in script
    assert "geography" in script.casefold()
    assert "Text alternative to the extent diagram" in script
    assert "function portalBbox(extent)" in script
    assert 'pathNumber(state.evaluation, ["metrics", "recall_at_k", "5"])' in script
    assert '"MCP binding planned"' in script
    assert "selection.inspection_tool || selection.tool || null" in script
    assert "selection.query_tool || (structurallyComplete ? selection.tool : null)" in script
    assert '"inspect-sdmx-structure-and-configure"' in script
    assert '"inspect-and-configure"' in script
    assert "portalBbox(record.raw.portal_extent)" in script
    assert "record.recordId" in script
    assert "item.nativeId" in script
    assert "statistical accuracy" in script
    assert "GitHub Pages does not call ONS" in script
    assert '"Statistical producer"' in script
    assert "Not evidenced in this metadata record" in script
    assert '"Catalogue publisher / metadata service"' in script
    assert '["Producer"' not in script
    assert 'typeof child === "string" && child.trim() !== ""' in script


def test_public_files_contain_no_credential_values() -> None:
    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PAGES.rglob("*")) if path.is_file()
    )
    secret_patterns = (
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        r"\b[A-Fa-f0-9]{32}\b",
        r"(?:api[_-]?key|password|client[_-]?secret)\s*[:=]\s*['\"][^'\"]+",
    )
    for pattern in secret_patterns:
        assert not re.search(pattern, public_text, flags=re.IGNORECASE)


def test_core_palette_meets_normal_text_contrast() -> None:
    # These are the actual principal text/background pairs from styles.css.
    pairs = (
        ("#1f1b24", "#ffffff"),
        ("#5e5764", "#ffffff"),
        ("#3d236b", "#ffffff"),
        ("#2a174d", "#ffffff"),
        ("#006b78", "#ffffff"),
        ("#ffffff", "#3d236b"),
        ("#ffffff", "#2a174d"),
        ("#176b3a", "#e4f3e9"),
        ("#9c1c2b", "#fae8eb"),
    )
    assert all(contrast(foreground, background) >= 4.5 for foreground, background in pairs)


def test_supporting_pages_and_sendable_documents_state_claim_boundaries() -> None:
    demo_html = (PAGES / "demo-guide.html").read_text(encoding="utf-8")
    accessibility_html = (PAGES / "accessibility.html").read_text(encoding="utf-8")
    demo_markdown = (ROOT / "docs" / "demo-guide.md").read_text(encoding="utf-8")
    accessibility_markdown = (ROOT / "accessibility.md").read_text(encoding="utf-8")

    assert "seven-minute route" in demo_html.casefold()
    assert "metadata completeness" in demo_markdown.casefold()
    assert "all ons" in demo_markdown.casefold()
    assert "wcag 2.2" in accessibility_html.casefold()
    accessibility_words = " ".join(accessibility_html.casefold().split())
    assert "has not yet received a formal independent accessibility audit" in (accessibility_words)
    assert "does not request an api key" in accessibility_markdown.casefold()
    assert "text table" in accessibility_markdown.casefold()


def test_pages_workflow_validates_prs_and_deploys_only_main() -> None:
    workflow = ROOT / ".github" / "workflows" / "pages.yml"
    assert workflow.exists()
    text_value = workflow.read_text(encoding="utf-8")

    assert "      - main" in text_value
    assert "codex/monday-ons-okf-demonstrator" not in text_value
    assert "workflow_dispatch:" in text_value
    assert "pull_request:" in text_value
    assert text_value.count("if: github.ref == 'refs/heads/main'") == 3
    assert "contents: read" in text_value
    assert "pages: write" in text_value
    assert "id-token: write" in text_value
    assert "actions/checkout@v7" in text_value
    assert "actions/setup-python@v6" in text_value
    assert "actions/configure-pages@v6" in text_value
    assert "actions/upload-pages-artifact@v5" in text_value
    assert "actions/deploy-pages@v5" in text_value
    assert "source/demo-snapshot" in text_value
    assert "python scripts/build_bundle.py" in text_value
    assert "secrets." not in text_value
