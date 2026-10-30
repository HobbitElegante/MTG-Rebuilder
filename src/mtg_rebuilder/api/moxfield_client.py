"""Public Moxfield deck API client (unofficial api2.moxfield.com)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from mtg_rebuilder.config import MOXFIELD_API_BASE

# App identity first; browser-like fallback if Cloudflare rejects the app UA.
_APP_HEADERS = {
    "User-Agent": "MTG-Rebuilder/0.10 (+https://github.com/HobbitElegante/MTG-Rebuilder)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.moxfield.com",
    "Referer": "https://www.moxfield.com/",
}
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.moxfield.com",
    "Referer": "https://www.moxfield.com/",
}

MoxfieldErrorCode = Literal["forbidden", "not_found", "http", "bad_response"]


class MoxfieldError(RuntimeError):
    """Failure fetching a public Moxfield deck (UI maps ``code`` to i18n)."""

    def __init__(self, code: MoxfieldErrorCode, *, status: int | None = None) -> None:
        self.code = code
        self.status = status
        detail = code if status is None else f"{code} ({status})"
        super().__init__(detail)


@dataclass(frozen=True)
class MoxfieldDeckExport:
    """Deck metadata + MTGO-style text ready for ImportService."""

    public_id: str
    name: str
    list_text: str
    commander_name: str | None = None
    secondary_role: str | None = None  # partner | companion | background
    secondary_name: str | None = None


class MoxfieldClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=MOXFIELD_API_BASE,
            headers=_APP_HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_deck(self, public_id: str) -> dict[str, Any]:
        response = self._request_deck(public_id)
        if response.status_code == 403:
            # Some networks/Cloudflare setups reject the app User-Agent.
            response = self._request_deck(public_id, headers=_BROWSER_HEADERS)
        if response.status_code == 403:
            raise MoxfieldError("forbidden", status=403)
        if response.status_code == 404:
            raise MoxfieldError("not_found", status=404)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MoxfieldError("http", status=exc.response.status_code) from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise MoxfieldError("bad_response")
        return payload

    def _request_deck(
        self,
        public_id: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        kwargs: dict[str, Any] = {}
        if headers is not None:
            kwargs["headers"] = headers
        response = self._client.get(f"/v3/decks/all/{public_id}", **kwargs)
        if response.status_code == 404:
            # Older path some clients still use.
            response = self._client.get(f"/v2/decks/all/{public_id}", **kwargs)
        return response


def deck_export_from_payload(payload: dict[str, Any]) -> MoxfieldDeckExport:
    public_id = str(payload.get("publicId") or payload.get("id") or "")
    name = str(payload.get("name") or "Moxfield deck").strip() or "Moxfield deck"

    lines: list[str] = []
    commander_name: str | None = None
    secondary_role: str | None = None
    secondary_name: str | None = None

    commanders = _named_board_entries(payload, "commanders")
    for index, card in enumerate(commanders):
        if index == 0:
            commander_name = card.name
            lines.append(_format_line("Commander", card))
        else:
            secondary_role = "partner"
            secondary_name = card.name
            lines.append(_format_line("Partner", card))

    companions = _named_board_entries(payload, "companions")
    for card in companions:
        if secondary_role is None:
            secondary_role = "companion"
            secondary_name = card.name
        lines.append(_format_line("Companion", card))

    backgrounds = _named_board_entries(payload, "backgrounds")
    for card in backgrounds:
        if secondary_role is None:
            secondary_role = "background"
            secondary_name = card.name
        lines.append(_format_line("Background", card))

    for card in _named_board_entries(payload, "mainboard"):
        lines.append(_format_line(None, card))

    return MoxfieldDeckExport(
        public_id=public_id,
        name=name,
        list_text="\n".join(lines),
        commander_name=commander_name,
        secondary_role=secondary_role,
        secondary_name=secondary_name,
    )


def fetch_moxfield_deck(public_id: str) -> MoxfieldDeckExport:
    client = MoxfieldClient()
    try:
        payload = client.fetch_deck(public_id)
    finally:
        client.close()
    return deck_export_from_payload(payload)


@dataclass(frozen=True)
class _MoxfieldCard:
    name: str
    quantity: int
    set_code: str | None = None
    collector_number: str | None = None
    foil: bool = False


def _named_board_entries(payload: dict[str, Any], board_name: str) -> list[_MoxfieldCard]:
    """Read a named board from v3 ``boards`` or legacy top-level v2 fields."""
    boards = payload.get("boards")
    if isinstance(boards, dict):
        board = boards.get(board_name)
        if isinstance(board, dict) and isinstance(board.get("cards"), dict):
            return _board_entries(board["cards"])
    return _board_entries(payload.get(board_name))


def _board_entries(board: Any) -> list[_MoxfieldCard]:
    if not isinstance(board, dict):
        return []
    entries: list[_MoxfieldCard] = []
    for key, value in board.items():
        if key in {"count", "cards"}:
            continue
        if not isinstance(value, dict):
            continue
        # Skip non-entry metadata blobs.
        if "quantity" not in value and "card" not in value:
            continue
        card = value.get("card")
        if isinstance(card, dict) and card.get("name"):
            card_name = str(card["name"])
        else:
            card_name = str(key)
            card = card if isinstance(card, dict) else {}
        try:
            quantity = int(value.get("quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1
        if quantity <= 0:
            continue
        set_code, collector, foil = _print_facts(card if isinstance(card, dict) else {})
        # Also accept finish on the board entry itself.
        if not foil and _is_foil(value):
            foil = True
        entries.append(
            _MoxfieldCard(
                name=card_name,
                quantity=quantity,
                set_code=set_code,
                collector_number=collector,
                foil=foil,
            )
        )
    entries.sort(key=lambda item: item.name.casefold())
    return entries


def _print_facts(card: dict[str, Any]) -> tuple[str | None, str | None, bool]:
    """Set, collector number, and foil when the payload already has them."""
    raw_set = card.get("set") or card.get("set_code")
    set_code = raw_set.strip().upper() if isinstance(raw_set, str) and raw_set.strip() else None
    raw_number = card.get("cn") or card.get("collector_number") or card.get("collectorNumber")
    collector = (
        raw_number.strip()
        if isinstance(raw_number, str) and raw_number.strip()
        else None
    )
    return set_code, collector, _is_foil(card)


def _is_foil(payload: dict[str, Any]) -> bool:
    if payload.get("foil") is True or payload.get("isFoil") is True:
        return True
    finish = payload.get("finish")
    return isinstance(finish, str) and finish.strip().casefold() == "foil"


def _format_line(role: str | None, card: _MoxfieldCard) -> str:
    """MTGO line. Set is added only when the number or foil needs it.

    A set by itself stays off the line, matching exports that never had one.
    """
    body = f"{card.quantity} {card.name}"
    if card.set_code and (card.collector_number or card.foil):
        body = f"{body} ({card.set_code})"
        if card.collector_number:
            body = f"{body} {card.collector_number}"
    if card.foil:
        body = f"{body} *F*"
    if role:
        return f"{role}: {body}"
    return body
