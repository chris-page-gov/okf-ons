from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.docx_release import (  # noqa: E402
    PUBLIC_LINK_LABEL,
    PUBLIC_LINK_TARGET,
    DocxReleaseError,
    inspect_public_docx,
    sanitize_public_docx,
)


def _write_unsafe_docx(path: Path) -> None:
    members = {
        "[Content_Types].xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Override PartName="/docProps/core.xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/xml"/>
  <Override PartName="/docProps/custom.xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/xml"/>
</Types>""",
        "_rels/.rels": b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
    Target="docProps/custom.xml"/>
</Relationships>""",
        "docProps/core.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:creator>private-author@example.test</dc:creator>
  <cp:lastModifiedBy>Private Author</cp:lastModifiedBy>
</cp:coreProperties>""",
        "docProps/app.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Microsoft Office</Application>
  <Company>Private tenant</Company>
  <HLinks xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
    <vt:vector size="1" baseType="variant"><vt:variant><vt:lpwstr>https://tenant.sharepoint.com/personal/private</vt:lpwstr></vt:variant></vt:vector>
  </HLinks>
</Properties>""",
        "docProps/custom.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties">
  <property name="MSIP_Label_private"/>
</Properties>""",
        "word/document.xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body><w:p><w:hyperlink r:id="rId9">
    <w:r><w:t>Private enterprise citation</w:t></w:r>
  </w:hyperlink></w:p>
  <w:p><w:r><w:instrText>PAGE</w:instrText></w:r></w:p></w:body>
</w:document>""",
        "word/_rels/document.xml.rels": b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    Target="https://tenant.sharepoint.com/personal/private?itemId=private" TargetMode="External"/>
</Relationships>""",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, value in members.items():
            package.writestr(name, value)


def test_sanitizer_removes_hidden_office_metadata_and_link_labels(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unsafe.docx"
    first = tmp_path / "public-first.docx"
    second = tmp_path / "public-second.docx"
    _write_unsafe_docx(source)

    with pytest.raises(DocxReleaseError):
        inspect_public_docx(source)

    first_report = sanitize_public_docx(source, first)
    sanitize_public_docx(source, second)

    assert first.read_bytes() == second.read_bytes()
    assert first_report["custom_properties_removed"] == 1
    assert first_report["custom_relationships_removed"] == 1
    assert first_report["external_relationships_redacted"] == 1
    assert first_report["hyperlink_labels_redacted"] == 1
    assert first_report["inspection"]["public_metadata_safe"] is True
    with zipfile.ZipFile(first) as package:
        names = set(package.namelist())
        document = package.read("word/document.xml")
        relationships = package.read("word/_rels/document.xml.rels")
        assert "docProps/custom.xml" not in names
        assert PUBLIC_LINK_LABEL.encode() in document
        assert b"Private enterprise citation" not in document
        assert PUBLIC_LINK_TARGET.encode() in relationships
        assert b"sharepoint.com" not in b"".join(package.read(name) for name in names)
