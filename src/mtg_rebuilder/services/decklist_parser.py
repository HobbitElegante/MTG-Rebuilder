"""Parse decklists from Moxfield/MTGO text, Arena, Archidekt, and MTGO .dek XML."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from enum import Enum

from mtg_rebuilder.models.enums import DeckCardRole

ROLE_PREFIXES: dict[str, DeckCardRole] = {
    "commander": DeckCardRole.COMMANDER,
    "partner": DeckCardRole.PARTNER,
    "companion": DeckCardRole.COMPANION,
    "background": DeckCardRole.BACKGROUND,
    "token": DeckCardRole.TOKEN,
    "sideboard": DeckCardRole.MAIN,
}

# Category / section headers that are not card lines.
CATEGORY_HEADER_RE = re.compile(
    r"^(?:\/\/|#|creatures?\s*\(|instants?\s*\(|sorceries?\s*\(|enchantments?\s*\(|"
    r"artifacts?\s*\(|lands?\s*\(|planeswalkers?\s*\(|battles?\s*\(|"
    r"maybeboard|sideboard:|mainboard:)\b.*$",
    re.IGNORECASE,
)

ARENA_SECTION_RE = re.compile(
    r"^(commander|deck|sideboard|companion)$",
    re.IGNORECASE,
)

# qty [x] name [(SET) [collector] [*F*]] [*F*] [Category] …
# Collector number stays inside the set group so a bare name cannot lose its
# last word. A trailing star (``101★`` or ``263*``) is part of the number;
# ``*F*`` is foil and is not a collector number. ``*F*`` may also sit on a
# line with no set.
CARD_LINE_RE = re.compile(
    r"^(?:(?P<role>[A-Za-z ]+):\s*)?"
    r"(?P<qty>\d+)\s*(?:x\s*)?"
    r"(?P<name>.+?)"
    r"(?:"
    r"\s*\((?P<set>[A-Z0-9]+)\)"
    r"(?:\s+(?P<collector>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?:★|\*(?!F\*))?))?"
    r")?"
    r"(?:\s*(?P<foil>\*F\*))?"
    r"(?:\s*\[[^\]]*\])?"
    r"\s*$"
)

MOXFIELD_URL_RE = re.compile(
    r"https?://(?:www\.)?moxfield\.com/decks/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

ARCHIDEKT_URL_RE = re.compile(
    r"https?://(?:www\.)?archidekt\.com/decks/(\d+)",
    re.IGNORECASE,
)


class DecklistFormat(str, Enum):
    MOXFIELD_MTGO = "moxfield_mtgo"
    ARENA = "arena"
    ARCHIDEKT = "archidekt"
    MTGO_DEK = "mtgo_dek"
    MOXFIELD_URL = "moxfield_url"
    ARCHIDEKT_URL = "archidekt_url"


@dataclass(frozen=True)
class ParsedDeckLine:
    quantity: int
    name: str
    role: DeckCardRole
    raw_line: str
    # Set code when the line carried one, e.g. "1 Sol Ring (C21) 263".
    set_code: str | None = None
    # Collector number when the line carried one, including a trailing star.
    collector_number: str | None = None
    # True only when the line had ``*F*``. Absence is not nonfoil.
    foil: bool = False


def _single_line_url_candidate(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    if "\n" in stripped or "\r" in stripped:
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        if len(lines) != 1:
            return None
        stripped = lines[0]
    return stripped


def _match_deck_url(pattern: re.Pattern[str], text: str) -> str | None:
    stripped = _single_line_url_candidate(text)
    if stripped is None:
        return None
    match = pattern.fullmatch(stripped.rstrip("/"))
    if match is None:
        match = pattern.search(stripped)
        if match is None:
            return None
        # Reject if there is substantial non-URL content.
        if len(stripped) > len(match.group(0)) + 20:
            return None
    return match.group(1)


def extract_moxfield_deck_id(text: str) -> str | None:
    """Return public deck id if text is (only) a Moxfield deck URL."""
    return _match_deck_url(MOXFIELD_URL_RE, text)


def extract_archidekt_deck_id(text: str) -> str | None:
    """Return numeric deck id if text is (only) an Archidekt deck URL."""
    return _match_deck_url(ARCHIDEKT_URL_RE, text)


def detect_format(text: str) -> DecklistFormat:
    stripped = text.strip()
    if not stripped:
        return DecklistFormat.MOXFIELD_MTGO

    if extract_moxfield_deck_id(stripped) is not None:
        return DecklistFormat.MOXFIELD_URL

    if extract_archidekt_deck_id(stripped) is not None:
        return DecklistFormat.ARCHIDEKT_URL

    if "<Deck" in stripped or (
        stripped.lstrip().startswith("<") and "Quantity=" in stripped
    ):
        return DecklistFormat.MTGO_DEK

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    has_1x = False
    has_bracket_category = False
    has_arena_section = False
    for line in lines[:40]:
        if ARENA_SECTION_RE.match(line):
            has_arena_section = True
        if re.match(r"^\d+\s*x\s+", line, re.IGNORECASE):
            has_1x = True
        if re.search(r"\[[^\]]+\]\s*$", line):
            has_bracket_category = True

    if has_arena_section:
        return DecklistFormat.ARENA

    if has_1x or has_bracket_category:
        return DecklistFormat.ARCHIDEKT

    return DecklistFormat.MOXFIELD_MTGO


def parse_decklist(text: str) -> list[ParsedDeckLine]:
    """Parse pasted/loaded decklist text into card lines (not URLs)."""
    fmt = detect_format(text)
    if fmt in (DecklistFormat.MOXFIELD_URL, DecklistFormat.ARCHIDEKT_URL):
        return []
    if fmt == DecklistFormat.MTGO_DEK:
        return _parse_mtgo_dek(text)
    if fmt == DecklistFormat.ARENA:
        return _parse_arena(text)
    # Archidekt and Moxfield/MTGO share the same line grammar.
    return _parse_line_based(text)


def parse_moxfield_line(line: str) -> ParsedDeckLine | None:
    """Parse a single MTGO/Moxfield/Archidekt-style card line."""
    return _parse_card_line(line, default_role=DeckCardRole.MAIN)


def parse_moxfield_export(text: str) -> list[ParsedDeckLine]:
    """Backward-compatible alias for line-based Moxfield/MTGO text."""
    return _parse_line_based(text)


def _parse_role_prefix(line: str) -> tuple[DeckCardRole | None, str]:
    if ":" not in line:
        return None, line
    prefix, remainder = line.split(":", 1)
    role_key = prefix.strip().lower()
    if role_key in ROLE_PREFIXES:
        return ROLE_PREFIXES[role_key], remainder.strip()
    return None, line


def _parse_card_line(
    line: str,
    *,
    default_role: DeckCardRole,
) -> ParsedDeckLine | None:
    stripped = line.strip()
    if not stripped:
        return None
    if CATEGORY_HEADER_RE.match(stripped):
        return None
    if ARENA_SECTION_RE.match(stripped):
        return None

    role, content = _parse_role_prefix(stripped)
    match = CARD_LINE_RE.match(content)
    if not match:
        return None

    parsed_role = role
    if parsed_role is None and match.group("role"):
        role_key = match.group("role").strip().lower()
        parsed_role = ROLE_PREFIXES.get(role_key)

    name = match.group("name").strip()
    # Strip leftover Archidekt category if regex optional group missed it.
    name = re.sub(r"\s*\[[^\]]*\]\s*$", "", name).strip()
    if not name:
        return None

    set_code = match.group("set")
    collector = match.group("collector")
    return ParsedDeckLine(
        quantity=int(match.group("qty")),
        name=name,
        role=parsed_role or default_role,
        raw_line=line,
        set_code=set_code.upper() if set_code else None,
        collector_number=collector or None,
        foil=match.group("foil") is not None,
    )


def _parse_line_based(text: str) -> list[ParsedDeckLine]:
    parsed: list[ParsedDeckLine] = []
    for line in text.splitlines():
        item = _parse_card_line(line, default_role=DeckCardRole.MAIN)
        if item is not None:
            parsed.append(item)
    return parsed


def _parse_arena(text: str) -> list[ParsedDeckLine]:
    parsed: list[ParsedDeckLine] = []
    section_role = DeckCardRole.MAIN
    in_sideboard = False
    commanders_in_section = 0

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        section = ARENA_SECTION_RE.match(stripped)
        if section:
            key = section.group(1).lower()
            if key == "commander":
                section_role = DeckCardRole.COMMANDER
                in_sideboard = False
                commanders_in_section = 0
            elif key == "companion":
                section_role = DeckCardRole.COMPANION
                in_sideboard = False
            elif key == "sideboard":
                section_role = DeckCardRole.MAIN
                in_sideboard = True
            else:  # deck
                section_role = DeckCardRole.MAIN
                in_sideboard = False
            continue

        if in_sideboard:
            continue

        item = _parse_card_line(raw, default_role=DeckCardRole.MAIN)
        if item is None:
            continue

        if section_role == DeckCardRole.COMMANDER:
            role = (
                DeckCardRole.PARTNER
                if commanders_in_section > 0
                else DeckCardRole.COMMANDER
            )
            commanders_in_section += 1
            item = replace(item, role=role)
        elif section_role == DeckCardRole.COMPANION:
            item = replace(item, role=DeckCardRole.COMPANION)

        parsed.append(item)

    return parsed


def _parse_mtgo_dek(text: str) -> list[ParsedDeckLine]:
    """Parse MTGO .dek XML; sideboard cards are skipped."""
    stripped = text.strip()
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError:
        # Some exports wrap fragments; try wrapping.
        try:
            root = ET.fromstring(f"<Deck>{stripped}</Deck>")
        except ET.ParseError:
            return []

    parsed: list[ParsedDeckLine] = []
    # Cards may be direct children or nested.
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag.lower() != "cards":
            continue
        name = elem.attrib.get("Name") or elem.attrib.get("name")
        if not name:
            continue
        qty_raw = elem.attrib.get("Quantity") or elem.attrib.get("quantity") or "1"
        try:
            quantity = int(qty_raw)
        except ValueError:
            continue
        sideboard = (
            elem.attrib.get("Sideboard") or elem.attrib.get("sideboard") or "false"
        ).lower() in {"true", "1", "yes"}
        if sideboard:
            continue
        raw_line = f"{quantity} {name}"
        parsed.append(
            ParsedDeckLine(
                quantity=quantity,
                name=name.strip(),
                role=DeckCardRole.MAIN,
                raw_line=raw_line,
            )
        )
    return parsed
