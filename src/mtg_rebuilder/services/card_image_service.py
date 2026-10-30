import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy.orm import Session

from mtg_rebuilder.api.scryfall_client import ScryfallClient
from mtg_rebuilder.config import IMAGES_DIR
from mtg_rebuilder.models import Card, CardPrinting
from mtg_rebuilder.repositories import CardRepository
from mtg_rebuilder.services.scryfall_service import ScryfallService, card_from_scryfall

IMAGE_SUFFIX = ".jpg"
BACK_IMAGE_SUFFIX = "_back.jpg"

class ImageDownloadScope(StrEnum):
    COLLECTION = "collection"
    CACHED = "cached"


@dataclass(frozen=True)
class ImageDownloadResult:
    downloaded: int
    skipped: int
    missing_uri: int
    total: int


@dataclass(frozen=True)
class ImageCacheStatus:
    collection_with_uri: int
    collection_on_disk: int
    cached_with_uri: int
    cached_on_disk: int


def preview_image_url(image_uri: str | None) -> str | None:
    """Print-grid URLs are ``small``. The side preview wants ``normal``."""
    if image_uri is None:
        return None
    cleaned = image_uri.strip()
    if not cleaned:
        return None
    return cleaned.replace("/small/", "/normal/", 1)


def printing_image_path(
    printing_id: str,
    images_dir: Path | None = None,
) -> Path:
    root = images_dir if images_dir is not None else IMAGES_DIR
    return root / "prints" / f"{printing_id}.jpg"


def image_path_for(
    oracle_id: str,
    images_dir: Path | None = None,
    *,
    back: bool = False,
) -> Path:
    root = images_dir if images_dir is not None else IMAGES_DIR
    suffix = BACK_IMAGE_SUFFIX if back else IMAGE_SUFFIX
    return root / f"{oracle_id}{suffix}"


class CardImageService:
    def __init__(
        self,
        session: Session,
        client: ScryfallClient | None = None,
        *,
        images_dir: Path | None = None,
    ) -> None:
        self._session = session
        self._cards = CardRepository(session)
        self._client = client
        self._owns_client = client is None
        self._images_dir = images_dir if images_dir is not None else IMAGES_DIR

    def _get_client(self) -> ScryfallClient:
        if self._client is None:
            self._client = ScryfallClient()
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def status(self) -> ImageCacheStatus:
        """Front-face image counts, as set arithmetic over ids.

        Runs on the GUI thread against the whole cache (~36k cards), so it reads
        one column and lists the images directory once rather than loading each
        ``Card`` and ``stat()``-ing its file.
        """
        collection_ids = set(ScryfallService(self._session).collection_oracle_ids())
        with_uri = self._cards.oracle_ids_with_image_uri()
        on_disk = with_uri & self._front_image_ids_on_disk()
        # Collection cards without image_uri are not counted as "with uri".
        collection_with_uri = with_uri & collection_ids
        return ImageCacheStatus(
            collection_with_uri=len(collection_with_uri),
            collection_on_disk=len(collection_with_uri & on_disk),
            cached_with_uri=len(with_uri),
            cached_on_disk=len(on_disk),
        )

    def _front_image_ids_on_disk(self) -> set[str]:
        try:
            entries = os.scandir(self._images_dir)
        except OSError:
            return set()
        with entries:
            return {
                entry.name[: -len(IMAGE_SUFFIX)]
                for entry in entries
                if entry.name.endswith(IMAGE_SUFFIX)
                and not entry.name.endswith(BACK_IMAGE_SUFFIX)
                and entry.is_file()
            }

    def has_back_image(self, oracle_id: str) -> bool:
        card = self._cards.get(oracle_id)
        return bool(card is not None and card.image_uri_back)

    def ensure_printing_image(self, printing_id: str) -> Path | None:
        """Local normal-size image for one Scryfall printing.

        Returns None when that printing has no picture or the download fails,
        so the preview can fall back to the card's usual image.
        """
        safe = printing_id.strip()
        if not safe or "/" in safe or ".." in safe:
            return None
        destination = printing_image_path(safe, self._images_dir)
        if destination.is_file() and destination.stat().st_size > 0:
            return destination
        row = self._session.get(CardPrinting, safe)
        image_uri = preview_image_url(row.image_uri if row is not None else None)
        if not image_uri:
            return None
        try:
            self._get_client().download_file(image_uri, destination)
        except Exception:
            destination.unlink(missing_ok=True)
            return None
        return destination

    def ensure_image(self, oracle_id: str, *, back: bool = False) -> Path | None:
        """Local path for one card face, downloading it on demand.

        Returns None instead of raising when the card has no image or Scryfall
        is unreachable, so previews can fall back to a placeholder.
        """
        destination = image_path_for(oracle_id, self._images_dir, back=back)
        if destination.is_file():
            return destination

        card = self._cards.get(oracle_id)
        if card is None:
            return None

        image_uri = card.image_uri_back if back else card.image_uri
        if not image_uri:
            image_uri = self._refresh_image_uris(card, back=back)
        if not image_uri:
            return None

        try:
            self._get_client().download_file(image_uri, destination)
        except Exception:
            destination.unlink(missing_ok=True)
            return None
        return destination

    def _refresh_image_uris(self, card: Card, *, back: bool) -> str | None:
        """Fill missing image URLs for a single card from the Scryfall API."""
        try:
            payload = self._get_client().fetch_cards_collection(
                [{"oracle_id": card.oracle_id}]
            )
        except Exception:
            return None

        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return None

        refreshed = card_from_scryfall(data[0])
        card.image_uri = refreshed.image_uri or card.image_uri
        card.image_uri_back = refreshed.image_uri_back or card.image_uri_back
        self._cards.flush()
        return card.image_uri_back if back else card.image_uri

    def download_images(
        self,
        scope: ImageDownloadScope,
        *,
        force: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> ImageDownloadResult:
        def report(message: str) -> None:
            if progress is not None:
                progress(message)

        targets = self._targets_for_scope(scope)
        total = len(targets)
        if total == 0:
            report("No cards with image URLs to download.")
            return ImageDownloadResult(
                downloaded=0, skipped=0, missing_uri=0, total=0
            )

        self._images_dir.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        skipped = 0
        missing_uri = 0

        for index, (oracle_id, image_uri) in enumerate(targets, start=1):
            if not image_uri:
                missing_uri += 1
                continue
            destination = image_path_for(oracle_id, self._images_dir)
            if destination.is_file() and not force:
                skipped += 1
                if index % 50 == 0 or index == total:
                    report(
                        f"Downloading images… {index:,}/{total:,} "
                        f"({downloaded:,} new, {skipped:,} skipped)"
                    )
                continue
            report(f"Downloading images… {index:,}/{total:,}")
            self._get_client().download_file(image_uri, destination)
            downloaded += 1

        report(
            f"Image download complete — {downloaded:,} downloaded, "
            f"{skipped:,} skipped, {missing_uri:,} missing URL."
        )
        return ImageDownloadResult(
            downloaded=downloaded,
            skipped=skipped,
            missing_uri=missing_uri,
            total=total,
        )

    def _targets_for_scope(
        self, scope: ImageDownloadScope
    ) -> list[tuple[str, str | None]]:
        if scope is ImageDownloadScope.COLLECTION:
            oracle_ids = ScryfallService(self._session).collection_oracle_ids()
            if not oracle_ids:
                return []
            cards = self._cards.list_by_oracle_ids(oracle_ids)
            by_id = {card.oracle_id: card.image_uri for card in cards}
            return [(oid, by_id.get(oid)) for oid in oracle_ids]

        cards = self._cards.list_with_image_uri(ordered=True)
        return [(card.oracle_id, card.image_uri) for card in cards]
