"""Public Archidekt deck API client (unofficial archidekt.com/api)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from mtg_rebuilder.config import ARCHIDEKT_API_BASE

_SKIP_CATEGORIES = frozenset({"maybeboard", "token", "tokens", "consider", "wishlist"})
_SIDEBOARD_CATEGORIES = frozenset({"sideboard"})
_COMMANDER_CATEGORIES = frozenset({"commander"})
_PARTNER_CATEGORIES = frozenset({"partner"})
_COMPANION_CATEGORIES = frozenset({"companion"})
_BACKGROUND_CATEGORIES = frozenset({"background"})


@dataclass(frozen=True)
class _ListedCard:
    name: str
    quantity: int
    set_code: str | None = None
    collector_number: str | None = None
    foil: bool = False


@dataclass(frozen=True)
class ArchidektDeckExport:
    """Deck metadata + MTGO-style text ready for ImportService."""

    deck_id: int
    name: str
    list_text: str
    commander_name: str | None = None
    secondary_role: str | None = None  # partner | companion | background
    secondary_name: str | None = None


class ArchidektClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=ARCHIDEKT_API_BASE,
            headers={
                "User-Agent": "MTG-Rebuilder/0.10",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_deck(self, deck_id: int | str) -> dict[str, Any]:
        response = self._client.get(f"/api/decks/{deck_id}/")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Archidekt response shape")
        if "error" in payload and "cards" not in payload:
            raise ValueError(str(payload.get("error") or "Archidekt deck not found"))
        return payload


def deck_export_from_payload(payload: dict[str, Any]) -> ArchidektDeckExport:
    deck_id_raw = payload.get("id")
    try:
        deck_id = int(deck_id_raw)
    except (TypeError, ValueError):
        deck_id = 0
    name = str(payload.get("name") or "Archidekt deck").strip() or "Archidekt deck"

    included_by_category = _included_map(payload.get("categories"))
    commanders: list[_ListedCard] = []
    partners: list[_ListedCard] = []
    companions: list[_ListedCard] = []
    backgrounds: list[_ListedCard] = []
    mainboard: list[_ListedCard] = []

    cards = payload.get("cards")
    if not isinstance(cards, list):
        cards = []

    for entry in cards:
        if not isinstance(entry, dict):
            continue
        parsed = _parse_card_entry(entry, included_by_category)
        if parsed is None:
            continue
        card, bucket = parsed
        if bucket == "commander":
            commanders.append(card)
        elif bucket == "partner":
            partners.append(card)
        elif bucket == "companion":
            companions.append(card)
        elif bucket == "background":
            backgrounds.append(card)
        else:
            mainboard.append(card)

    # Archidekt often tags Partner decks with two "Commander" categories.
    if len(commanders) > 1 and not partners:
        partners = commanders[1:]
        commanders = commanders[:1]

    lines: list[str] = []
    commander_name: str | None = None
    secondary_role: str | None = None
    secondary_name: str | None = None

    for index, card in enumerate(commanders):
        if index == 0:
            commander_name = card.name
            lines.append(_format_line("Commander", card))
        else:
            if secondary_role is None:
                secondary_role = "partner"
                secondary_name = card.name
            lines.append(_format_line("Partner", card))

    for card in partners:
        if secondary_role is None:
            secondary_role = "partner"
            secondary_name = card.name
        lines.append(_format_line("Partner", card))

    for card in companions:
        if secondary_role is None:
            secondary_role = "companion"
            secondary_name = card.name
        lines.append(_format_line("Companion", card))

    for card in backgrounds:
        if secondary_role is None:
            secondary_role = "background"
            secondary_name = card.name
        lines.append(_format_line("Background", card))

    mainboard.sort(key=lambda item: item.name.casefold())
    for card in mainboard:
        lines.append(_format_line(None, card))

    return ArchidektDeckExport(
        deck_id=deck_id,
        name=name,
        list_text="\n".join(lines),
        commander_name=commander_name,
        secondary_role=secondary_role,
        secondary_name=secondary_name,
    )


def fetch_archidekt_deck(deck_id: int | str) -> ArchidektDeckExport:
    client = ArchidektClient()
    try:
        payload = client.fetch_deck(deck_id)
    finally:
        client.close()
    return deck_export_from_payload(payload)


def _included_map(categories: Any) -> dict[str, bool]:
    result: dict[str, bool] = {}
    if not isinstance(categories, list):
        return result
    for cat in categories:
        if not isinstance(cat, dict) or not cat.get("name"):
            continue
        name = str(cat["name"]).casefold()
        result[name] = bool(cat.get("includedInDeck", True))
    return result


def _parse_card_entry(
    entry: dict[str, Any],
    included_by_category: dict[str, bool],
) -> tuple[_ListedCard, str] | None:
    categories = [
        str(name).casefold()
        for name in (entry.get("categories") or [])
        if name
    ]
    is_companion_flag = bool(entry.get("companion"))

    if any(cat in _SKIP_CATEGORIES for cat in categories):
        return None
    if any(included_by_category.get(cat, True) is False for cat in categories):
        # Companion often sits in Sideboard; keep it via the flag / category.
        if not (
            is_companion_flag
            or any(cat in _COMPANION_CATEGORIES for cat in categories)
            or any(cat in _BACKGROUND_CATEGORIES for cat in categories)
        ):
            return None
    if any(cat in _SIDEBOARD_CATEGORIES for cat in categories):
        if not (
            is_companion_flag
            or any(cat in _COMPANION_CATEGORIES for cat in categories)
            or any(cat in _BACKGROUND_CATEGORIES for cat in categories)
        ):
            return None

    card = entry.get("card")
    if not isinstance(card, dict):
        return None
    oracle = card.get("oracleCard")
    if isinstance(oracle, dict) and oracle.get("name"):
        card_name = str(oracle["name"]).strip()
    elif card.get("displayName"):
        card_name = str(card["displayName"]).strip()
    else:
        return None
    if not card_name:
        return None

    try:
        quantity = int(entry.get("quantity") or 1)
    except (TypeError, ValueError):
        quantity = 1
    if quantity <= 0:
        return None

    set_code: str | None = None
    edition = card.get("edition")
    if isinstance(edition, dict) and edition.get("editioncode"):
        set_code = str(edition["editioncode"]).upper()
    raw_number = card.get("collectorNumber")
    if raw_number is None:
        raw_number = card.get("collector_number")
    collector = (
        raw_number.strip()
        if isinstance(raw_number, str) and raw_number.strip()
        else None
    )
    foil = _is_foil(entry) or _is_foil(card)

    if is_companion_flag or any(cat in _COMPANION_CATEGORIES for cat in categories):
        bucket = "companion"
    elif any(cat in _BACKGROUND_CATEGORIES for cat in categories):
        bucket = "background"
    elif any(cat in _PARTNER_CATEGORIES for cat in categories):
        bucket = "partner"
    elif any(cat in _COMMANDER_CATEGORIES for cat in categories):
        bucket = "commander"
    else:
        bucket = "main"

    return (
        _ListedCard(
            name=card_name,
            quantity=quantity,
            set_code=set_code,
            collector_number=collector,
            foil=foil,
        ),
        bucket,
    )


def _is_foil(payload: dict[str, Any]) -> bool:
    if payload.get("foil") is True or payload.get("isFoil") is True:
        return True
    finish = payload.get("finish")
    return isinstance(finish, str) and finish.strip().casefold() == "foil"


def _format_line(role: str | None, card: _ListedCard) -> str:
    body = f"{card.quantity} {card.name}"
    if card.set_code:
        body = f"{body} ({card.set_code})"
        if card.collector_number:
            body = f"{body} {card.collector_number}"
    if card.foil:
        body = f"{body} *F*"
    if role:
        return f"{role}: {body}"
    return body
