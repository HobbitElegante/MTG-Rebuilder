from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mtg_rebuilder.models import Base, Card, CardCopy, CardPrinting
from mtg_rebuilder.services.card_image_service import (
    CardImageService,
    ImageDownloadScope,
    image_path_for,
    preview_image_url,
)


class FakeImageClient:
    def __init__(self, collection_payload: dict | None = None) -> None:
        self.downloaded: list[tuple[str, Path]] = []
        self.collection_calls: list[list[dict[str, str]]] = []
        self._collection_payload = collection_payload or {"data": []}

    def download_file(self, url: str, destination: Path) -> None:
        self.downloaded.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"jpeg-bytes")

    def fetch_cards_collection(self, identifiers: list[dict[str, str]]) -> dict:
        self.collection_calls.append(identifiers)
        return self._collection_payload

    def close(self) -> None:
        return None


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session


def test_download_images_collection_and_skip_existing(
    session: Session, tmp_path: Path
) -> None:
    owned = Card(
        oracle_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        name="Sol Ring",
        image_uri="https://example.test/sol.jpg",
        is_basic_land=False,
        is_token=False,
    )
    other = Card(
        oracle_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        name="Mana Crypt",
        image_uri="https://example.test/crypt.jpg",
        is_basic_land=False,
        is_token=False,
    )
    session.add_all([owned, other])
    session.add(CardCopy(card_id=owned.oracle_id))
    session.flush()

    existing = image_path_for(owned.oracle_id, tmp_path)
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"already")

    client = FakeImageClient()
    service = CardImageService(session, client, images_dir=tmp_path)
    result = service.download_images(ImageDownloadScope.COLLECTION)

    assert result.total == 1
    assert result.skipped == 1
    assert result.downloaded == 0
    assert client.downloaded == []

    result_force = service.download_images(
        ImageDownloadScope.COLLECTION, force=True
    )
    assert result_force.downloaded == 1
    assert client.downloaded[0][0] == "https://example.test/sol.jpg"


def test_download_images_cached_scope(session: Session, tmp_path: Path) -> None:
    session.add_all(
        [
            Card(
                oracle_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                name="Sol Ring",
                image_uri="https://example.test/sol.jpg",
                is_basic_land=False,
                is_token=False,
            ),
            Card(
                oracle_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                name="No Art",
                image_uri=None,
                is_basic_land=False,
                is_token=False,
            ),
        ]
    )
    session.flush()

    client = FakeImageClient()
    service = CardImageService(session, client, images_dir=tmp_path)
    result = service.download_images(ImageDownloadScope.CACHED)

    assert result.total == 1
    assert result.downloaded == 1
    assert image_path_for(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", tmp_path
    ).is_file()

    status = service.status()
    assert status.cached_with_uri == 1
    assert status.cached_on_disk == 1


def test_status_counts_collection_and_cache(session: Session, tmp_path: Path) -> None:
    def card(oracle_id: str, uri: str | None) -> Card:
        return Card(
            oracle_id=oracle_id,
            name=oracle_id,
            image_uri=uri,
            is_basic_land=False,
            is_token=False,
        )

    session.add_all(
        [
            card("owned-on-disk", "https://example.test/1.jpg"),
            card("owned-missing", "https://example.test/2.jpg"),
            card("owned-no-uri", None),
            card("cached-on-disk", "https://example.test/3.jpg"),
            card("cached-back-only", "https://example.test/4.jpg"),
            card("cached-missing", "https://example.test/5.jpg"),
        ]
    )
    session.add_all(
        CardCopy(card_id=oid) for oid in ("owned-on-disk", "owned-missing", "owned-no-uri")
    )
    session.flush()
    for name in (
        "owned-on-disk.jpg",
        "owned-no-uri.jpg",
        "cached-on-disk.jpg",
        "cached-back-only_back.jpg",
        "not-in-db.jpg",
        "notes.txt",
    ):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "folder.jpg").mkdir()

    status = CardImageService(session, FakeImageClient(), images_dir=tmp_path).status()

    assert status.collection_with_uri == 2
    assert status.collection_on_disk == 1
    assert status.cached_with_uri == 5
    assert status.cached_on_disk == 2


def test_status_without_images_dir(session: Session, tmp_path: Path) -> None:
    session.add(
        Card(
            oracle_id="sol",
            name="Sol Ring",
            image_uri="https://example.test/sol.jpg",
            is_basic_land=False,
            is_token=False,
        )
    )
    session.flush()

    status = CardImageService(
        session, FakeImageClient(), images_dir=tmp_path / "missing"
    ).status()

    assert status.cached_with_uri == 1
    assert status.cached_on_disk == 0


def test_image_path_for_back_face(tmp_path: Path) -> None:
    front = image_path_for("oracle-1", tmp_path)
    back = image_path_for("oracle-1", tmp_path, back=True)

    assert front.name == "oracle-1.jpg"
    assert back.name == "oracle-1_back.jpg"


def test_ensure_image_returns_existing_file_without_download(
    session: Session, tmp_path: Path
) -> None:
    session.add(
        Card(
            oracle_id="oracle-1",
            name="Sol Ring",
            image_uri="https://example.test/sol.jpg",
            is_basic_land=False,
            is_token=False,
        )
    )
    session.flush()
    on_disk = image_path_for("oracle-1", tmp_path)
    on_disk.parent.mkdir(parents=True, exist_ok=True)
    on_disk.write_bytes(b"already")

    client = FakeImageClient()
    service = CardImageService(session, client, images_dir=tmp_path)

    assert service.ensure_image("oracle-1") == on_disk
    assert client.downloaded == []


def test_ensure_image_downloads_missing_face(
    session: Session, tmp_path: Path
) -> None:
    session.add(
        Card(
            oracle_id="oracle-dfc",
            name="Delver of Secrets // Insectile Aberration",
            image_uri="https://example.test/front.jpg",
            image_uri_back="https://example.test/back.jpg",
            is_basic_land=False,
            is_token=False,
        )
    )
    session.flush()

    client = FakeImageClient()
    service = CardImageService(session, client, images_dir=tmp_path)

    assert service.has_back_image("oracle-dfc") is True
    back = service.ensure_image("oracle-dfc", back=True)

    assert back == image_path_for("oracle-dfc", tmp_path, back=True)
    assert back.is_file()
    assert client.downloaded[0][0] == "https://example.test/back.jpg"


def test_ensure_image_fetches_uri_when_card_has_none(
    session: Session, tmp_path: Path
) -> None:
    session.add(
        Card(
            oracle_id="oracle-2",
            name="Mana Crypt",
            image_uri=None,
            is_basic_land=False,
            is_token=False,
        )
    )
    session.flush()

    client = FakeImageClient(
        {
            "data": [
                {
                    "oracle_id": "oracle-2",
                    "name": "Mana Crypt",
                    "image_uris": {"normal": "https://example.test/crypt.jpg"},
                }
            ]
        }
    )
    service = CardImageService(session, client, images_dir=tmp_path)
    path = service.ensure_image("oracle-2")

    assert path is not None and path.is_file()
    assert client.collection_calls == [[{"oracle_id": "oracle-2"}]]
    assert session.get(Card, "oracle-2").image_uri == "https://example.test/crypt.jpg"


def test_ensure_image_returns_none_for_unknown_card(
    session: Session, tmp_path: Path
) -> None:
    service = CardImageService(session, FakeImageClient(), images_dir=tmp_path)

    assert service.ensure_image("missing") is None
    assert service.has_back_image("missing") is False


def test_printing_preview_downloads_the_normal_image(
    session: Session, tmp_path: Path
) -> None:
    session.add(
        Card(
            oracle_id="oracle-1",
            name="Sol Ring",
            is_basic_land=False,
            is_token=False,
        )
    )
    session.flush()
    session.add(
        CardPrinting(
            id="art-a",
            oracle_id="oracle-1",
            set_code="C21",
            collector_number="263",
            image_uri="https://cards.scryfall.io/small/front/a/b/art-a.jpg",
        )
    )
    session.flush()
    client = FakeImageClient()
    service = CardImageService(session, client, images_dir=tmp_path)

    path = service.ensure_printing_image("art-a")

    assert path is not None and path.is_file()
    assert client.downloaded[0][0] == preview_image_url(
        "https://cards.scryfall.io/small/front/a/b/art-a.jpg"
    )
    assert "/normal/" in client.downloaded[0][0]
    assert service.ensure_printing_image("missing") is None


def test_ensure_image_degrades_when_download_fails(
    session: Session, tmp_path: Path
) -> None:
    session.add(
        Card(
            oracle_id="oracle-3",
            name="Offline Card",
            image_uri="https://example.test/offline.jpg",
            is_basic_land=False,
            is_token=False,
        )
    )
    session.flush()

    class OfflineClient(FakeImageClient):
        def download_file(self, url: str, destination: Path) -> None:
            raise RuntimeError("network down")

    service = CardImageService(session, OfflineClient(), images_dir=tmp_path)

    assert service.ensure_image("oracle-3") is None
    assert not image_path_for("oracle-3", tmp_path).exists()
