"""Sanitize and inspect DOCX research derivatives for public release.

Office packages can retain tenant URLs, account aliases, sensitivity labels and
other provenance that is not visible in a rendered page. This module removes
those package-level locators and replaces external hyperlink labels with an
explicit redaction marker. It does not assert information-governance clearance;
the sanitized output still requires a hash-bound human release review.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

PUBLIC_LINK_TARGET = "https://example.invalid/redacted-external-reference"
PUBLIC_LINK_LABEL = "[external reference redacted for public release]"
PUBLIC_CREATOR = "OKF-ONS public evidence export"
PUBLIC_TITLE = "Sanitized public research derivative"

_PROHIBITED_PART_PREFIXES = (
    "customxml/",
    "_xmlsignatures/",
    "word/activex/",
    "word/embeddings/",
    "word/webextensions/",
    "word/comments",
    "word/people",
    "word/threadedcomments",
)
_PROHIBITED_PART_NAMES = {
    "word/vbaproject.bin",
    "word/vbadata.xml",
}
_PROHIBITED_XML = (
    re.compile(rb"(?i)sharepoint\.com"),
    re.compile(rb"(?i)outlook\.(?:office|office365)\.com"),
    re.compile(rb"(?i)(?:itemid|sourcedoc|entityrepresentationid)\s*="),
    re.compile(rb"(?i)/personal/"),
    re.compile(rb"(?i)msip_label_"),
    re.compile(rb"(?i)(?:file|mailto):"),
    re.compile(rb"(?i)(?:/Users/|[A-Z]:\\Users\\)"),
    re.compile(rb"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
)
_TRACKED_CHANGE_PATTERNS = (
    re.compile(rb"<w:ins(?:\s|>)"),
    re.compile(rb"<w:del(?:\s|>)"),
    re.compile(rb"<w:moveFrom(?:\s|>)"),
    re.compile(rb"<w:moveTo(?:\s|>)"),
)
_PNG_METADATA_CHUNKS = {b"eXIf", b"iTXt", b"tEXt", b"zTXt", b"tIME"}


class DocxReleaseError(ValueError):
    """Raised when a DOCX cannot meet the public-derivative contract."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_xml(value: bytes, label: str) -> ET.Element:
    try:
        return ET.fromstring(value)
    except ET.ParseError as error:
        raise DocxReleaseError(f"invalid XML in {label}") from error


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _relationship_owner(path: str) -> str | None:
    if path == "_rels/.rels":
        return None
    parts = list(PurePosixPath(path).parts)
    if "_rels" not in parts or not path.endswith(".rels"):
        return None
    index = parts.index("_rels")
    owner_name = parts[-1][: -len(".rels")]
    return str(PurePosixPath(*parts[:index], owner_name))


def _redact_hyperlink_labels(xml: bytes, relationship_ids: set[str]) -> tuple[bytes, int]:
    redacted = 0
    safe_run = (
        b"<w:r><w:t>"
        + PUBLIC_LINK_LABEL.encode("utf-8")
        + b"</w:t></w:r>"
    )
    for relationship_id in sorted(relationship_ids):
        identifier = re.escape(relationship_id.encode("utf-8"))
        pattern = re.compile(
            rb"(<w:hyperlink\b[^>]*\br:id=(?:\""
            + identifier
            + rb"\"|'"
            + identifier
            + rb"')[^>]*>).*?(</w:hyperlink>)",
            re.DOTALL,
        )
        xml, count = pattern.subn(
            lambda match: match.group(1) + safe_run + match.group(2),
            xml,
        )
        redacted += count
    return xml, redacted


def _sanitize_relationships(
    path: str,
    value: bytes,
) -> tuple[bytes, set[str], int, int]:
    ET.register_namespace("", RELATIONSHIP_NS)
    root = _parse_xml(value, path)
    external_ids: set[str] = set()
    external_count = 0
    custom_count = 0
    for relationship in list(root):
        relationship_type = str(relationship.get("Type", ""))
        if relationship_type.endswith("/custom-properties"):
            root.remove(relationship)
            custom_count += 1
            continue
        if relationship.get("TargetMode") == "External":
            external_count += 1
            relationship_id = relationship.get("Id")
            if relationship_id:
                external_ids.add(relationship_id)
            relationship.set("Target", PUBLIC_LINK_TARGET)
    return _xml_bytes(root), external_ids, external_count, custom_count


def _sanitize_content_types(value: bytes) -> bytes:
    ET.register_namespace("", CONTENT_TYPES_NS)
    root = _parse_xml(value, "[Content_Types].xml")
    for child in list(root):
        if child.get("PartName", "").casefold() == "/docprops/custom.xml":
            root.remove(child)
    return _xml_bytes(root)


def _set_or_add(root: ET.Element, tag: str, value: str) -> None:
    child = root.find(tag)
    if child is None:
        child = ET.SubElement(root, tag)
    child.text = value


def _sanitize_core_properties(value: bytes) -> bytes:
    ET.register_namespace("cp", CORE_NS)
    ET.register_namespace("dc", DC_NS)
    ET.register_namespace("dcterms", DCTERMS_NS)
    ET.register_namespace("xsi", XSI_NS)
    root = _parse_xml(value, "docProps/core.xml")
    _set_or_add(root, f"{{{DC_NS}}}title", PUBLIC_TITLE)
    _set_or_add(root, f"{{{DC_NS}}}creator", PUBLIC_CREATOR)
    _set_or_add(root, f"{{{CORE_NS}}}lastModifiedBy", PUBLIC_CREATOR)
    for tag in (
        f"{{{CORE_NS}}}category",
        f"{{{CORE_NS}}}contentStatus",
        f"{{{CORE_NS}}}keywords",
        f"{{{DC_NS}}}description",
        f"{{{DC_NS}}}subject",
    ):
        for child in list(root.findall(tag)):
            root.remove(child)
    return _xml_bytes(root)


def _sanitize_app_properties(value: bytes) -> bytes:
    ET.register_namespace("", APP_NS)
    root = _parse_xml(value, "docProps/app.xml")
    for tag, text in (
        ("Application", PUBLIC_CREATOR),
        ("Company", ""),
        ("Manager", ""),
        ("Template", ""),
        ("HyperlinkBase", ""),
    ):
        _set_or_add(root, f"{{{APP_NS}}}{tag}", text)
    for tag in ("HeadingPairs", "TitlesOfParts", "HLinks"):
        child = root.find(f"{{{APP_NS}}}{tag}")
        if child is not None:
            root.remove(child)
    return _xml_bytes(root)


def _inspect_png(path: str, value: bytes) -> dict[str, Any]:
    if not value.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DocxReleaseError(f"{path} has a .png extension but no PNG signature")
    position = 8
    chunks: list[str] = []
    while position + 12 <= len(value):
        length = int.from_bytes(value[position : position + 4], "big")
        chunk_type = value[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(value):
            raise DocxReleaseError(f"{path} has a truncated PNG chunk")
        chunks.append(chunk_type.decode("ascii", errors="replace"))
        if chunk_type in _PNG_METADATA_CHUNKS:
            raise DocxReleaseError(
                f"{path} contains prohibited PNG metadata chunk "
                f"{chunk_type.decode('ascii', errors='replace')}"
            )
        position = end
        if chunk_type == b"IEND":
            break
    if not chunks or chunks[-1] != "IEND":
        raise DocxReleaseError(f"{path} has no complete PNG end marker")
    return {
        "path": path,
        "format": "png",
        "sha256": _sha256(value),
        "metadata_present": False,
    }


def _inspect_media(path: str, value: bytes) -> dict[str, Any]:
    suffix = PurePosixPath(path).suffix.casefold()
    if suffix == ".png":
        return _inspect_png(path, value)
    if suffix in {".jpg", ".jpeg"}:
        prohibited = (b"Exif\x00\x00", b"<x:xmpmeta", b"Photoshop 3.0")
        if any(marker in value for marker in prohibited):
            raise DocxReleaseError(f"{path} contains EXIF, XMP or Photoshop metadata")
        if not value.startswith(b"\xff\xd8") or not value.endswith(b"\xff\xd9"):
            raise DocxReleaseError(f"{path} has an invalid JPEG signature")
        return {
            "path": path,
            "format": "jpeg",
            "sha256": _sha256(value),
            "metadata_present": False,
        }
    raise DocxReleaseError(f"unsupported embedded media type in {path}")


def _prohibited_parts(names: set[str]) -> list[str]:
    prohibited: list[str] = []
    for name in names:
        folded = name.casefold()
        if folded == "docprops/custom.xml":
            prohibited.append(name)
        elif folded in _PROHIBITED_PART_NAMES:
            prohibited.append(name)
        elif any(folded.startswith(prefix) for prefix in _PROHIBITED_PART_PREFIXES):
            prohibited.append(name)
    return sorted(prohibited)


def inspect_public_docx(path: str | Path) -> dict[str, Any]:
    """Validate one public DOCX derivative and return a bounded safety report."""

    document = Path(path)
    try:
        with zipfile.ZipFile(document) as package:
            names = set(package.namelist())
            prohibited = _prohibited_parts(names)
            if prohibited:
                raise DocxReleaseError(
                    f"DOCX contains prohibited package parts: {prohibited}"
                )
            external_relationships = 0
            for name in sorted(item for item in names if item.endswith(".rels")):
                root = _parse_xml(package.read(name), name)
                for relationship in root:
                    if relationship.get("TargetMode") != "External":
                        continue
                    external_relationships += 1
                    if relationship.get("Target") != PUBLIC_LINK_TARGET:
                        raise DocxReleaseError(
                            f"DOCX has an unredacted external relationship in {name}"
                        )
            xml_parts = {
                name: package.read(name)
                for name in names
                if name.casefold().endswith((".xml", ".rels"))
            }
            for name, value in xml_parts.items():
                if any(pattern.search(value) for pattern in _PROHIBITED_XML):
                    raise DocxReleaseError(
                        f"DOCX contains prohibited public-release metadata in {name}"
                    )
                if name.startswith("word/") and any(
                    pattern.search(value) for pattern in _TRACKED_CHANGE_PATTERNS
                ):
                    raise DocxReleaseError(f"DOCX contains tracked changes in {name}")
            core = _parse_xml(package.read("docProps/core.xml"), "docProps/core.xml")
            creator = core.findtext(f"{{{DC_NS}}}creator")
            modified_by = core.findtext(f"{{{CORE_NS}}}lastModifiedBy")
            if creator != PUBLIC_CREATOR or modified_by != PUBLIC_CREATOR:
                raise DocxReleaseError("DOCX core author properties are not sanitized")
            app = _parse_xml(package.read("docProps/app.xml"), "docProps/app.xml")
            for tag in ("Company", "Manager", "HyperlinkBase"):
                if (app.findtext(f"{{{APP_NS}}}{tag}") or "").strip():
                    raise DocxReleaseError(
                        f"DOCX app property {tag} is not sanitized"
                    )
            media = [
                _inspect_media(name, package.read(name))
                for name in sorted(names)
                if name.startswith("word/media/") and not name.endswith("/")
            ]
    except (KeyError, zipfile.BadZipFile) as error:
        raise DocxReleaseError(f"invalid public DOCX package: {document.name}") from error
    return {
        "path": document.name,
        "sha256": _sha256(document.read_bytes()),
        "public_metadata_safe": True,
        "external_relationships_redacted": external_relationships,
        "custom_properties_present": False,
        "tracked_changes_present": False,
        "embedded_media": media,
    }


def sanitize_public_docx(
    source: str | Path,
    destination: str | Path,
) -> dict[str, Any]:
    """Create a deterministic public derivative from a source DOCX package."""

    source_path = Path(source)
    destination_path = Path(destination)
    source_bytes = source_path.read_bytes()
    try:
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as package:
            members = {
                name: package.read(name)
                for name in package.namelist()
                if not name.endswith("/")
            }
    except zipfile.BadZipFile as error:
        raise DocxReleaseError(f"invalid source DOCX: {source_path.name}") from error

    source_names = set(members)
    prohibited = [
        name
        for name in _prohibited_parts(source_names)
        if name.casefold() != "docprops/custom.xml"
    ]
    if prohibited:
        raise DocxReleaseError(
            f"source DOCX has unsupported active or review parts: {prohibited}"
        )
    custom_properties_removed = int("docProps/custom.xml" in members)
    members.pop("docProps/custom.xml", None)

    relationships_by_owner: dict[str, set[str]] = {}
    external_relationships = 0
    custom_relationships = 0
    for name in sorted(item for item in members if item.endswith(".rels")):
        sanitized, external_ids, external_count, custom_count = _sanitize_relationships(
            name,
            members[name],
        )
        members[name] = sanitized
        owner = _relationship_owner(name)
        if owner is not None and external_ids:
            relationships_by_owner.setdefault(owner, set()).update(external_ids)
        external_relationships += external_count
        custom_relationships += custom_count

    hyperlink_labels = 0
    for owner, relationship_ids in sorted(relationships_by_owner.items()):
        if owner not in members:
            continue
        members[owner], count = _redact_hyperlink_labels(
            members[owner],
            relationship_ids,
        )
        hyperlink_labels += count

    members["[Content_Types].xml"] = _sanitize_content_types(
        members["[Content_Types].xml"]
    )
    members["docProps/core.xml"] = _sanitize_core_properties(
        members["docProps/core.xml"]
    )
    members["docProps/app.xml"] = _sanitize_app_properties(
        members["docProps/app.xml"]
    )
    for name, value in members.items():
        if name.startswith("word/media/"):
            _inspect_media(name, value)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as package:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            package.writestr(info, members[name])

    inspection = inspect_public_docx(destination_path)
    return {
        "schema": "okf-ons.docx-public-sanitization.v1",
        "source_name": source_path.name,
        "source_sha256": _sha256(source_bytes),
        "output_name": destination_path.name,
        "output_sha256": inspection["sha256"],
        "external_relationships_redacted": external_relationships,
        "hyperlink_labels_redacted": hyperlink_labels,
        "custom_properties_removed": custom_properties_removed,
        "custom_relationships_removed": custom_relationships,
        "inspection": inspection,
    }
