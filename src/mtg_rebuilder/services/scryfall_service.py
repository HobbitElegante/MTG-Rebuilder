import re
from collections.abc import Callable

from sqlalchemy.orm import Session

from mtg_rebuilder.algorithms.card_utils import (
    commander_legality_from_payload,
    is_art_series_type_line,
    is_basic_land_type_line,
    is_token_type_line,
)
from mtg_rebuilder.api.scryfall_client import ScryfallClient
from mtg_rebuilder.config import SCRYFALL_COLLECTION_BATCH_SIZE
from mtg_rebuilder.models import Card
from mtg_rebuilder.repositories import (
    CardPrintingRepository,
    CardPrintRepository,
    CardRepository,
)


def normalize_card_name(name: str) -> str:
    lowered = name.casefold().strip()
    return re.sub(r"[^a-z0-9]+", "", lowered)


def _is_lookup_candidate(card: Card) -> bool:
    return not is_art_series_type_line(card.type_line)


def _pick_preferred_card(candidates: list[Card], *, prefer_token: bool) -> Card | None:
    """Prefer the playable card over a same-named token (or the reverse)."""
    usable = [card for card in candidates if _is_lookup_candidate(card)]
    if not usable:
        return None
    if prefer_token:
        tokens = [card for card in usable if card.is_token]
        if tokens:
            return tokens[0]
        return usable[0]
    playable = [card for card in usable if not card.is_token]
    if playable:
        return playable[0]
    return usable[0]


def _normal_image_uri(source: object) -> str | None:
    if not isinstance(source, dict):
        return None
    images = source.get("image_uris")
    if not isinstance(images, dict):
        return None
    normal = images.get("normal")
    return normal if isinstance(normal, str) else None


def oracle_id_from_scryfall(payload: dict) -> str | None:
    """Resolve oracle_id from a Scryfall card object.

    ``unique_artwork`` includes ``reversible_card`` prints with no top-level
    ``oracle_id``; the identity lives on each face instead.
    """
    oracle_id = payload.get("oracle_id")
    if isinstance(oracle_id, str) and oracle_id:
        return oracle_id
    faces = payload.get("card_faces")
    if not isinstance(faces, list):
        return None
    for face in faces:
        if not isinstance(face, dict):
            continue
        face_id = face.get("oracle_id")
        if isinstance(face_id, str) and face_id:
            return face_id
    return None


def card_from_scryfall(payload: dict) -> Card:
    faces = payload.get("card_faces")
    faces = faces if isinstance(faces, list) else []
    primary = faces[0] if faces and isinstance(faces[0], dict) else None

    oracle_id = oracle_id_from_scryfall(payload)
    if oracle_id is None:
        raise ValueError("Scryfall card payload is missing oracle_id")

    name = payload.get("name")
    # Reversible prints use "Name // Name"; prefer the face name for the cache.
    if payload.get("layout") == "reversible_card" and primary and primary.get("name"):
        name = primary["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("Scryfall card payload is missing name")

    image_uri = _normal_image_uri(payload)
    if image_uri is None and primary is not None:
        image_uri = _normal_image_uri(primary)
    # Split/adventure cards carry a single top-level image, so only true
    # double-faced layouts end up with a back image here. Reversible cards are
    # the same oracle on both sides — do not treat the reverse as a DFC back.
    if payload.get("layout") == "reversible_card":
        image_uri_back = None
    else:
        image_uri_back = _normal_image_uri(faces[1]) if len(faces) > 1 else None

    type_line = payload.get("type_line")
    if not type_line and primary is not None:
        type_line = primary.get("type_line")

    mana_cost = payload.get("mana_cost")
    if mana_cost is None and primary is not None:
        mana_cost = primary.get("mana_cost")

    oracle_text = payload.get("oracle_text")
    if oracle_text is None and primary is not None:
        oracle_text = primary.get("oracle_text")

    colors = payload.get("colors")
    if colors is None and primary is not None:
        colors = primary.get("colors")

    cmc = payload.get("cmc")
    if cmc is None and primary is not None:
        cmc = primary.get("cmc")

    rarity = payload.get("rarity")
    if not isinstance(rarity, str) or not rarity.strip():
        rarity = None
    else:
        rarity = rarity.strip().casefold()

    return Card(
        oracle_id=oracle_id,
        name=name,
        mana_cost=mana_cost,
        type_line=type_line,
        oracle_text=oracle_text,
        colors="".join(colors or []),
        color_identity="".join(payload.get("color_identity") or []),
        cmc=float(cmc or 0),
        rarity=rarity,
        image_uri=image_uri,
        image_uri_back=image_uri_back,
        commander_legality=commander_legality_from_payload(payload),
        is_basic_land=is_basic_land_type_line(type_line),
        is_token=is_token_type_line(type_line),
    )


def prints_from_scryfall(
    payloads: list[dict],
) -> list[tuple[str, str | None, str | None, str | None]]:
    """Collapse Scryfall printings to one row per set, newest release kept.

    Each row is ``(set_code, set_name, released_at, rarity)``.
    """
    by_code: dict[str, tuple[str, str | None, str | None, str | None]] = {}
    for entry in payloads:
        set_code = entry.get("set")
        if not isinstance(set_code, str) or not set_code.strip():
            continue
        code = set_code.strip().upper()
        set_name = entry.get("set_name")
        released_at = entry.get("released_at")
        rarity_raw = entry.get("rarity")
        rarity = (
            rarity_raw.strip().casefold()
            if isinstance(rarity_raw, str) and rarity_raw.strip()
            else None
        )
        by_code[code] = (
            code,
            set_name if isinstance(set_name, str) else None,
            released_at if isinstance(released_at, str) else None,
            rarity,
        )
    return sorted(by_code.values(), key=lambda row: (row[2] or "", row[0]))


def _printing_image_uri(entry: dict) -> str | None:
    """Small Scryfall image for the print grid. Faces cover double-faced cards."""
    sources = [entry]
    faces = entry.get("card_faces")
    if isinstance(faces, list):
        sources.extend(face for face in faces if isinstance(face, dict))
    for source in sources:
        images = source.get("image_uris")
        if not isinstance(images, dict):
            continue
        for key in ("small", "normal"):
            uri = images.get(key)
            if isinstance(uri, str) and uri.strip():
                return uri.strip()
    return None


def printings_from_scryfall(
    payloads: list[dict],
) -> list[tuple[str, str, str | None, str | None, str | None, str]]:
    """One row per Scryfall card id. Does not collapse arts in the same set.

    Each row is ``(scryfall_id, set_code, collector_number, illustration_id, label, image_uri)``.
    ``image_uri`` is ``""`` when Scryfall has no picture, so a later open does
    not refetch the whole list just to look again.
    """
    by_id: dict[str, tuple[str, str, str | None, str | None, str | None]] = {}
    for entry in payloads:
        scryfall_id = entry.get("id")
        set_code = entry.get("set")
        if not isinstance(scryfall_id, str) or not scryfall_id.strip():
            continue
        if not isinstance(set_code, str) or not set_code.strip():
            continue
        number = entry.get("collector_number")
        collector = number.strip() if isinstance(number, str) and number.strip() else None
        illustration = entry.get("illustration_id")
        illustration_id = (
            illustration.strip()
            if isinstance(illustration, str) and illustration.strip()
            else None
        )
        by_id[scryfall_id.strip()] = (
            scryfall_id.strip(),
            set_code.strip().upper(),
            collector,
            illustration_id,
            _printing_label(entry, collector),
            _printing_image_uri(entry) or "",
        )
    return sorted(by_id.values(), key=lambda row: (row[1], row[2] or "", row[0]))


def _printing_tuple(row) -> tuple[str, str, str | None, str | None, str | None]:
    return (
        row.id,
        row.set_code,
        row.collector_number,
        row.label,
        row.image_uri or None,
    )


def _printing_label(entry: dict, collector: str | None) -> str | None:
    """Short combo text: collector number, plus a frame hint when there is one."""
    effects = entry.get("frame_effects")
    hint = ""
    if isinstance(effects, list):
        for effect in effects:
            if isinstance(effect, str) and effect.strip():
                hint = effect.strip()
                break
    if collector and hint:
        return f"{collector} · {hint}"[:255]
    if collector:
        return collector[:255]
    if hint:
        return hint[:255]
    return None


class ScryfallOfflineError(RuntimeError):
    pass


class ScryfallService:
    def __init__(self, session: Session, client: ScryfallClient | None = None) -> None:
        self._session = session
        self._cards = CardRepository(session)
        self._prints = CardPrintRepository(session)
        self._printings = CardPrintingRepository(session)
        self._client = client or ScryfallClient()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def lookup_local(self, name: str, *, prefer_token: bool = False) -> Card | None:
        trimmed = name.strip()
        if not trimmed:
            return None

        exact_matches = self._cards.list_exact_lower(trimmed)
        exact = _pick_preferred_card(exact_matches, prefer_token=prefer_token)
        if exact is not None:
            return exact

        normalized_query = normalize_card_name(trimmed)
        if normalized_query:
            normalized_matches = [
                card
                for card in self._cards.list_all()
                if normalize_card_name(card.name) == normalized_query
            ]
            normalized = _pick_preferred_card(
                normalized_matches, prefer_token=prefer_token
            )
            if normalized is not None:
                return normalized

        fuzzy_matches = self._cards.list_fuzzy(trimmed, limit=20)
        preferred_fuzzy = [
            card
            for card in fuzzy_matches
            if _is_lookup_candidate(card)
            and (card.is_token if prefer_token else not card.is_token)
        ]
        if len(preferred_fuzzy) == 1:
            return preferred_fuzzy[0]
        if len(preferred_fuzzy) == 0:
            fallback = _pick_preferred_card(fuzzy_matches, prefer_token=prefer_token)
            # Only accept a sole fuzzy fallback to avoid ambiguous names.
            usable = [card for card in fuzzy_matches if _is_lookup_candidate(card)]
            if len(usable) == 1:
                return fallback
        return None

    def upsert_from_payload(self, payload: dict) -> Card:
        card = self._cards.get(payload["oracle_id"])
        if card is None:
            card = card_from_scryfall(payload)
            self._cards.add(card)
        else:
            refreshed = card_from_scryfall(payload)
            card.name = refreshed.name
            card.mana_cost = refreshed.mana_cost
            card.type_line = refreshed.type_line
            card.oracle_text = refreshed.oracle_text
            card.colors = refreshed.colors
            card.color_identity = refreshed.color_identity
            card.cmc = refreshed.cmc
            card.rarity = refreshed.rarity
            card.image_uri = refreshed.image_uri
            card.image_uri_back = refreshed.image_uri_back
            card.commander_legality = refreshed.commander_legality
            card.is_basic_land = refreshed.is_basic_land
            card.is_token = refreshed.is_token
        self._cards.flush()
        return card

    def fetch_and_cache(self, name: str, *, prefer_token: bool = False) -> Card:
        cached = self.lookup_local(name, prefer_token=prefer_token)
        if cached is not None:
            return cached

        try:
            payload = self._client.fetch_card_fuzzy(name)
        except Exception as exc:
            raise ScryfallOfflineError(
                f"Card '{name}' is not cached locally and Scryfall is unavailable."
            ) from exc

        card = self.upsert_from_payload(payload)
        if prefer_token == card.is_token:
            return card

        # Named API usually returns the playable card; if we wanted the other
        # side of a shared name, try the local cache again after upserting.
        preferred = self.lookup_local(name, prefer_token=prefer_token)
        return preferred if preferred is not None else card

    def list_prints(
        self, oracle_id: str, *, refresh: bool = False
    ) -> list[tuple[str, str | None]]:
        """Sets the card was printed in, as ``(set_code, set_name)``.

        Cached per card after the first lookup. Returns whatever is cached when
        Scryfall is unreachable, so the edition picker still opens offline.
        """
        if not refresh and self._prints.has_any(oracle_id):
            return [(row.set_code, row.set_name) for row in self._prints.list_for_card(oracle_id)]

        try:
            payloads = self._client.fetch_card_prints(oracle_id)
        except Exception:
            return [
                (row.set_code, row.set_name)
                for row in self._prints.list_for_card(oracle_id)
            ]

        rows = prints_from_scryfall(payloads)
        if not rows:
            return []
        self._prints.replace_for_card(oracle_id, rows)
        return [(set_code, set_name) for set_code, set_name, _released, _rarity in rows]

    def list_printings(
        self, oracle_id: str, *, refresh: bool = False
    ) -> list[tuple[str, str, str | None, str | None, str | None]]:
        """Printings of one card.

        Each row is ``(scryfall_id, set_code, collector_number, label, image_uri)``.
        Cached per card after the first lookup. A cache from before images
        existed is fetched again. Offline, returns whatever is already cached.
        Does not change ``CardPrint`` (one row per set).
        """
        cached = self._printings.list_for_card(oracle_id)
        images_ready = bool(cached) and all(row.image_uri is not None for row in cached)
        if not refresh and images_ready:
            return [_printing_tuple(row) for row in cached]

        try:
            payloads = self._client.fetch_card_prints(oracle_id)
        except Exception:
            return [_printing_tuple(row) for row in self._printings.list_for_card(oracle_id)]

        rows = printings_from_scryfall(payloads)
        if not rows:
            return []
        stored = self._printings.replace_for_card(oracle_id, rows)
        return [_printing_tuple(row) for row in stored]

    def cached_card_count(self) -> int:
        return self._cards.count_all()

    def collection_oracle_ids(self) -> list[str]:
        """Oracle ids for physical inventory copies and cards on deck lists."""
        return self._cards.collection_oracle_ids()

    def refresh_collection_card_data(
        self,
        progress: Callable[[str], None] | None = None,
    ) -> int:
        """Refresh Commander legalities and image URLs for collection cards.

        Both come from the same payload, so this keeps ⚠ warnings and card
        previews current without re-downloading the full bulk pack.

        Returns how many cards were looked up (inventory copies ∪ deck lists).
        """
        oracle_ids = self.collection_oracle_ids()
        if not oracle_ids:
            if progress is not None:
                progress("No collection cards to refresh.")
            return 0

        def report(message: str) -> None:
            if progress is not None:
                progress(message)

        total = len(oracle_ids)
        batch_size = SCRYFALL_COLLECTION_BATCH_SIZE
        for start in range(0, total, batch_size):
            chunk = oracle_ids[start : start + batch_size]
            report(
                f"Refreshing card data… {min(start + len(chunk), total):,}/{total:,}"
            )
            identifiers = [{"oracle_id": oracle_id} for oracle_id in chunk]
            try:
                payload = self._client.fetch_cards_collection(identifiers)
            except Exception as exc:
                raise ScryfallOfflineError(
                    "Could not refresh collection card data from Scryfall."
                ) from exc

            data = payload.get("data")
            if not isinstance(data, list):
                continue
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                oracle_id = entry.get("oracle_id")
                if not isinstance(oracle_id, str):
                    continue
                card = self._cards.get(oracle_id)
                if card is None:
                    self.upsert_from_payload(entry)
                    continue
                refreshed = card_from_scryfall(entry)
                card.commander_legality = refreshed.commander_legality
                if refreshed.image_uri:
                    card.image_uri = refreshed.image_uri
                if refreshed.image_uri_back:
                    card.image_uri_back = refreshed.image_uri_back
                if refreshed.rarity:
                    card.rarity = refreshed.rarity

            self._cards.flush()

        report(f"Card data refreshed for {total:,} collection cards.")
        return total
