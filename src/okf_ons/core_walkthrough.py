"""Generate a source-bound question for the portable OKF 0.3 core Reader."""

# Template markup is kept as readable HTML/SVG text; long lines here are output
# markup rather than Python statements. All other Ruff rules remain enabled.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import __version__

CORE_ID = "https://chris-page-gov.github.io/okf-ons/okf-core-explorer.json"
EXPLORER = "https://chris-page-gov.github.io/okf-explorer/explore/?bundle="
ROUTES = (
    "concepts/catalogue.md",
    "concepts/snapshot.md",
    "concepts/governance.md",
    "concepts/standards.md",
)
QUESTION = (
    "Does OKF 0.3 conformance mean this ONS catalogue is complete, current, "
    "or statistically verified?"
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _svg(
    docs: list[dict[str, Any]], *, mobile: bool, descriptor_sha256: str
) -> bytes:
    width, height = (480, 1520) if mobile else (1440, 670)
    boxes = [
        ("Catalogue", "5,097 source-qualified", "metadata records", docs[0]),
        ("Snapshot", "Four bounded lanes", "no observation values", docs[1]),
        ("Governance", "No verified event", "integrity is not truth", docs[2]),
        ("Standards", "OKF 0.3 structure", "not accuracy or certification", docs[3]),
    ]
    if mobile:
        box_w, box_h, x, first_y, gap = 400, 220, 40, 120, 115
        coordinates = [(x, first_y + index * (box_h + gap)) for index in range(len(boxes))]
    else:
        box_w, box_h, first_x, y, gap = 300, 240, 45, 150, 45
        coordinates = [(first_x + index * (box_w + gap), y) for index in range(len(boxes))]
    title_lines = (
        [
            '<text class="title" x="40" y="48">Does conformance mean complete,</text>',
            '<text class="title" x="40" y="78">current or statistically verified?</text>',
        ]
        if mobile
        else [
            '<text class="title" x="45" y="55">'
            "Does conformance mean complete, current or verified?</text>"
        ]
    )
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
        "<title id=\"title\">A core-only answer about ONS metadata limits</title>",
        "<desc id=\"description\">Four exact OKF 0.3 Markdown sources explain the bounded catalogue, snapshot, governance and standards boundary. Dotted connectors show a reading sequence only; the portable core graph has zero edges.</desc>",
        "<defs><style>.bg{fill:#f6f8fb}.card{fill:#fff;stroke:#28577a;stroke-width:3}.warn{fill:#fff5d6;stroke:#8a5b00;stroke-width:3}.title{font:700 25px system-ui,sans-serif;fill:#14283b}.label{font:700 15px system-ui,sans-serif;fill:#334e68}.body{font:19px system-ui,sans-serif;fill:#14283b}.small{font:15px system-ui,sans-serif;fill:#334e68}.reading{fill:none;stroke:#526a7c;stroke-width:3;stroke-dasharray:9 9}</style></defs>",
        f'<rect class="bg" width="{width}" height="{height}" rx="20"/>',
        *title_lines,
    ]
    for index, ((heading, line_one, line_two, document), (x, y)) in enumerate(
        zip(boxes, coordinates, strict=True)
    ):
        css = "warn" if heading == "Standards" else "card"
        lines.extend([
            f'<rect class="{css}" x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="16"/>',
            f'<text class="label" x="{x + 22}" y="{y + 35}">{index + 1} · {html.escape(heading.upper())}</text>',
            f'<text class="title" x="{x + 22}" y="{y + 82}">{html.escape(line_one)}</text>',
            f'<text class="body" x="{x + 22}" y="{y + 119}">{html.escape(line_two)}</text>',
            f'<text class="small" x="{x + 22}" y="{y + 166}">{html.escape(document["route"])}</text>',
            f'<text class="small" x="{x + 22}" y="{y + 195}">SHA-256 {document["sha256"][:16]}…</text>',
        ])
        if index < len(boxes) - 1:
            if mobile:
                xmid = x + box_w / 2
                lines.append(f'<path class="reading" d="M{xmid} {y + box_h} V{y + box_h + gap - 20}"/>')
            else:
                lines.append(f'<path class="reading" d="M{x + box_w} {y + box_h / 2} H{x + box_w + gap - 10}"/>')
    if mobile:
        note_y = coordinates[-1][1] + box_h + 75
        lines.extend([
            f'<text class="body" x="40" y="{note_y}">Reading sequence only; 0 core relationship edges.</text>',
            f'<text class="small" x="40" y="{note_y + 35}">No dataset record, observation value or live claim is used.</text>',
        ])
    else:
        lines.extend([
            '<text class="body" x="45" y="465">Dotted connectors are a reading sequence, not semantic relationships.</text>',
            '<text class="small" x="45" y="505">The portable core projection contains 12 typed concepts and zero core edges.</text>',
            f'<text class="small" x="45" y="545">Core descriptor SHA-256 {descriptor_sha256[:24]}…</text>',
        ])
    lines.append("</svg>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def generate(core: Mapping[str, Any], descriptor_bytes: bytes, bundle: Path) -> dict[str, bytes]:
    """Return deterministic guide, diagrams and evidence for the exact core bytes."""
    if core.get("schema") != "okf-explorer-bundle.v0" or core.get("okf_version") != "0.3":
        raise ValueError("Core walkthrough requires the OKF 0.3 core projection")
    if core.get("bundle_id") != CORE_ID or core.get("version") != __version__:
        raise ValueError("Core Reader identity differs from the current ONS producer version")
    if core.get("snapshot") != "monday-2026-07-17-r2":
        raise ValueError("Core Reader snapshot differs from the frozen publication snapshot")
    if core.get("edges") != [] or len(core.get("nodes", {})) != 12:
        raise ValueError("Core-only walkthrough requires all 12 concepts and zero core edges")
    documents: list[dict[str, Any]] = []
    for route in ROUTES:
        node = core["nodes"].get(route)
        if not isinstance(node, Mapping) or node.get("source_path") != route:
            raise ValueError(f"Core concept source is missing or misrouted: {route}")
        path = bundle / route
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError(f"Core source is missing or escapes the candidate: {route}")
        raw = path.read_bytes()
        if _sha256(raw) != node.get("source_sha256") or len(raw) != node.get("source_bytes"):
            raise ValueError(f"Core source bytes differ from Reader projection: {route}")
        source_text = raw.decode("utf-8")
        source_claim = {
            "concepts/catalogue.md": "bounded metadata-only catalogue",
            "concepts/snapshot.md": "No governed `stale_after` date is currently defined",
            "concepts/governance.md": "not statistical truth",
            "concepts/standards.md": "independently of statistical accuracy, legal compliance or certification",
        }[route]
        if source_claim not in source_text:
            raise ValueError(f"Core answer claim is no longer present in its source concept: {route}")
        documents.append({
            "route": route,
            "title": node.get("title"),
            "sha256": _sha256(raw),
            "bytes": len(raw),
        })

    descriptor_sha = _sha256(descriptor_bytes)
    answer_paragraphs = [
        "No. The core describes a bounded metadata snapshot across four source lanes, "
        "not every ONS dataset, and contains no statistical observations.",
        "It defines no governed stale_after date; current-value and live-execution "
        "claims need provider revalidation.",
        "Governance says structural validation and frozen-input integrity do not "
        "establish statistical truth, while the standards concept separates OKF 0.3 "
        "structure from accuracy, legal compliance and certification.",
        "The conclusion about completeness, currentness and accuracy is an inference "
        "from these stated limits.",
    ]
    answer_markup = "\n".join(
        f"<p>{html.escape(paragraph).replace('stale_after', '<code>stale_after</code>')}</p>"
        for paragraph in answer_paragraphs
    )
    evidence = {
        "schema": "okf-ons-core-only-walkthrough.v1",
        "question": QUESTION,
        "answer_scope": "typed-core-markdown-only",
        "answer": " ".join(answer_paragraphs),
        "core_descriptor": {
            "path": "okf-core-explorer.json",
            "bundle_id": core["bundle_id"],
            "version": core["version"],
            "snapshot": core["snapshot"],
            "sha256": descriptor_sha,
        },
        "core_scope": {
            "typed_markdown_concepts": len(core["nodes"]),
            "directed_core_reference_pairs": len(core["edges"]),
            "metadata_extension_graph_used": False,
            "dataset_record_used": False,
            "observation_values_used": False,
        },
        "source_documents": documents,
        "claims": [
            {"claim": "This catalogue is a bounded, metadata-only projection.", "sources": [ROUTES[0], ROUTES[1]]},
            {"claim": "Current-value and live-execution claims require provider revalidation.", "sources": [ROUTES[1]]},
            {"claim": "Structural conformance is not statistical truth or certification.", "sources": [ROUTES[2], ROUTES[3]]},
        ],
        "negative_controls": [
            "The 5,097 figure is a metadata-record count for this bounded snapshot, not observation coverage.",
            "No governed stale_after date is defined; no freshness interval is inferred.",
            "OKF 0.3 structural conformance does not establish statistical accuracy, legal compliance or certification.",
            "The core projection has zero semantic edges; its reading sequence does not create graph relationships.",
            "No metadata-extension record, specific dataset, observation value or live query is used in this answer.",
        ],
    }
    evidence_bytes = _json_bytes(evidence)
    explorer_url = EXPLORER + quote(CORE_ID, safe="") + "#concepts/snapshot.md"
    source_list = "\n".join(
        f'<li><a href="{html.escape(item["route"], quote=True)}">{html.escape(item["title"])}</a> '
        f'(<code>{html.escape(item["route"])}</code>), SHA-256 <code>{item["sha256"]}</code>.</li>'
        for item in documents
    )
    desktop = _svg(documents, mobile=False, descriptor_sha256=descriptor_sha)
    mobile = _svg(documents, mobile=True, descriptor_sha256=descriptor_sha)
    evidence_hash = _sha256(evidence_bytes)
    diagram_hash = _sha256(desktop)
    mobile_hash = _sha256(mobile)
    html_page = f'''<!doctype html>
<html lang="en-GB"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><link rel="icon" href="data:,">
<meta name="description" content="A core-only, source-linked answer about the ONS OKF 0.3 snapshot boundary.">
<title>Does OKF 0.3 conformance mean complete or current?</title>
<style>
:root{{font:16px/1.55 system-ui,sans-serif;color:#14283b;background:#f6f8fb}}body{{margin:0}}main{{max-width:1050px;margin:auto;padding:1.5rem 1rem 3rem}}h1,h2{{line-height:1.2}}a{{color:#005a8b;text-underline-offset:.15em}}a:focus-visible{{outline:3px solid #ffbf47;outline-offset:3px}}.answer,.limits,.sources{{background:white;border:1px solid #b5c4d2;border-radius:.8rem;padding:1rem 1.2rem;margin:1rem 0}}.answer{{border-left:.35rem solid #216e4e}}.limits{{border-left:.35rem solid #8a5b00}}figure{{margin:1.5rem 0}}picture img{{display:block;width:100%;height:auto}}code{{overflow-wrap:anywhere;word-break:break-word}}li+li{{margin-top:.5rem}}.muted{{color:#334e68}}@media(max-width:600px){{main{{padding:.8rem}}}}</style>
</head><body><main>
<p><a href="index.html">ONS bundle homepage</a> · <a href="{html.escape(explorer_url, quote=True)}">Open this core bundle at the snapshot concept in OKF Explorer</a></p>
<h1>{html.escape(QUESTION)}</h1>
<section class="answer"><h2>Worked answer from the core sources</h2>
{answer_markup}</section>
<h2>Follow the core source trail</h2><figure><picture><source media="(max-width: 600px)" srcset="ons-core-walkthrough-mobile.svg"><img src="ons-core-walkthrough.svg" alt="A reading sequence through the catalogue, snapshot, governance and standards concepts. Dotted connectors are not semantic edges; the core graph has zero edges."></picture><figcaption class="muted">This is a guided reading sequence through four exact Markdown sources. It does not depict graph relationships; the core projection has zero edges.</figcaption></figure>
<section class="limits"><h2>Negative controls</h2><ul>
<li>The 5,097 figure is a metadata-record count for this bounded snapshot, not observation coverage or a claim about all ONS datasets.</li>
<li>No governed freshness interval is defined, so the guide does not invent one.</li>
<li>Structural conformance does not establish statistical accuracy, legal compliance or certification.</li>
<li>No metadata-extension entity, individual dataset, observation value or live query is used for this answer.</li>
</ul></section>
<section class="sources"><h2>Exact sources and identity</h2><p>Core descriptor <code>okf-core-explorer.json</code>, bundle ID <code>{html.escape(core['bundle_id'])}</code>, version <code>{html.escape(core['version'])}</code>, snapshot <code>{html.escape(core['snapshot'])}</code>, SHA-256 <code>{descriptor_sha}</code>. It contains 12 typed concepts and zero directed core reference pairs.</p>
<ul>{source_list}</ul><p>Desktop diagram SHA-256 <code>{diagram_hash}</code>; mobile diagram SHA-256 <code>{mobile_hash}</code>. <a href="ons-core-walkthrough-evidence.json">Machine-readable evidence</a>, SHA-256 <code>{evidence_hash}</code>.</p>
<p>This question uses only the portable OKF core sources. It does not make a claim about a particular dataset or use the 5,097-record metadata extension graph.</p></section>
</main></body></html>
'''.encode()
    return {
        "core-walkthrough.html": html_page,
        "ons-core-walkthrough.svg": desktop,
        "ons-core-walkthrough-mobile.svg": mobile,
        "ons-core-walkthrough-evidence.json": evidence_bytes,
    }
