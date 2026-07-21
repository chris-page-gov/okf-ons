"""Normalize ONS metadata into stable, provenance-bearing discovery records."""

from __future__ import annotations

import hashlib
import html
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlparse

STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "data",
    "dataset",
    "for",
    "from",
    "in",
    "of",
    "on",
    "statistics",
    "the",
    "to",
    "uk",
    "united",
    "kingdom",
    "with",
}

ONS_API_ROOT = "https://api.beta.ons.gov.uk/v1"
NOMIS_ROOT = "https://www.nomisweb.co.uk/api/v01"
OGP_ROOT = "https://geoportal.statistics.gov.uk"
OKF_ONS_REPOSITORY = "https://github.com/chris-page-gov/okf-ons"
BUNDLE_PUBLISHER = {
    "id": OKF_ONS_REPOSITORY,
    "name": "OKF ONS project",
    "url": OKF_ONS_REPOSITORY,
}
_NATIVE_TABLE_CODE_RE = re.compile(r"^[A-Z]{2}\d{3}$", re.IGNORECASE)
_TITLE_TABLE_CODE_RE = re.compile(
    r"^\s*([A-Z]{2}\d{3}[A-Z]*)\s*(?:[-:–—]|$)",
    re.IGNORECASE,
)
_HTTP_URL_RE = re.compile(r"https?://[^\s<>\"'\[\]()]+", re.IGNORECASE)
_NOMIS_QUALITY_CONTEXT_RE = re.compile(
    r"(?:"
    r"\bquality(?:\s+(?:information|consideration|work|report|guidance))?\b|"
    r"\buncertaint(?:y|ies)\b|"
    r"\bstatistical\s+disclosure\s+control\b|"
    r"\bprotect(?:ing|ion)?\b.{0,40}\bpersonal\s+(?:data|information)\b|"
    r"\bprotect\b.{0,40}\bagainst\s+disclosure\b"
    r")",
    re.IGNORECASE,
)
_NOMIS_POPULATION_CONTEXT_RE = re.compile(
    r"\b(?:"
    r"people|persons?|residents?|population|households?|famil(?:y|ies)|"
    r"dwellings?|children|child|adults?|students?|schoolchildren|parents?|"
    r"males?|females?|establishments?|armed\s+forces"
    r")\b",
    re.IGNORECASE,
)
_OGP_TITLE_YEAR_RE = re.compile(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)")
_OGP_AREA_KEYWORD_CROSSWALK = {
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "great britain": "Great Britain",
    "gb": "Great Britain",
    "england": "England",
    "en": "England",
    "england and wales": "England and Wales",
    "ew": "England and Wales",
    "wales": "Wales",
    "wa": "Wales",
    "scotland": "Scotland",
    "sc": "Scotland",
    "northern ireland": "Northern Ireland",
    "ni": "Northern Ireland",
}
_OGP_FREQUENCY_RULES = (
    (re.compile(r"\bquarterly\b", re.IGNORECASE), "quarterly"),
    (re.compile(r"\bevery 6 weeks\b", re.IGNORECASE), "every 6 weeks"),
    (re.compile(r"\bissued every 12 weeks\b", re.IGNORECASE), "every 12 weeks"),
    (re.compile(r"\bannually\b", re.IGNORECASE), "annually"),
)
_OGP_GENERIC_CATEGORIES = {
    "/categories/latest",
    "/categories/ons geography open data",
}
_OGP_GUIDE_TITLE_RE = re.compile(
    r"\b(?:user guide|guidance and information|statistical guidance)\b",
    re.IGNORECASE,
)
_OGP_METHODOLOGY_WORD_RE = re.compile(
    r"\bmethodolog(?:y|ies|ical)\b",
    re.IGNORECASE,
)
_OGP_SUBSTANTIVE_METHOD_RE = re.compile(
    r"(?:"
    r"\bmethodology used\b|"
    r"\bmethodology has been applied\b|"
    r"\bcreated using an automated approach\b|"
    r"\bgenerated using\b|"
    r"\bcalculated using\b|"
    r"\bassigned using a ['‘’]?point-in-polygon['‘’]? methodology\b"
    r")",
    re.IGNORECASE,
)
_OGP_QUALITY_NOTE_RE = re.compile(
    r"\b(?:"
    r"data quality and limitations|"
    r"quality assurance checks?|"
    r"known limitations?/caveats?|"
    r"known caveats and limitations"
    r")\b",
    re.IGNORECASE,
)
_OGP_REFERENCE_DATE_RE = re.compile(
    r"\bas at\s+"
    r"(?P<date>"
    r"(?:(?:\d{1,2}(?:st|nd|rd|th)?\s+)?"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|"
    r"Oct|Nov|Dec)\s+)?"
    r"(?P<year>(?:18|19|20)\d{2})"
    r")\b",
    re.IGNORECASE,
)
_OGP_VERSION_LABEL_RE = re.compile(r"\((V\d+(?:\.\d+)?)\)", re.IGNORECASE)
_OGP_REVISION_HISTORY_RE = re.compile(
    r"(?:"
    r"\b(?:this|the)\s+"
    r"(?:file|dataset|product|guide|boundary set|documents? folder)\s+"
    r"(?:(?:has|have) been\s+|(?:was|were|is|are)\s+)?"
    r"(?:updated|corrected|amended|revised)\b|"
    r"\b(?:file|dataset|product)\s+(?:has been\s+)?"
    r"(?:updated|corrected|amended|revised)\b|"
    r"\b(?:V(?:ersion)?\s*\d+(?:\.\d+)?)\s+"
    r"(?:corrects?|updates?|amends?|revises?)\b|"
    r"\b(?:note|n\.?b\.?)\s*[:.-]?\s*"
    r"(?:updated|corrected|amended|revised)\b|"
    r"\[(?:updated|corrected|amended|revised)\b|"
    r"\b(?:amended|updated|corrected|revised)\s+"
    r"\d{1,2}/\d{1,2}/\d{2,4}\b"
    r")",
    re.IGNORECASE,
)
_ELS_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_ELS_METHOD_LINK_CONTEXT_RE = re.compile(
    r"(?:"
    r"\bmethodolog(?:y|ies|ical)\b|"
    r"\bmethods?\b|"
    r"\buser[ -]?guide\b|"
    r"\bfrascati[ -]?manual\b|"
    r"\btechnical[ -]?report\b|"
    r"\bmodel-params\b|"
    r"\bnotes-and-definitions\b|"
    r"\bindicator[ -]?definitions\b|"
    r"\bsupporting[ -]?information\b"
    r")",
    re.IGNORECASE,
)
_ELS_QUALITY_LINK_CONTEXT_RE = re.compile(
    r"(?:\bquality\b|\bqmi\b|\buncertaint(?:y|ies)\b|\brobustness\b)",
    re.IGNORECASE,
)
_ELS_COUNTRY_CODE_CROSSWALK = {
    "E": "England",
    "N": "Northern Ireland",
    "S": "Scotland",
    "W": "Wales",
}
_SECRET_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
    "uid",
    "x-api-key",
}


def plain_text(value: Any, limit: int = 10_000) -> str:
    """Return bounded plain text from inconsistent upstream metadata."""

    text = html.unescape(str(value or ""))
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("\\r\\n", " ").replace("\\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def slugify(value: Any, fallback: str = "record") -> str:
    text = plain_text(value, 500).casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        text = fallback
    return text[:180].rstrip("-")


def tokenize(*values: Any) -> list[str]:
    text = " ".join(plain_text(value, 50_000).casefold() for value in values)
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9'-]+", text)
        if len(token) >= 2 and token not in STOP_WORDS
    ]


def content_sha256(value: Any) -> str:
    import json

    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _link(value: Any, *keys: str) -> str:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    if isinstance(current, dict):
        current = current.get("href") or current.get("url") or current.get("id")
    return str(current or "")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = value
    elif value is None or value == "":
        rows = []
    else:
        rows = [value]
    return sorted({plain_text(row, 300) for row in rows if plain_text(row, 300)})


def _public_url(value: Any, limit: int = 2_000) -> str:
    """Return a bounded public URL without embedded credentials or secret keys."""

    url = plain_text(value, limit)
    parsed = urlparse(url)
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query)}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or query_keys.intersection(_SECRET_QUERY_KEYS)
    ):
        return ""
    return url


def _contacts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, str]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        contact: dict[str, str] = {
            key: plain_text(row.get(key), 300)
            for key in ("name", "email", "telephone")
            if row.get(key)
        }
        if public_url := _public_url(row.get("url")):
            contact["url"] = public_url
        if contact:
            output.append(contact)
    return output


def _version_identity(link: str) -> tuple[str, str, str]:
    match = re.search(r"/datasets/([^/]+)/editions/([^/]+)/versions/([^/?#]+)", link)
    return match.groups() if match else ("", "", "")


def _ons_version_dimensions(value: Any) -> list[dict[str, Any]]:
    """Return a bounded projection of source-declared ONS version dimensions."""

    if not isinstance(value, list):
        return []
    dimensions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in value[:100]:
        if not isinstance(item, Mapping):
            continue
        dimension: dict[str, Any] = {}
        for key, limit in (
            ("id", 300),
            ("name", 300),
            ("label", 500),
            ("description", 5_000),
            ("variable", 300),
        ):
            if text := plain_text(item.get(key), limit):
                dimension[key] = text
        quality_text = plain_text(
            item.get("qualityStatementText", item.get("quality_statement_text")),
            5_000,
        )
        if quality_text:
            dimension["quality_statement_text"] = quality_text
        if url := _public_url(item.get("href")):
            dimension["href"] = url
        quality_url = _public_url(
            item.get("qualityStatementUrl", item.get("quality_statement_url"))
        )
        if quality_url:
            dimension["quality_statement_url"] = quality_url
        is_area_type = item.get("isAreaType", item.get("is_area_type"))
        if isinstance(is_area_type, bool):
            dimension["is_area_type"] = is_area_type
        option_count = item.get("number_of_options")
        if (
            isinstance(option_count, int)
            and not isinstance(option_count, bool)
            and 0 <= option_count <= 100_000_000
        ):
            dimension["number_of_options"] = option_count
        identity = (
            str(dimension.get("id") or ""),
            str(dimension.get("name") or ""),
            str(dimension.get("label") or ""),
        )
        if not any(identity) or identity in seen:
            continue
        seen.add(identity)
        dimensions.append(dimension)
    return dimensions


def _ons_geography_dimensions(
    dimensions: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Select only explicitly declared ONS area dimensions."""

    return [
        dict(dimension)
        for dimension in dimensions
        if dimension.get("is_area_type") is True
        or plain_text(dimension.get("name"), 300).casefold() == "geography"
        or plain_text(dimension.get("label"), 500).casefold() == "geography"
    ]


def _nomis_annotation_map(value: Any) -> dict[str, str]:
    """Return text-bearing projected Nomis annotations by their native title."""

    if not isinstance(value, list):
        return {}
    annotations: dict[str, str] = {}
    for item in value:
        if not isinstance(item, Mapping):
            continue
        title = plain_text(item.get("title"), 300)
        text = plain_text(item.get("text"))
        if title and text:
            annotations.setdefault(title, text)
    return annotations


def _nomis_geography_levels(annotation_map: Mapping[str, str]) -> list[str]:
    """Normalise only the source-declared Nomis geography-level annotation."""

    value = annotation_map.get("contenttype/geoglevel", "")
    return sorted(
        {
            level
            for item in re.split(r"[,;|]", value)
            if (level := plain_text(item, 300))
        },
        key=str.casefold,
    )


def _nomis_population_universe(annotation_map: Mapping[str, str]) -> str:
    """Return a source-declared universe, rejecting codes and gap sentinels.

    Most ``SubDescription`` values are natural-language statistical universes,
    but the frozen Nomis source also uses the field for legacy mnemonics such
    as ``vat`` and the sentinel ``previously unavailable``. Requiring an
    explicit population-unit noun retains only values that evidence a universe.
    """

    value = plain_text(annotation_map.get("SubDescription"))
    return value if _NOMIS_POPULATION_CONTEXT_RE.search(value) else ""


def _nomis_quality_documentation_links(
    annotation_map: Mapping[str, str],
) -> list[str]:
    """Extract public quality-documentation URLs from Nomis metadata notes.

    Nomis ``MetadataTextN`` annotations also contain general explanatory and
    classification links. A URL is therefore retained only when the matching
    ``MetadataTitleN``, the note text, or the URL itself contains an explicit
    quality, uncertainty, privacy-protection, or disclosure-control signal.
    """

    links: set[str] = set()
    for title, note in annotation_map.items():
        match = re.fullmatch(r"MetadataText(\d*)", title)
        if not match:
            continue
        companion_title = annotation_map.get(f"MetadataTitle{match.group(1)}", "")
        for url_match in _HTTP_URL_RE.finditer(note):
            url = _public_url(url_match.group().rstrip(".,;:!?"))
            if not url:
                continue
            context_start = max(0, url_match.start() - 180)
            context_end = min(len(note), url_match.end() + 180)
            quality_context = " ".join(
                (companion_title, note[context_start:context_end], url)
            )
            if _NOMIS_QUALITY_CONTEXT_RE.search(quality_context):
                links.add(url)
    return sorted(links)


def _nomis_quality_documentation_notes(
    annotation_map: Mapping[str, str],
) -> list[str]:
    """Return explicitly labelled or self-describing Nomis quality notes."""

    notes: set[str] = set()
    for title, note in annotation_map.items():
        match = re.fullmatch(r"MetadataText(\d*)", title)
        if not match:
            continue
        bounded_note = plain_text(note, 5_000)
        if len(bounded_note) < 20:
            continue
        companion_title = annotation_map.get(f"MetadataTitle{match.group(1)}", "")
        if _NOMIS_QUALITY_CONTEXT_RE.search(
            " ".join((companion_title, bounded_note))
        ):
            notes.add(bounded_note)
    return sorted(notes)


def _ogp_area_served(keywords: Any) -> list[str]:
    """Crosswalk exact source keywords to a small controlled country list."""

    return sorted(
        {
            area
            for keyword in _string_list(keywords)
            if (area := _OGP_AREA_KEYWORD_CROSSWALK.get(keyword.casefold()))
        },
        key=str.casefold,
    )


def _ogp_geography_vintage(title: Any) -> int | str:
    """Return a title year only when the source title has one distinct year."""

    years = {int(value) for value in _OGP_TITLE_YEAR_RE.findall(plain_text(title, 1_000))}
    return years.pop() if len(years) == 1 else ""


def _ogp_frequency(description: Any) -> str:
    """Return cadence only for an explicit, bounded source-description phrase."""

    text = plain_text(description)
    for pattern, frequency in _OGP_FREQUENCY_RULES:
        if pattern.search(text):
            return frequency
    return ""


def _ogp_informative_categories(value: Any) -> list[str]:
    """Retain source categories except the two catalogue-wide containers."""

    return [
        category
        for category in _string_list(value)
        if category.rstrip("/").casefold() not in _OGP_GENERIC_CATEGORIES
    ]


def _ogp_category_subtopics(categories: Iterable[str]) -> list[str]:
    """Render retained source category paths as readable, lossless subtopics."""

    prefix = "/Categories/"
    return sorted(
        {
            category[len(prefix) :] if category.startswith(prefix) else category
            for category in categories
        },
        key=str.casefold,
    )


def _ogp_exact_self_url(projected: Mapping[str, Any], native_id: str) -> str:
    """Return one public OGP self link only when it identifies this record."""

    links = projected.get("links")
    related = links.get("related") if isinstance(links, Mapping) else None
    if not isinstance(related, list):
        return ""
    candidates: set[str] = set()
    for link in related:
        if not isinstance(link, Mapping) or plain_text(link.get("rel"), 50).casefold() != "self":
            continue
        url = _public_url(link.get("href"))
        if not url:
            continue
        terminal_id = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        if terminal_id == native_id:
            candidates.add(url)
    return next(iter(candidates)) if len(candidates) == 1 else ""


def _ogp_labelled_methodology_links(description: Any) -> list[str]:
    """Extract URLs immediately preceded by an explicit methodology label."""

    text = plain_text(description)
    links: set[str] = set()
    for match in _HTTP_URL_RE.finditer(text):
        context = text[max(0, match.start() - 180) : match.start()]
        if not _OGP_METHODOLOGY_WORD_RE.search(context):
            continue
        url = _public_url(match.group().rstrip(".,;:!?"))
        if url:
            links.add(url)
    return sorted(links)


def _ogp_methodology_links(
    title: Any,
    description: Any,
    self_url: str,
) -> list[str]:
    """Return evidence URLs only for one of three conservative method signals."""

    title_text = plain_text(title, 1_000)
    description_text = plain_text(description)
    labelled_links = _ogp_labelled_methodology_links(description_text)
    guide_with_method = bool(
        _OGP_GUIDE_TITLE_RE.search(title_text)
        and _OGP_METHODOLOGY_WORD_RE.search(description_text)
    )
    substantive_method = bool(_OGP_SUBSTANTIVE_METHOD_RE.search(description_text))
    if not (guide_with_method or substantive_method or labelled_links):
        return []
    links = set(labelled_links)
    if self_url:
        links.add(self_url)
    return sorted(links)


def _ogp_evidence_excerpt(
    description: Any,
    pattern: re.Pattern[str],
) -> str:
    """Return one bounded source sentence around a conservative evidence match."""

    text = plain_text(description)
    match = pattern.search(text)
    if match is None:
        return ""
    sentence_start = text.rfind(". ", 0, match.start()) + 2
    sentence_end = text.find(". ", match.end())
    if sentence_end == -1:
        sentence_end = len(text)
    else:
        sentence_end += 1
    if sentence_end - sentence_start > 500:
        sentence_start = max(0, match.start() - 180)
        sentence_end = min(len(text), match.end() + 300)
    return plain_text(text[sentence_start:sentence_end], 500)


def _ogp_quality_notes(description: Any) -> list[str]:
    note = _ogp_evidence_excerpt(description, _OGP_QUALITY_NOTE_RE)
    return [note] if note else []


def _ogp_geography_reference_date(title: Any, description: Any) -> str:
    """Extract one early resource date that agrees with the sole title year."""

    text = plain_text(description)
    matches = list(_OGP_REFERENCE_DATE_RE.finditer(text))
    title_year = _ogp_geography_vintage(title)
    if (
        len(matches) != 1
        or not isinstance(title_year, int)
        or matches[0].start() > 300
        or int(matches[0].group("year")) != title_year
    ):
        return ""
    return plain_text(matches[0].group("date"), 100)


def _ogp_source_version_label(title: Any) -> str:
    """Preserve an exact parenthesised OGP version identity from the title."""

    match = _OGP_VERSION_LABEL_RE.search(plain_text(title, 1_000))
    return match.group(1).upper() if match else ""


def _ogp_revision_history_notes(description: Any) -> list[str]:
    """Preserve explicit update history without inferring publication status."""

    note = _ogp_evidence_excerpt(description, _OGP_REVISION_HISTORY_RE)
    return [note] if note else []


def _merge_field_derivation(
    existing: Any,
    additions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge per-field derivations without discarding existing evidence."""

    merged = dict(existing) if isinstance(existing, Mapping) else {}
    existing_fields = merged.get("fields")
    fields = {
        str(field): dict(details)
        for field, details in existing_fields.items()
        if isinstance(details, Mapping)
    } if isinstance(existing_fields, Mapping) else {}
    for field, details in additions.items():
        prior = fields.get(field, {})
        fields[field] = {**dict(details), **prior}

    modes = {
        plain_text(mode, 300)
        for mode in merged.get("modes", [])
        if plain_text(mode, 300)
    } if isinstance(merged.get("modes"), list) else set()
    modes.update(
        plain_text(details.get("mode"), 300)
        for details in fields.values()
        if plain_text(details.get("mode"), 300)
    )
    merged.update(
        {
            "schema": "okf-ons-field-derivation.v1",
            "modes": sorted(modes),
            "fields": dict(sorted(fields.items())),
        }
    )
    return merged


def _els_documentation_links(caveats: Iterable[str]) -> tuple[list[str], list[str]]:
    """Extract only explicitly labelled method and quality links from ELS caveats."""

    methodology_links: set[str] = set()
    quality_links: set[str] = set()
    for caveat in caveats:
        for match in _ELS_MARKDOWN_LINK_RE.finditer(caveat):
            label = plain_text(match.group(1), 1_000)
            url = match.group(2).rstrip(".,;:!?")
            parsed = urlparse(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                continue
            context = f"{label} {url}"
            if _ELS_METHOD_LINK_CONTEXT_RE.search(context):
                methodology_links.add(url)
            if _ELS_QUALITY_LINK_CONTEXT_RE.search(context):
                quality_links.add(url)
    return sorted(methodology_links), sorted(quality_links)


def _els_area_served(geography: Mapping[str, Any]) -> list[str]:
    """Crosswalk projected ELS country codes without inferring wider coverage."""

    countries = geography.get("countries")
    if not isinstance(countries, list):
        return []
    return sorted(
        {
            area
            for code in countries
            if (area := _ELS_COUNTRY_CODE_CROSSWALK.get(plain_text(code, 10).upper()))
        },
        key=str.casefold,
    )


def _public_host(value: Any) -> str:
    """Return the host of an explicit public HTTP(S) URL without credentials."""

    parsed = urlparse(plain_text(value, 2_000))
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return ""
    return parsed.hostname.casefold()


def _quality_evidence(record: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "identity": bool(record.get("native_id") and record.get("source_surface")),
        "description": bool(record.get("notes")),
        "publisher": bool(record.get("publisher_title")),
        "licence": bool(record.get("license_id"))
        and record.get("license_id") != "not-evaluated",
        "contact": bool(record.get("contacts")),
        "release_or_modified": bool(
            record.get("metadata_modified") or record.get("first_released")
        ),
        "frequency": bool(record.get("frequency")),
        "population": bool(record.get("population_type")),
        "geography": bool(
            record.get("geography")
            or record.get("portal_extent")
            or record.get("geography_vintage")
            or record.get("area_served")
        ),
        "time_coverage": bool(record.get("time_coverage")),
        "methodology": bool(record.get("methodology_links")),
        "quality_documentation": bool(
            record.get("quality_links") or record.get("quality_notes")
        ),
        "revision_status": bool(record.get("revision_status")),
        "provenance": bool(record.get("provenance")),
    }
    total = len(evidence)
    present = sum(evidence.values())
    return {
        "schema": "okf-metadata-evidence.v1",
        "label": "metadata evidence availability",
        "score": round(present / total, 3),
        "present": present,
        "possible": total,
        "evidence": evidence,
        "statistical_accuracy_evaluated": False,
        "warning": (
            "This score measures discoverable metadata evidence. It does not "
            "certify statistical accuracy, methodological quality, or fitness for use."
        ),
    }


def _standards_evidence(record: dict[str, Any]) -> dict[str, Any]:
    has_method = bool(record.get("methodology_links"))
    has_quality = bool(record.get("quality_links") or record.get("quality_notes"))
    has_release = bool(record.get("metadata_modified"))
    has_provenance = bool(record.get("provenance"))
    has_dimensions = bool(record.get("dimensions") or record.get("dimension_count"))
    return {
        "schema": "okf-ons-standards-evidence.v1",
        "claims_are_alignment_not_certification": True,
        "code-of-practice-3.0": {
            "status": "partial",
            "evidence": {
                "trustworthiness": has_release and has_provenance,
                "quality": has_method or has_quality,
                "value": bool(record.get("notes") and record.get("topics")),
            },
        },
        "dcat-3": {
            "status": "aligned",
            "mapped_type": "dcat:Dataset",
            "evidence": bool(record.get("title") and record.get("url")),
        },
        "dqv": {
            "status": "partial",
            "evidence": bool(record.get("quality_evidence")),
        },
        "prov-o": {
            "status": "aligned" if has_provenance else "partial",
            "evidence": has_provenance,
        },
        "sdmx": {
            "status": "aligned" if record.get("source_surface") == "nomis" else "not-applicable",
            "evidence": has_dimensions,
        },
        "data-cube": {
            "status": "partial" if has_dimensions else "not-evaluated",
            "evidence": has_dimensions,
        },
    }


def _base_record(
    *,
    record_id: str,
    native_id: str,
    source_surface: str,
    title: str,
    description: str,
    url: str,
    record_type: str,
    snapshot_id: str,
    retrieved_at: str,
    source_url: str,
    source_sha256: str,
) -> dict[str, Any]:
    name = slugify(record_id)
    host = urlparse(url).hostname or ""
    return {
        "id": record_id,
        "record_id": record_id,
        "native_id": native_id,
        "name": name,
        "title": plain_text(title, 1_000) or native_id,
        "notes": plain_text(description),
        "description": plain_text(description),
        "record_type": record_type,
        "source_surface": source_surface,
        "publisher": "office-for-national-statistics",
        "publisher_title": "Office for National Statistics",
        "route": f"dataset/{name}",
        "open": f"dataset/{name}",
        "url": url,
        "documentation": url,
        "host": host,
        "formats": ["REST/HTTP"],
        "protocol": ["REST/HTTP"],
        "topics": [],
        "tags": [],
        "contacts": [],
        "license_id": "open-government-licence-v3",
        "license_title": "Open Government Licence v3.0",
        "license_source_id": "https://www.ons.gov.uk/help/terms-and-conditions",
        "metadata_modified": "",
        "frequency": "",
        "population_type": "",
        "geography": [],
        "time_coverage": {},
        "methodology_links": [],
        "quality_links": [],
        "revision_status": "",
        "dimension_count": 0,
        "dimensions": [],
        "resource_count": 1,
        "dcat_type": "dcat:Dataset",
        "source_adapter": source_surface,
        "source_tier": "official-provider-metadata",
        "confidence": "declared",
        "provenance": {
            "schema": "okf-provenance.v1",
            "source_url": source_url,
            "source_adapter": source_surface,
            "snapshot_id": snapshot_id,
            "retrieved_at": retrieved_at,
            "source_sha256": source_sha256,
            "native_id": native_id,
        },
    }


def normalize_ons_dataset(
    row: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    dataset_id = plain_text(row.get("id"), 300)
    if not dataset_id:
        return None
    self_url = _link(row, "links", "self") or f"{ONS_API_ROOT}/datasets/{dataset_id}"
    record = _base_record(
        record_id=f"ons-data-api:dataset:{dataset_id}",
        native_id=dataset_id,
        source_surface="ons-data-api",
        title=plain_text(row.get("title"), 1_000) or dataset_id,
        description=plain_text(row.get("description")),
        url=self_url,
        record_type="ONS Dataset",
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
        source_url=f"{ONS_API_ROOT}/datasets",
        source_sha256=source_sha256,
    )
    latest_url = _link(row, "links", "latest_version")
    _, edition, version = _version_identity(latest_url)
    based_on = row.get("is_based_on") if isinstance(row.get("is_based_on"), dict) else {}
    if edition and version:
        selection_tool = "ons_data.dimensions"
        selection_arguments = {
            "dataset": dataset_id,
            "edition": edition,
            "version": version,
        }
        selection_reason = "Dataset-specific dimension options must be selected before querying."
    elif edition:
        selection_tool = "ons_data.versions"
        selection_arguments = {"dataset": dataset_id, "edition": edition}
        selection_reason = "Select an exact version before inspecting dimensions."
    else:
        selection_tool = "ons_data.editions"
        selection_arguments = {"dataset": dataset_id}
        selection_reason = "Select an exact edition and version before inspecting dimensions."
    record.update(
        {
            "topics": _string_list(row.get("keywords")),
            "tags": _string_list(row.get("keywords")),
            "contacts": _contacts(row.get("contacts")),
            "metadata_modified": plain_text(row.get("last_updated"), 100),
            "frequency": plain_text(row.get("release_frequency"), 200),
            "population_type": plain_text(based_on.get("id"), 300),
            "geography": _string_list(row.get("geography")),
            "state": plain_text(row.get("state"), 100) or "published",
            "canonical_topic": plain_text(row.get("canonical_topic"), 200),
            "latest_edition": edition,
            "latest_version": version,
            "latest_version_url": latest_url,
            "dimensions": row.get("dimensions") if isinstance(row.get("dimensions"), list) else [],
            "dimension_count": int(row.get("dimension_count") or 0),
            "methodology_links": _string_list(row.get("methodology_links")),
            "quality_links": _string_list(row.get("quality_links")),
            "quality_notes": _string_list(row.get("quality_notes")),
            "selection": {
                "schema": "okf-ons-selection-binding.v1",
                "tool": selection_tool,
                "arguments": selection_arguments,
                "query_tool": "ons_data.query",
                "mcp_available": True,
                "binding_status": "available",
                "complete": False,
                "reason": selection_reason,
            },
        }
    )
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def _nomis_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("value", "#text", "text", "name"):
            if value.get(key):
                return plain_text(value[key])
    return plain_text(value)


def _nomis_codelist_evidence(
    projected: Mapping[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Extract only unambiguous cadence and available-period evidence."""

    raw_codelists = projected.get("nomisCodelists")
    if not isinstance(raw_codelists, list):
        return "", {}, {}
    codelists: dict[str, dict[str, Any]] = {}
    not_evidenced: list[dict[str, str]] = []
    for raw in raw_codelists:
        if not isinstance(raw, Mapping):
            continue
        concept = plain_text(raw.get("concept"), 20).upper()
        code_list = plain_text(raw.get("codeList"), 300)
        status = plain_text(raw.get("status"), 100).casefold()
        raw_codes = raw.get("codes")
        if concept not in {"FREQ", "TIME"} or not code_list:
            continue
        if status == "not-evidenced":
            reason = plain_text(raw.get("reason"), 200)
            if reason:
                not_evidenced.append(
                    {"concept": concept, "codeList": code_list, "reason": reason}
                )
            continue
        if status not in {"", "present"} or not isinstance(raw_codes, list):
            continue
        codes: list[dict[str, str]] = []
        for raw_code in raw_codes:
            if not isinstance(raw_code, Mapping):
                continue
            value = plain_text(raw_code.get("value"), 300)
            label = plain_text(raw_code.get("label"), 500)
            revision_status = plain_text(raw_code.get("revisionStatus"), 100)
            if not value or not label:
                continue
            code = {"value": value, "label": label}
            if revision_status:
                code["revisionStatus"] = revision_status
            codes.append(code)
        if codes:
            codelists[concept] = {"codeList": code_list, "codes": codes}

    frequency = ""
    frequency_metadata: dict[str, Any] = {}
    frequency_source = codelists.get("FREQ")
    if frequency_source:
        options = [
            {"code": code["value"], "label": code["label"]}
            for code in frequency_source["codes"]
        ]
        labels = sorted(
            {
                code["label"]
                for code in frequency_source["codes"]
                if code["label"].casefold()
                not in {"n/a", "not applicable", "not available", "unknown"}
            },
            key=str.casefold,
        )
        single_frequency = len(frequency_source["codes"]) == 1 and len(labels) == 1
        frequency_metadata = {
            "codeList": frequency_source["codeList"],
            "codeCount": len(frequency_source["codes"]),
            "labels": labels,
            "options": options,
            "singleFrequencyDerived": single_frequency,
        }
        if single_frequency:
            frequency = labels[0]

    time_coverage: dict[str, Any] = {}
    time_metadata: dict[str, Any] = {}
    time_source = codelists.get("TIME")
    if time_source:
        rejected_statuses = {
            "future",
            "not available",
            "not released",
            "pre-release",
            "prerelease",
            "unreleased",
        }
        available = [
            code
            for code in time_source["codes"]
            if code.get("revisionStatus", "").casefold() not in rejected_statuses
            and not re.search(
                r"\b(?:not yet released|not released|unreleased)\b",
                code["label"],
                re.IGNORECASE,
            )
        ]
        time_metadata = {
            "codeList": time_source["codeList"],
            "codeCount": len(time_source["codes"]),
            "availableCodeCount": len(available),
            "coverageDerived": False,
        }
        years = [
            (int(code["value"]), code)
            for code in available
            if re.fullmatch(r"[12][0-9]{3}", code["value"])
        ]
        months: list[tuple[tuple[int, int], dict[str, str]]] = []
        for code in available:
            match = re.fullmatch(r"([12][0-9]{3})-([0-9]{2})", code["value"])
            if match and 1 <= int(match.group(2)) <= 12:
                months.append(((int(match.group(1)), int(match.group(2))), code))
        dated: list[tuple[Any, dict[str, str]]] = []
        if years and len(years) == len(available):
            dated = years
            time_metadata["periodFormat"] = "YYYY"
        elif months and len(months) == len(available):
            dated = months
            time_metadata["periodFormat"] = "YYYY-MM"
        if dated and len({key for key, _ in dated}) == len(dated):
            start = min(dated, key=lambda item: item[0])[1]
            end = max(dated, key=lambda item: item[0])[1]
            time_coverage = {
                "start": start["value"],
                "end": end["value"],
                "startLabel": start["label"],
                "endLabel": end["label"],
                "availablePeriodCount": len(available),
                "sourceCodeList": time_source["codeList"],
            }
            time_metadata = {
                **time_metadata,
                "coverageDerived": True,
            }
    return frequency, time_coverage, {
        **({"frequency": frequency_metadata} if frequency_metadata else {}),
        **({"time": time_metadata} if time_metadata else {}),
        **({"notEvidenced": not_evidenced} if not_evidenced else {}),
    }


def _nomis_sdmx_structure(
    projected: Mapping[str, Any],
    *,
    dataset_id: str,
    components: list[Any],
) -> dict[str, Any]:
    """Preserve source-native SDMX structure identity without claiming conformance."""

    agency = plain_text(projected.get("agencyId"), 200)
    version = plain_text(projected.get("definitionVersion"), 100)
    definition_url = _projected_url(projected, "apiDefinition") or (
        f"{NOMIS_ROOT}/dataset/{dataset_id}/def.sdmx.json"
    )
    normalised_components: list[dict[str, Any]] = []
    dimensions: list[dict[str, Any]] = []
    dimension_position = 0
    role_names = {
        "dimension": "Dimension",
        "timedimension": "TimeDimension",
        "attribute": "Attribute",
        "primarymeasure": "PrimaryMeasure",
    }
    for raw_component in components:
        if not isinstance(raw_component, Mapping):
            continue
        kind = plain_text(raw_component.get("kind"), 100).casefold()
        role = role_names.get(kind)
        if role is None:
            continue
        component = {
            key: raw_component[key]
            for key in (
                "concept",
                "codeList",
                "attachmentLevel",
                "assignmentStatus",
            )
            if raw_component.get(key) not in (None, "")
        }
        component["role"] = role
        if kind in {"dimension", "timedimension"}:
            dimension_position += 1
            source_position = raw_component.get("position")
            component["position"] = (
                source_position
                if isinstance(source_position, int) and not isinstance(source_position, bool)
                else dimension_position
            )
            dimensions.append(component)
        normalised_components.append(component)
    return {
        "schema": "okf-ons-sdmx-structure.v1",
        "standardId": "sdmx-3-1",
        "standardRole": "ontology-crosswalk-and-evidence-mapping",
        "identity": {
            "agency": agency,
            "identifier": dataset_id,
            "version": version,
            "structureRole": "DataStructureDefinition",
            "sourceStructureType": "keyfamily",
        },
        "definitionUrl": definition_url,
        "serviceEndpoint": NOMIS_ROOT,
        "components": normalised_components,
        "dimensions": dimensions,
        "selectionConstraints": {
            "sdmxRole": "ContentConstraint",
            "complete": False,
            "status": "requires-live-inspection",
            "reason": (
                "Nomis dimensions and codelist values must be selected before querying."
            ),
        },
        "upstreamSdmxVersion": "not-evidenced",
        "observationsIncluded": False,
        "assurance": (
            "Preserved SDMX identity and structure metadata do not assert that the "
            "upstream product conforms to SDMX 3.1."
        ),
    }


def normalize_nomis_dataset(
    row: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    dataset_id = plain_text(row.get("id") or row.get("agencyid"), 300)
    if not dataset_id:
        return None
    title = _nomis_value(row.get("name")) or dataset_id
    annotations = row.get("annotations", {}).get("annotation", [])
    if isinstance(annotations, dict):
        annotations = [annotations]
    annotation_text = " ".join(
        _nomis_value(annotation.get("annotationtext"))
        for annotation in annotations
        if isinstance(annotation, dict)
    )
    description = plain_text(row.get("description")) or annotation_text
    url = f"{NOMIS_ROOT}/dataset/{dataset_id}.overview.json"
    record = _base_record(
        record_id=f"nomis:dataset:{dataset_id}",
        native_id=dataset_id,
        source_surface="nomis",
        title=title,
        description=description,
        url=url,
        record_type="Nomis Dataset",
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
        source_url=f"{NOMIS_ROOT}/dataset/def.sdmx.json",
        source_sha256=source_sha256,
    )
    record.update(
        {
            "formats": ["SDMX-JSON", "JSON", "CSV", "XLS"],
            "protocol": ["SDMX", "REST/HTTP"],
            "topics": _string_list(row.get("keywords")),
            "tags": ["nomis", "sdmx"],
            "state": "published",
            "selection": {
                "schema": "okf-ons-selection-binding.v1",
                "arguments": {"dataset": dataset_id, "format": "sdmx"},
                "query_tool": "nomis_query",
                "tool_provider": "mcp-geo",
                "mcp_available": True,
                "binding_status": "available",
                "complete": False,
                "direct_metadata_url": f"{NOMIS_ROOT}/dataset/{dataset_id}/def.sdmx.json",
                "reason": "Nomis dimensions and codelist values must be selected before querying.",
            },
        }
    )
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def normalize_ogp_dataset(
    feature: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    item_id = plain_text(feature.get("id") or properties.get("id"), 500)
    if not item_id:
        return None
    title = plain_text(properties.get("title") or properties.get("name"), 1_000) or item_id
    source_description = plain_text(properties.get("description"))
    description = source_description or plain_text(
        properties.get("snippet") or properties.get("summary")
    )
    url = plain_text(
        properties.get("url")
        or properties.get("landingPage")
        or properties.get("landing_page")
        or f"{OGP_ROOT}/datasets/{item_id}"
    )
    record = _base_record(
        record_id=f"ons-open-geography:dataset:{item_id}",
        native_id=item_id,
        source_surface="ons-open-geography",
        title=title,
        description=description,
        url=url,
        record_type="ONS Geography Dataset",
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
        source_url=f"{OGP_ROOT}/api/search/v1/collections/dataset/items",
        source_sha256=source_sha256,
    )
    bbox = feature.get("bbox") or properties.get("bbox") or []
    if isinstance(bbox, list) and len(bbox) >= 4:
        bbox = [float(value) for value in bbox[:4]]
    else:
        bbox = []
    modified = (
        properties.get("modified")
        or properties.get("updated")
        or properties.get("modified_at")
        or feature.get("time")
        or ""
    )
    keywords = properties.get("keywords") or properties.get("tags") or []
    access = plain_text(properties.get("access"), 100)
    record_kind = plain_text(
        properties.get("record_kind") or properties.get("recordKind"), 200
    )
    area_served = _ogp_area_served(keywords)
    geography_vintage = _ogp_geography_vintage(title)
    frequency = _ogp_frequency(source_description)
    record.update(
        {
            "topics": _string_list(keywords) or ["Geography"],
            "tags": _string_list(keywords) + ["open-geography"],
            "metadata_created": plain_text(properties.get("created"), 100),
            "metadata_modified": plain_text(modified, 100),
            "type": record_kind,
            "state": plain_text(properties.get("status"), 100) or "published",
            "frequency": frequency,
            "geography": _string_list(
                properties.get("geography")
                or properties.get("spatial")
                or properties.get("coverage")
            ),
            "geography_vintage": geography_vintage,
            "area_served": area_served,
            "spatial": {"bbox": bbox, "crs": "EPSG:4326"} if bbox else {},
            "formats": _string_list(properties.get("formats")) or ["Download/Service"],
            "selection": {
                "schema": "okf-ons-selection-binding.v1",
                "arguments": {},
                "mcp_available": False,
                "binding_status": "planned",
                "complete": False,
                "read_only": True,
                "direct_metadata_url": url,
                "reason": (
                    "The current MCP-Geo server has no general Open Geography catalogue "
                    "item tool. Use the source URL for metadata; an MCP binding is planned."
                ),
            },
        }
    )
    if access.casefold() == "public":
        record.update(
            {
                "access_model": "public",
                "visibility": "public",
                "private": False,
            }
        )
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def _reference_links(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            plain_text(item.get("href"), 2_000)
            for item in value
            if isinstance(item, Mapping) and item.get("href")
        }
    )


def _authority_parties(value: Any) -> list[dict[str, str]]:
    """Return stable public organisation references from projected metadata."""

    rows = value if isinstance(value, list) else [value]
    parties: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if isinstance(row, Mapping):
            name = plain_text(row.get("name") or row.get("title"), 500)
            url = plain_text(row.get("url") or row.get("href"), 2_000)
            date = plain_text(row.get("date") or row.get("publicationDate"), 100)
        else:
            name = plain_text(row, 500)
            url = ""
            date = ""
        if not name:
            continue
        party = {"id": slugify(name), "name": name}
        if url:
            party["url"] = url
        if date:
            party["sourceDate"] = date
        parties[(name.casefold(), url)] = party
    return [parties[key] for key in sorted(parties)]


def _projected_url(record: Mapping[str, Any], *relations: str) -> str:
    links = record.get("links")
    if not isinstance(links, Mapping):
        return ""
    for relation in relations:
        value = links.get(relation)
        if isinstance(value, Mapping):
            url = value.get("href")
        else:
            url = value
        if url:
            return plain_text(url, 2_000)
    return ""


def _retrieved_at(provenance: Mapping[str, Any]) -> str:
    pages = provenance.get("pages")
    if not isinstance(pages, list):
        return ""
    timestamps = sorted(
        plain_text(page.get("retrievedAt"), 100)
        for page in pages
        if isinstance(page, Mapping) and page.get("retrievedAt")
    )
    return timestamps[-1] if timestamps else ""


def _finalise_projected_record(
    record: dict[str, Any],
    projected: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach acquisition provenance and evidence fields to a canonical record."""

    source = provenance.get("source")
    source = source if isinstance(source, Mapping) else {}
    source_publisher = source.get("publisher")
    source_publisher = source_publisher if isinstance(source_publisher, Mapping) else {}
    native_id = plain_text(projected.get("sourceRecordId"), 500)
    record["source_adapter"] = plain_text(source.get("adapter"), 200) or record["source_surface"]
    record["source_record_kind"] = plain_text(projected.get("recordKind"), 200) or "dataset"
    record["provenance"] = {
        "schema": "okf-provenance.v1",
        "source_url": plain_text(source.get("endpoint"), 2_000)
        or record["provenance"]["source_url"],
        "source_adapter": record["source_adapter"],
        "source_id": plain_text(source.get("id"), 300) or record["source_surface"],
        "snapshot_id": record["provenance"]["snapshot_id"],
        "retrieved_at": record["provenance"]["retrieved_at"],
        "source_sha256": plain_text(provenance.get("recordSetSha256"), 200)
        or record["provenance"]["source_sha256"],
        "native_id": native_id,
    }
    submodule = provenance.get("submodule")
    submodule = submodule if isinstance(submodule, Mapping) else {}
    source_commit_as_of = plain_text(submodule.get("commitAsOf"), 100)
    source_commit = plain_text(submodule.get("commit"), 200)
    retrieved_at = record["provenance"]["retrieved_at"]
    if source_commit:
        record["provenance"]["source_commit"] = source_commit
    if source_commit_as_of:
        record["provenance"]["source_commit_as_of"] = source_commit_as_of
        record["provenance"]["source_commit_as_of_verified"] = (
            submodule.get("commitAsOfVerified") is True
        )
    if retrieved_at:
        record["provenance"]["source_as_of"] = retrieved_at
        record["provenance"]["source_as_of_basis"] = "provenance.retrieved_at"
    elif source_commit_as_of:
        record["provenance"]["source_as_of"] = source_commit_as_of
        record["provenance"]["source_as_of_basis"] = (
            "provenance.source_commit_as_of"
        )
    else:
        record["provenance"]["source_as_of"] = ""
        record["provenance"]["source_as_of_basis"] = "not-evidenced"
    declared_publishers = (
        projected.get("sourcePublishers")
        or projected.get("sourcePublisher")
        or projected.get("producers")
    )
    source_publishers = _authority_parties(declared_publishers)
    if not source_publishers:
        source_publishers = _authority_parties(source_publisher)
    surface_operator = _authority_parties(
        projected.get("surfaceOperator") or projected.get("operator")
    )
    if not surface_operator:
        surface_operator = _authority_parties(source_publisher)
    bundle_publisher = dict(BUNDLE_PUBLISHER)
    record["source_publishers"] = source_publishers
    record["surface_operator"] = surface_operator[0] if surface_operator else {}
    record["authority"] = {
        "schema": "okf-qualified-authority.v1",
        "sourcePublisher": source_publishers,
        "surfaceOperator": record["surface_operator"],
        "bundlePublisher": bundle_publisher,
        "semanticAuthority": {
            **bundle_publisher,
            "scope": "this generated bundle release only",
            "status": "experimental",
        },
        "reviewedBy": [],
        "notEndorsedBySource": True,
        "operationalAuthority": "external live-data service",
        "decisionAuthority": "accountable external person or institution",
    }
    record["assertion_provenance"] = {
        "schema": "okf-qualified-assertion-provenance.v1",
        "statementClass": "deterministically-normalised",
        "wasDerivedFrom": record["provenance"]["source_url"],
        "sourceRecordId": native_id,
        "sourceRecordSetSha256": record["provenance"]["source_sha256"],
        "wasGeneratedBy": {
            "type": "deterministic-metadata-normalisation",
            "software": "okf-ons",
            "repository": OKF_ONS_REPOSITORY,
        },
        "wasAttributedTo": bundle_publisher,
        "reviewStatus": "not-reviewed-by-source",
    }
    derivation = projected.get("derivation")
    if isinstance(derivation, Mapping):
        record["assertion_provenance"]["sourceDerivation"] = dict(derivation)
    record["identity"] = {
        "dataset_id": native_id,
        "edition": record.get("latest_edition") or "",
        "version": record.get("latest_version") or "",
    }
    if record.get("dataset_family"):
        record["identity"].update(
            {
                "indicator_slug": native_id,
                "internal_dataset_id": record["dataset_family"],
                "indicator_code": record.get("indicator_code") or "",
                "source_edition_version_available": False,
            }
        )
    record["publication"] = {
        "release_date": record.get("first_released") or "",
        "revision_status": record.get("revision_status") or "",
        "revision_date": record.get("last_revised") or "",
        "next_update": record.get("next_update") or "",
        "state": record.get("state") or "",
    }
    record["statistical"] = {
        "measure": record.get("measure") or "",
        "unit": record.get("unit_of_measure") or "",
        "population": record.get("population_type") or "",
        "geography": record.get("geography") or [],
        "time_coverage": record.get("time_coverage") or {},
        "frequency": record.get("frequency") or "",
        "dimensions": record.get("dimensions") or [],
        "revision_status": record.get("revision_status") or "",
        "revision_date": record.get("last_revised") or "",
        "quality_notes": record.get("quality_notes")
        or sorted(
            {
                *record.get("methodology_links", []),
                *record.get("quality_links", []),
            }
        ),
        "metadata_derivation": record.get("metadata_derivation") or {},
    }
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def _normalize_els_indicator(
    projected: Mapping[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    """Normalise a safe, pinned ELS indicator metadata projection."""

    slug = plain_text(projected.get("sourceRecordId"), 300)
    if not slug:
        return None
    taxonomy = projected.get("taxonomy")
    taxonomy = taxonomy if isinstance(taxonomy, Mapping) else {}
    geography = projected.get("geography")
    geography = dict(geography) if isinstance(geography, Mapping) else {}
    dimensions = projected.get("dimensions")
    dimensions = list(dimensions) if isinstance(dimensions, list) else []
    producers = projected.get("producers")
    producers = list(producers) if isinstance(producers, list) else []
    aliases = _string_list(projected.get("aliases"))
    self_url = _projected_url(projected, "self") or (
        f"https://www.ons.gov.uk/explore-local-statistics/indicators/{slug}"
    )
    metadata_url = _projected_url(projected, "metadata") or self_url
    topic = plain_text(taxonomy.get("topic"), 300)
    subtopic = plain_text(taxonomy.get("subTopic"), 300)
    title = plain_text(projected.get("title"), 1_000) or slug
    description = plain_text(projected.get("description"))
    caveats = [
        plain_text(value)
        for value in projected.get("caveats", [])
        if plain_text(value)
    ] if isinstance(projected.get("caveats"), list) else []
    methodology_links, quality_links = _els_documentation_links(caveats)
    area_served = _els_area_served(geography)
    endpoint_host = _public_host(metadata_url)
    documentation_host = _public_host(self_url)
    resource_hosts = sorted(
        {host for host in (endpoint_host, documentation_host) if host}
    )
    record = _base_record(
        record_id=f"ons-explore-local-statistics:indicator:{slug}",
        native_id=slug,
        source_surface="ons-explore-local-statistics",
        title=title,
        description=description,
        url=self_url,
        record_type="ONS Explore Local Statistics Indicator",
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
        source_url=metadata_url,
        source_sha256=source_sha256,
    )
    source_publishers = _authority_parties(producers)
    sole_publisher = source_publishers[0] if len(source_publishers) == 1 else {}
    if len(source_publishers) > 1:
        publisher_id = "multiple-source-producers"
        publisher_title = f"{len(source_publishers)} attributed source producers"
        publisher_uri = ""
    else:
        publisher_id = sole_publisher.get("id") or "source-producer-not-evidenced"
        publisher_title = sole_publisher.get("name") or "Source producer not evidenced"
        publisher_uri = sole_publisher.get("url") or ""
    derivation = projected.get("derivation")
    derivation = dict(derivation) if isinstance(derivation, Mapping) else {}
    derived_flags = projected.get("derivedMetadataFlags")
    derived_flags = dict(derived_flags) if isinstance(derived_flags, Mapping) else {}
    classification = projected.get("classificationAssertions")
    classification = dict(classification) if isinstance(classification, Mapping) else {}
    record.update(
        {
            "publisher": publisher_id,
            "publisher_title": publisher_title,
            "publisher_uri": publisher_uri,
            "source_publishers": source_publishers,
            "type": plain_text(projected.get("recordKind"), 200),
            "formats": ["JSON-stat metadata", "REST/HTTP"],
            "protocol": ["REST/HTTP"],
            "topics": _string_list([topic, subtopic]),
            "tags": sorted(
                {
                    "explore-local-statistics",
                    "indicator",
                    "local-statistics",
                    *(_string_list([topic, subtopic])),
                }
            ),
            "state": plain_text(projected.get("lifecycleState"), 100) or "published",
            "metadata_modified": plain_text(
                projected.get("metadataModified") or projected.get("lastUpdated"), 100
            ),
            "data_modified": plain_text(projected.get("dataModified"), 100),
            "frequency": plain_text(projected.get("releaseFrequency"), 200),
            "measure": plain_text(projected.get("measure"), 500),
            "unit_of_measure": plain_text(projected.get("unitOfMeasure"), 500),
            "dataset_family": plain_text(projected.get("internalDatasetId"), 500),
            "indicator_code": plain_text(projected.get("indicatorCode"), 1_000),
            "subtitle": plain_text(projected.get("subtitle"), 2_000),
            "subtopic": subtopic,
            "geography": _string_list(geography.get("levels")),
            "geography_metadata": geography,
            "geography_vintage": geography.get("vintage") or "",
            "area_served": area_served,
            "endpoint_host": endpoint_host,
            "documentation_host": documentation_host,
            "resource_hosts": resource_hosts,
            "time_coverage": (
                dict(projected["timeCoverage"])
                if isinstance(projected.get("timeCoverage"), Mapping)
                else {}
            ),
            "period_format": plain_text(projected.get("periodFormat"), 100),
            "dimensions": dimensions,
            "dimension_count": len(dimensions),
            "dimension_order": [
                plain_text(value, 300)
                for value in projected.get("dimensionOrder", [])
                if plain_text(value, 300)
            ]
            if isinstance(projected.get("dimensionOrder"), list)
            else [],
            "caveats": caveats,
            "quality_notes": caveats,
            "methodology_links": methodology_links,
            "quality_links": quality_links,
            "statistical_flags": classification,
            "metadata_derivation": {
                **derivation,
                "modes": sorted(
                    {
                        str(mode)
                        for mode in (
                            derivation.get("mode"),
                            derived_flags.get("mode"),
                            geography.get("derivationMode"),
                        )
                        if mode
                    }
                ),
                "structureDerivedFlags": derived_flags,
            },
            "presentation": (
                dict(projected["presentation"])
                if isinstance(projected.get("presentation"), Mapping)
                else {}
            ),
            "evaluation_aliases": [
                f"ons-explore-local-statistics:indicator:{alias}" for alias in aliases
            ],
            "native_aliases": aliases,
            "source_tier": "ons-curated-multi-producer-metadata",
            "confidence": "declared-and-structure-derived",
            "license_id": "not-evaluated",
            "license_title": "Rights not evaluated for this multi-producer indicator metadata",
            "license_source_id": "",
            "rights_status": "not-evaluated",
            "selection": {
                "schema": "okf-ons-selection-binding.v1",
                "arguments": {"indicator": slug},
                "mcp_available": False,
                "binding_status": "planned",
                "complete": False,
                "read_only": True,
                "direct_metadata_url": metadata_url,
                "reason": (
                    "The pinned ELS application exposes internal metadata and data routes, "
                    "but this repository has no reviewed live ELS execution binding."
                ),
            },
        }
    )
    derivation_fields: dict[str, Mapping[str, Any]] = {}
    if record.get("type"):
        derivation_fields["type"] = {
            "mode": "source-declared",
            "sourceField": "recordKind",
        }
    if caveats:
        derivation_fields["quality_notes"] = {
            "mode": "source-declared",
            "sourceField": "caveats",
        }
    if methodology_links:
        derivation_fields["methodology_links"] = {
            "mode": "deterministic-extraction",
            "sourceField": "caveats",
            "classifier": "els-explicit-method-link-v1",
        }
    if quality_links:
        derivation_fields["quality_links"] = {
            "mode": "deterministic-extraction",
            "sourceField": "caveats",
            "classifier": "els-explicit-quality-link-v1",
        }
    if area_served:
        derivation_fields["area_served"] = {
            "mode": "controlled-vocabulary-crosswalk",
            "sourceField": "geography.countries",
            "crosswalk": "els-country-code-v1",
        }
    if endpoint_host:
        derivation_fields["endpoint_host"] = {
            "mode": "deterministic-extraction",
            "sourceField": "links.metadata",
        }
    if documentation_host:
        derivation_fields["documentation_host"] = {
            "mode": "deterministic-extraction",
            "sourceField": "links.self",
        }
    if resource_hosts:
        derivation_fields["resource_hosts"] = {
            "mode": "deterministic-extraction",
            "sourceFields": ["links.metadata", "links.self"],
        }
    record["metadata_derivation"] = _merge_field_derivation(
        record.get("metadata_derivation"), derivation_fields
    )
    return record


def normalize_acquisition_record(
    projected: Mapping[str, Any],
    *,
    snapshot_id: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Compile a public ``AcquisitionResult`` projection into an Explorer record."""

    source_id = plain_text(projected.get("sourceId"), 300)
    native_id = plain_text(projected.get("sourceRecordId"), 500)
    if not source_id or not native_id:
        return None
    retrieved_at = _retrieved_at(provenance)
    source_sha256 = plain_text(provenance.get("recordSetSha256"), 200)
    title = plain_text(projected.get("title"), 1_000) or native_id
    description = plain_text(projected.get("description"))
    keywords = _string_list(projected.get("keywords"))

    if source_id == "ons-data-api":
        based_on = (
            dict(projected["isBasedOn"])
            if isinstance(projected.get("isBasedOn"), Mapping)
            else {}
        )
        contacts = projected.get("contacts")
        contacts = contacts if isinstance(contacts, list) else []
        dimensions = _ons_version_dimensions(
            projected.get("versionDimensions", projected.get("dimensions"))
        )
        geography_dimensions = _ons_geography_dimensions(dimensions)
        geography = [
            plain_text(
                dimension.get("label")
                or dimension.get("name")
                or dimension.get("id"),
                500,
            )
            for dimension in geography_dimensions
        ]
        geography = list(dict.fromkeys(value for value in geography if value))
        dimension_quality_links = sorted(
            {
                str(dimension["quality_statement_url"])
                for dimension in dimensions
                if dimension.get("quality_statement_url")
            }
        )
        dimension_quality_notes = sorted(
            {
                str(dimension["quality_statement_text"])
                for dimension in dimensions
                if dimension.get("quality_statement_text")
            }
        )
        quality_links = sorted(
            {
                *_reference_links(projected.get("qualityMethodologyInformation")),
                *dimension_quality_links,
            }
        )
        canonical_topic = plain_text(projected.get("canonicalTopic"), 200)
        subtopics = _string_list(projected.get("subtopics"))
        derivation_fields: dict[str, Any] = {}
        if contacts:
            derivation_fields["contacts"] = {
                "mode": "source-declared",
                "sourceField": "contacts",
            }
        if based_on.get("id"):
            derivation_fields["population_type"] = {
                "mode": "source-declared",
                "sourceField": "is_based_on",
            }
        if canonical_topic or subtopics:
            derivation_fields["taxonomy"] = {
                "mode": "source-declared",
                "sourceFields": ["canonical_topic", "subtopics"],
            }
        if dimensions:
            derivation_fields["dimensions"] = {
                "mode": "source-declared",
                "sourceField": "version.metadata.dimensions",
            }
        if geography_dimensions:
            derivation_fields["geography"] = {
                "mode": "deterministic-extraction",
                "sourceField": "version.metadata.dimensions",
                "rule": "is-area-type-or-exact-geography-name-v1",
            }
        if dimension_quality_links:
            derivation_fields["quality_links"] = {
                "mode": "source-declared",
                "sourceField": (
                    "version.metadata.dimensions[].quality_statement_url"
                ),
            }
        if dimension_quality_notes:
            derivation_fields["quality_notes"] = {
                "mode": "source-declared",
                "sourceField": (
                    "version.metadata.dimensions[].quality_statement_text"
                ),
            }
        raw = {
            "id": native_id,
            "title": title,
            "description": description,
            "state": projected.get("lifecycleState"),
            "last_updated": projected.get("lastUpdated"),
            "release_frequency": projected.get("releaseFrequency"),
            "keywords": keywords,
            "links": projected.get("links"),
            "contacts": contacts,
            "is_based_on": based_on,
            "canonical_topic": canonical_topic,
            "methodology_links": _reference_links(projected.get("methodologies")),
            "quality_links": quality_links,
            "quality_notes": dimension_quality_notes,
            "geography": geography,
            "dimensions": dimensions,
            "dimension_count": len(dimensions),
        }
        record = normalize_ons_dataset(
            raw,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            source_sha256=source_sha256,
        )
        if record is None:
            return None
        record.update(
            {
                "unit_of_measure": plain_text(projected.get("unitOfMeasure"), 300),
                "next_release": plain_text(projected.get("nextRelease"), 100),
                "national_statistic": projected.get("nationalStatistic"),
                "related_datasets": projected.get("relatedDatasets", []),
                "related_content": projected.get("relatedContent", []),
                "publications": projected.get("publications", []),
                "themes": projected.get("themes", []),
                "canonical_topic": canonical_topic,
                "subtopic": subtopics,
                "type": plain_text(projected.get("datasetType"), 200),
                "dataset_type": plain_text(projected.get("datasetType"), 200),
                "survey": plain_text(projected.get("survey"), 200),
                "source_licence": plain_text(projected.get("licence"), 500),
                "population_type_metadata": based_on,
                "geography_metadata": (
                    {
                        "dimensions": geography_dimensions,
                        "derivationMode": "source-declared",
                    }
                    if geography_dimensions
                    else {}
                ),
                "taxonomy_metadata": {
                    "canonicalTopicId": canonical_topic,
                    "subtopicIds": subtopics,
                }
                if canonical_topic or subtopics
                else {},
                "metadata_derivation": (
                    {
                        "schema": "okf-ons-field-derivation.v1",
                        "modes": ["source-declared"],
                        "fields": derivation_fields,
                    }
                    if derivation_fields
                    else {}
                ),
            }
        )
    elif source_id == "nomis-dataset-definitions":
        annotations = projected.get("annotations")
        annotation_map = _nomis_annotation_map(annotations)
        geography_levels = _nomis_geography_levels(annotation_map)
        population_type = _nomis_population_universe(annotation_map)
        quality_links = _nomis_quality_documentation_links(annotation_map)
        quality_notes = _nomis_quality_documentation_notes(annotation_map)
        contacts = _contacts(projected.get("contacts"))
        geographic_coverage = plain_text(projected.get("geographicCoverage"), 500)
        area_served = _string_list(geographic_coverage)
        declared_last_revised = plain_text(projected.get("lastRevised"), 100)
        last_revised = declared_last_revised or plain_text(
            annotation_map.get("LastRevised"), 100
        )
        next_update = plain_text(projected.get("nextUpdate"), 100)
        frequency, time_coverage, codelist_metadata = _nomis_codelist_evidence(
            projected
        )
        derivation_fields: dict[str, Any] = {}
        if geography_levels:
            derivation_fields["geography"] = {
                "mode": "source-declared",
                "sourceAnnotation": "contenttype/geoglevel",
            }
        if population_type:
            derivation_fields["population_type"] = {
                "mode": "source-declared",
                "sourceAnnotation": "SubDescription",
            }
        if quality_links:
            derivation_fields["quality_links"] = {
                "mode": "deterministic-extraction",
                "sourceAnnotationPattern": "MetadataTextN",
                "classifier": "nomis-quality-context-v1",
            }
        if quality_notes:
            derivation_fields["quality_notes"] = {
                "mode": "deterministic-extraction",
                "sourceAnnotationPattern": "MetadataTextN",
                "classifier": "nomis-quality-context-v1",
            }
        if contacts:
            derivation_fields["contacts"] = {
                "mode": "source-declared",
                "sourceField": "overview.contact",
            }
        if area_served:
            derivation_fields["area_served"] = {
                "mode": "source-declared",
                "sourceField": "overview.coverage",
            }
        if last_revised:
            derivation_fields["last_revised"] = {
                "mode": "source-declared",
                "sourceField": (
                    "overview.lastrevised"
                    if declared_last_revised
                    else "annotations.LastRevised"
                ),
            }
        if next_update:
            derivation_fields["next_update"] = {
                "mode": "source-declared",
                "sourceField": "overview.nextupdate",
            }
        if frequency:
            derivation_fields["frequency"] = {
                "mode": "deterministic-extraction",
                "sourceField": "nomisCodelists[FREQ].codes",
                "rule": "single-explicit-frequency-label-v1",
            }
        if time_coverage:
            derivation_fields["time_coverage"] = {
                "mode": "deterministic-extraction",
                "sourceField": "nomisCodelists[TIME].codes",
                "rule": "available-time-codelist-range-v1",
            }
        raw = {
            "id": native_id,
            "name": title,
            "description": description,
            "agencyid": projected.get("agencyId"),
            "keywords": keywords,
        }
        record = normalize_nomis_dataset(
            raw,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            source_sha256=source_sha256,
        )
        if record is None:
            return None
        components = (
            projected.get("components") if isinstance(projected.get("components"), list) else []
        )
        dimensions = [
            component
            for component in components
            if isinstance(component, Mapping)
            and component.get("kind") in {"dimension", "timedimension"}
        ]
        sdmx = _nomis_sdmx_structure(
            projected,
            dataset_id=native_id,
            components=components,
        )
        record.update(
            {
                "metadata_modified": plain_text(projected.get("lastUpdated"), 100),
                "contacts": contacts,
                "population_type": population_type,
                "geography": geography_levels,
                "geography_metadata": (
                    {
                        "levels": geography_levels,
                        "derivationMode": "source-declared",
                        **(
                            {"coverage": geographic_coverage}
                            if geographic_coverage
                            else {}
                        ),
                    }
                    if geography_levels or geographic_coverage
                    else {}
                ),
                "geographic_coverage": geographic_coverage,
                "area_served": area_served,
                "quality_links": quality_links,
                "quality_notes": quality_notes,
                "unit_of_measure": plain_text(projected.get("unitOfMeasure"), 300),
                "dimensions": sdmx["dimensions"],
                "dimension_count": len(dimensions),
                "definition_version": plain_text(projected.get("definitionVersion"), 100),
                "agency_id": plain_text(projected.get("agencyId"), 200),
                "content_source": plain_text(projected.get("contentSource"), 500),
                "first_released": plain_text(projected.get("firstReleased"), 100),
                "last_revised": last_revised,
                "next_update": next_update,
                "frequency": frequency,
                "time_coverage": time_coverage,
                "nomis_codelist_metadata": codelist_metadata,
                "mnemonic": plain_text(projected.get("mnemonic"), 300),
                "publisher_uri": plain_text(projected.get("publisherUri"), 1_000),
                "annotations": annotations if isinstance(annotations, list) else [],
                "metadata_derivation": (
                    _merge_field_derivation({}, derivation_fields)
                    if derivation_fields
                    else {}
                ),
                "sdmx": sdmx,
            }
        )
    elif source_id == "ons-open-geography":
        item_url = _public_url(_projected_url(projected, "item"))
        self_url = _ogp_exact_self_url(projected, native_id)
        feature = {
            "id": native_id,
            "bbox": projected.get("spatialEnvelope", []),
            "properties": {
                "title": title,
                "description": description,
                "snippet": projected.get("snippet"),
                "url": item_url or self_url,
                "modified": projected.get("modified"),
                "created": projected.get("created"),
                "record_kind": projected.get("recordKind"),
                "access": projected.get("access"),
                "keywords": keywords,
                "status": projected.get("lifecycleState"),
                "formats": [projected.get("itemType")] if projected.get("itemType") else [],
                "geography": projected.get("classification") or projected.get("categories"),
            },
        }
        record = normalize_ogp_dataset(
            feature,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            source_sha256=source_sha256,
        )
        if record is None:
            return None
        portal_extent = projected.get("portalExtent", {})
        informative_categories = _ogp_informative_categories(
            projected.get("categories")
        )
        methodology_links = _ogp_methodology_links(
            title,
            description,
            self_url,
        )
        quality_notes = _ogp_quality_notes(description)
        geography_reference_date = _ogp_geography_reference_date(title, description)
        source_version_label = _ogp_source_version_label(title)
        revision_history_notes = _ogp_revision_history_notes(description)
        endpoint_host = _public_host(item_url or self_url)
        documentation_host = _public_host(self_url)
        resource_hosts = sorted(
            {
                host
                for url in (item_url, self_url)
                if (host := _public_host(url))
            }
        )
        record.update(
            {
                "access": plain_text(projected.get("access"), 500),
                "access_information": plain_text(projected.get("accessInformation"), 2_000),
                "source_licence": plain_text(projected.get("licence"), 2_000),
                "portal_owner": plain_text(projected.get("owner"), 500),
                "source_organisation": plain_text(projected.get("source"), 500),
                "spatial_reference": projected.get("spatialReference", {}),
                "portal_extent": portal_extent,
                "temporal_extent": projected.get("temporalExtent", {}),
                "groups": informative_categories,
                "subtopic": _ogp_category_subtopics(informative_categories),
                "methodology_links": methodology_links,
                "quality_notes": quality_notes,
                "geography_reference_date": geography_reference_date,
                "geography_metadata": (
                    {
                        "referenceDate": geography_reference_date,
                        "referenceDateSemantics": (
                            "source-declared geography resource reference/effective date"
                        ),
                        "derivationMode": "deterministic-extraction",
                    }
                    if geography_reference_date
                    else {}
                ),
                "source_version_label": source_version_label,
                "revision_history_notes": revision_history_notes,
                "endpoint_host": endpoint_host,
                "documentation_host": documentation_host,
                "resource_hosts": resource_hosts,
            }
        )
        if self_url:
            record["documentation"] = self_url
            record["selection"]["direct_metadata_url"] = self_url
        derivation_fields: dict[str, Mapping[str, Any]] = {}
        if record.get("metadata_created"):
            derivation_fields["metadata_created"] = {
                "mode": "source-declared",
                "sourceField": "created",
            }
        if record.get("type"):
            derivation_fields["type"] = {
                "mode": "source-declared",
                "sourceField": "recordKind",
            }
        if record.get("access_model") == "public":
            for field in ("access_model", "visibility", "private"):
                derivation_fields[field] = {
                    "mode": "deterministic-normalisation",
                    "sourceField": "access",
                    "rule": "public-access-v1",
                }
        if record.get("area_served"):
            derivation_fields["area_served"] = {
                "mode": "controlled-vocabulary-crosswalk",
                "sourceField": "keywords",
                "crosswalk": "ogp-country-area-keyword-v1",
            }
        if record.get("geography_vintage"):
            derivation_fields["geography_vintage"] = {
                "mode": "deterministic-extraction",
                "sourceField": "title",
                "rule": "exactly-one-distinct-title-year-v1",
            }
        if record.get("frequency"):
            derivation_fields["frequency"] = {
                "mode": "deterministic-extraction",
                "sourceField": "description",
                "rule": "explicit-cadence-phrase-v1",
            }
        if informative_categories:
            for field in ("groups", "subtopic"):
                derivation_fields[field] = {
                    "mode": "deterministic-normalisation",
                    "sourceField": "categories",
                    "rule": "exclude-generic-ogp-categories-v1",
                }
        if methodology_links:
            derivation_fields["methodology_links"] = {
                "mode": "deterministic-extraction",
                "sourceFields": ["title", "description", "links.related.self"],
                "classifier": "ogp-conservative-method-evidence-v1",
            }
        if quality_notes:
            derivation_fields["quality_notes"] = {
                "mode": "deterministic-extraction",
                "sourceField": "description",
                "classifier": "ogp-explicit-quality-limitations-v1",
            }
        if geography_reference_date:
            derivation_fields["geography_reference_date"] = {
                "mode": "deterministic-extraction",
                "sourceFields": ["title", "description"],
                "rule": "single-early-as-at-date-matching-title-year-v1",
                "semantics": "geography-resource-reference-date",
            }
        if source_version_label:
            derivation_fields["source_version_label"] = {
                "mode": "deterministic-extraction",
                "sourceField": "title",
                "rule": "parenthesised-ogp-version-label-v1",
            }
        if revision_history_notes:
            derivation_fields["revision_history_notes"] = {
                "mode": "deterministic-extraction",
                "sourceField": "description",
                "classifier": "ogp-explicit-revision-history-v1",
                "doesNotImply": "revision_status",
            }
        if endpoint_host:
            derivation_fields["endpoint_host"] = {
                "mode": "deterministic-extraction",
                "sourceFields": ["links.item", "links.related.self"],
                "rule": "item-host-else-exact-self-host-v1",
            }
        if documentation_host:
            derivation_fields["documentation_host"] = {
                "mode": "deterministic-extraction",
                "sourceField": "links.related.self",
                "rule": "exact-self-host-v1",
            }
        if resource_hosts:
            derivation_fields["resource_hosts"] = {
                "mode": "deterministic-extraction",
                "sourceFields": ["links.item", "links.related.self"],
                "rule": "exact-public-ogp-hosts-v1",
            }
        if not description and record.get("description") and projected.get("snippet"):
            derivation_fields["description"] = {
                "mode": "source-declared-fallback",
                "sourceField": "snippet",
            }
        if portal_extent:
            derivation_fields["portal_extent"] = {
                "mode": "source-declared",
                "sourceField": "portalExtent",
            }
        record["metadata_derivation"] = _merge_field_derivation(
            record.get("metadata_derivation"), derivation_fields
        )
    elif source_id == "ons-explore-local-statistics":
        record = _normalize_els_indicator(
            projected,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            source_sha256=source_sha256,
        )
        if record is None:
            return None
    else:
        raise ValueError(f"Unsupported acquisition source id {source_id!r}")

    return _finalise_projected_record(record, projected, provenance)


def _contrast_values(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source surface": record.get("source_surface") or "",
        "record type": record.get("record_type") or "",
        "dataset family": record.get("dataset_family") or "",
        "topic": record.get("subtopic") or record.get("topics") or [],
        "measure": record.get("measure") or "",
        "unit": record.get("unit_of_measure") or "",
        "frequency": record.get("frequency") or "",
        "population": record.get("population_type") or "",
        "geography": record.get("geography") or [],
        "geography vintage": record.get("geography_vintage") or "",
        "time coverage": record.get("time_coverage") or {},
        "source producers": [
            publisher.get("name")
            for publisher in record.get("source_publishers", [])
            if isinstance(publisher, Mapping)
        ],
        # Derivation remains available on each hydrated record, but it is provenance
        # about how a field was produced rather than an evidence-backed distinction
        # between two datasets. Including the full ledger here also makes compact
        # alternative previews grow with every metadata enrichment.
        "edition": record.get("latest_edition") or "",
        "version": record.get("latest_version") or "",
        "release state": record.get("state") or "",
        "last updated": record.get("metadata_modified") or "",
        "methodology evidence": bool(record.get("methodology_links")),
        "quality documentation": bool(record.get("quality_links")),
    }


def _has_contrast_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def declared_table_codes(record: Mapping[str, Any]) -> list[str]:
    """Return table codes observed in native identity or a title prefix."""

    codes: set[str] = set()
    native_id = plain_text(record.get("native_id"), 200).upper()
    if _NATIVE_TABLE_CODE_RE.fullmatch(native_id):
        codes.add(native_id)
    title_match = _TITLE_TABLE_CODE_RE.match(plain_text(record.get("title"), 1_000))
    if title_match:
        codes.add(title_match.group(1).upper())
    return sorted(codes)


def _normalised_table_title(title: str) -> str:
    without_code = _TITLE_TABLE_CODE_RE.sub("", plain_text(title, 1_000), count=1)
    words = without_code.casefold().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", words).strip()


def build_cross_source_reconciliation(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Link cross-source representations only when a declared table code agrees."""

    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        codes = declared_table_codes(record)
        record["declared_table_codes"] = codes
        for code in codes:
            by_code[code].append(record)

    relationships: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    matched_codes: list[str] = []
    title_aligned_codes: list[str] = []
    title_conflicted_codes: list[dict[str, Any]] = []
    disambiguated_candidates: list[dict[str, Any]] = []
    anchor_codes = {
        code
        for code, rows in by_code.items()
        if any(row.get("source_surface") == "ons-data-api" for row in rows)
    }
    unmatched_codes: list[str] = []
    for code in sorted(anchor_codes):
        rows = by_code[code]
        anchors = [row for row in rows if row.get("source_surface") == "ons-data-api"]
        if len(anchors) != 1:
            conflicts.append(
                {
                    "code": code,
                    "reason": "ambiguous-anchor-source",
                    "source": "ons-data-api",
                    "record_ids": sorted(str(row["id"]) for row in anchors),
                }
            )
            continue
        anchor = anchors[0]
        candidates = [row for row in rows if row.get("source_surface") != "ons-data-api"]
        if not candidates:
            unmatched_codes.append(code)
            continue

        anchor_title = _normalised_table_title(str(anchor.get("title") or ""))
        exact_title_candidates = [
            row
            for row in candidates
            if _normalised_table_title(str(row.get("title") or "")) == anchor_title
        ]
        if len(exact_title_candidates) == 1:
            candidate = exact_title_candidates[0]
            if len(candidates) > 1:
                disambiguated_candidates.append(
                    {
                        "code": code,
                        "selected_record_id": candidate["id"],
                        "evidence": "unique-normalised-title-match",
                        "rejected_record_ids": sorted(
                            str(row["id"]) for row in candidates if row is not candidate
                        ),
                    }
                )
        elif len(candidates) == 1:
            candidate = candidates[0]
        else:
            conflicts.append(
                {
                    "code": code,
                    "reason": "ambiguous-cross-source-candidates",
                    "anchor_record_id": anchor["id"],
                    "candidate_record_ids": sorted(str(row["id"]) for row in candidates),
                    "normalised_title_match_count": len(exact_title_candidates),
                }
            )
            continue

        matched_codes.append(code)
        candidate_title = _normalised_table_title(str(candidate.get("title") or ""))
        title_alignment = (
            "normalised-identical" if anchor_title == candidate_title else "conflicted"
        )
        if title_alignment == "normalised-identical":
            title_aligned_codes.append(code)
        else:
            title_conflicted_codes.append(
                {
                    "code": code,
                    "source_title": anchor["title"],
                    "target_title": candidate["title"],
                }
            )
        relationships.append(
            {
                "source": anchor["route"],
                "target": candidate["route"],
                "kind": "cross-source-representation",
                "confidence": "observed-identifier",
                "evidence_type": "shared-declared-statistical-table-code",
                "shared_code": code,
                "source_native_id": anchor["native_id"],
                "target_native_id": candidate["native_id"],
                "source_record_id": anchor["id"],
                "target_record_id": candidate["id"],
                "title_alignment": title_alignment,
                "statistical_equivalence_asserted": False,
                "note": (
                    "The shared declared table code supports cross-source "
                    "reconciliation, not statistical equivalence."
                ),
            }
        )

    report = {
        "schema": "okf-ons-cross-source-reconciliation.v1",
        "method": "declared-native-id-or-title-prefix-table-code",
        "statistical_equivalence_asserted": False,
        "anchor_source": "ons-data-api",
        "anchor_codes_detected": len(anchor_codes),
        "matched_codes": matched_codes,
        "matched_code_count": len(matched_codes),
        "title_aligned_code_count": len(set(title_aligned_codes)),
        "title_conflicted_code_count": len(title_conflicted_codes),
        "title_conflicts": title_conflicted_codes,
        "unmatched_anchor_codes": unmatched_codes,
        "unmatched_anchor_code_count": len(unmatched_codes),
        "relationship_count": len(relationships),
        "candidate_disambiguation_count": len(disambiguated_candidates),
        "candidate_disambiguations": disambiguated_candidates,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }
    return relationships, report


def build_alternatives(
    records: list[dict[str, Any]],
    *,
    limit: int = 4,
    threshold: float = 0.32,
) -> list[dict[str, Any]]:
    """Attach deterministic, evidence-backed alternatives to records."""

    token_sets: list[set[str]] = []
    inverted: dict[str, list[int]] = defaultdict(list)
    for ordinal, record in enumerate(records):
        tokens = set(
            tokenize(
                record.get("title"),
                " ".join(record.get("topics") or []),
                " ".join(record.get("tags") or []),
            )
        )
        token_sets.append(tokens)
        for token in tokens:
            inverted[token].append(ordinal)

    relationships: list[dict[str, Any]] = []
    for ordinal, record in enumerate(records):
        tokens = token_sets[ordinal]
        candidates: set[int] = set()
        for token in tokens:
            if len(inverted[token]) <= 500:
                candidates.update(inverted[token])
        candidates.discard(ordinal)
        scored: list[tuple[float, int, list[str]]] = []
        for other_ordinal in candidates:
            other = token_sets[other_ordinal]
            union = tokens | other
            if not union:
                continue
            shared = sorted(tokens & other)
            title_a = set(tokenize(record.get("title")))
            title_b = set(tokenize(records[other_ordinal].get("title")))
            title_union = title_a | title_b
            title_score = len(title_a & title_b) / len(title_union) if title_union else 0.0
            score = 0.75 * title_score + 0.25 * (len(shared) / len(union))
            if score >= threshold:
                scored.append((score, other_ordinal, shared))
        scored.sort(key=lambda item: (-item[0], records[item[1]]["title"], records[item[1]]["id"]))

        alternatives: list[dict[str, Any]] = []
        left = _contrast_values(record)
        for score, other_ordinal, shared in scored[:limit]:
            other_record = records[other_ordinal]
            right = _contrast_values(other_record)
            differences = [
                {"field": field, "selected": left[field], "alternative": right[field]}
                for field in left
                if left[field] != right[field]
                and (_has_contrast_value(left[field]) or _has_contrast_value(right[field]))
            ]
            relationship_type = (
                "cross-source-alternative"
                if record.get("source_surface") != other_record.get("source_surface")
                else "alternative"
            )
            alternative = {
                "record_id": other_record["id"],
                "title": other_record["title"],
                "route": other_record["route"],
                "source_surface": other_record["source_surface"],
                "record_type": other_record["record_type"],
                "relationship_type": relationship_type,
                "similarity": round(score, 3),
                "shared_terms": shared[:12],
                "differences": differences,
                "not_enough_evidence": not bool(differences),
            }
            alternatives.append(alternative)
            relationships.append(
                {
                    "source": record["route"],
                    "target": other_record["route"],
                    "kind": relationship_type,
                    "confidence": "inferred",
                    "evidence_type": "deterministic-title-topic-similarity",
                    "score": round(score, 3),
                    "shared_terms": shared[:12],
                    "differences": differences,
                    "statistical_equivalence_asserted": False,
                }
            )
        record["alternatives"] = alternatives
        record["alternative_count"] = len(alternatives)
        if alternatives:
            titles = "; ".join(row["title"] for row in alternatives[:3])
            record["context_note"] = f"Compare before selecting: {titles}."
        else:
            record["context_note"] = "No close alternative was identified from available metadata."
    return relationships


def unique_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = str(record.get("id") or "")
        if record_id and record_id not in by_id:
            by_id[record_id] = record
    return sorted(
        by_id.values(),
        key=lambda row: (
            str(row.get("source_surface") or ""),
            str(row.get("title") or "").casefold(),
            str(row.get("id") or ""),
        ),
    )
