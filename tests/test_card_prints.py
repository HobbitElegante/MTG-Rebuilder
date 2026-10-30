import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from mtg_rebuilder.models import Base, Card, CardPrint, CardPrinting
from mtg_rebuilder.services.scryfall_service import (
    ScryfallService,
    printings_from_scryfall,
    prints_from_scryfall,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db_session:
        db_session.add(
            Card(
                oracle_id="sol",
                name="Sol Ring",
                is_basic_land=False,
                is_token=False,
            )
        )
        db_session.flush()
        yield db_session


class _FakePrintsClient:
    def __init__(self, payloads: list[dict] | None = None, fail: bool = False) -> None:
        self.payloads = payloads or []
        self.fail = fail
        self.calls = 0

    def fetch_card_prints(self, oracle_id: str) -> list[dict]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("offline")
        return self.payloads

    def close(self) -> None:
        return None


def test_prints_from_scryfall_dedupes_by_set_and_sorts_by_release() -> None:
    rows = prints_from_scryfall(
        [
            {
                "set": "c21",
                "set_name": "Commander 2021",
                "released_at": "2021-04-23",
                "rarity": "rare",
            },
            {
                "set": "c21",
                "set_name": "Commander 2021",
                "released_at": "2021-04-23",
                "rarity": "rare",
            },
            {
                "set": "ltr",
                "set_name": "The Lord of the Rings",
                "released_at": "2023-06-23",
                "rarity": "mythic",
            },
            {"set_name": "No code"},
        ]
    )

    assert rows == [
        ("C21", "Commander 2021", "2021-04-23", "rare"),
        ("LTR", "The Lord of the Rings", "2023-06-23", "mythic"),
    ]


def test_list_prints_caches_after_first_lookup(session: Session) -> None:
    client = _FakePrintsClient(
        [
            {
                "set": "c21",
                "set_name": "Commander 2021",
                "released_at": "2021-04-23",
                "rarity": "uncommon",
            },
            {
                "set": "ltr",
                "set_name": "The Lord of the Rings",
                "released_at": "2023-06-23",
                "rarity": "rare",
            },
        ]
    )
    service = ScryfallService(session, client=client)

    first = service.list_prints("sol")
    second = service.list_prints("sol")

    assert first == [("C21", "Commander 2021"), ("LTR", "The Lord of the Rings")]
    assert second == first
    assert client.calls == 1
    assert session.query(CardPrint).count() == 2
    rarities = {
        row.set_code: row.rarity for row in session.query(CardPrint).all()
    }
    assert rarities == {"C21": "uncommon", "LTR": "rare"}


def test_list_prints_falls_back_to_cache_when_offline(session: Session) -> None:
    session.add(CardPrint(oracle_id="sol", set_code="C21", set_name="Commander 2021"))
    session.flush()
    client = _FakePrintsClient(fail=True)

    prints = ScryfallService(session, client=client).list_prints("sol", refresh=True)

    assert prints == [("C21", "Commander 2021")]


def test_two_arts_in_one_set_stay_one_card_print(session: Session) -> None:
    payloads = [
        {
            "id": "art-a",
            "set": "c21",
            "set_name": "Commander 2021",
            "collector_number": "263",
            "illustration_id": "ill-a",
            "released_at": "2021-04-23",
            "rarity": "uncommon",
        },
        {
            "id": "art-b",
            "set": "c21",
            "set_name": "Commander 2021",
            "collector_number": "264",
            "illustration_id": "ill-b",
            "frame_effects": ["borderless"],
            "released_at": "2021-04-23",
            "rarity": "uncommon",
        },
    ]
    collapsed = prints_from_scryfall(payloads)
    assert [row[0] for row in collapsed] == ["C21"]

    client = _FakePrintsClient(payloads)
    service = ScryfallService(session, client=client)
    assert service.list_prints("sol") == [("C21", "Commander 2021")]
    arts = service.list_printings("sol")

    assert session.query(CardPrint).count() == 1
    assert session.query(CardPrinting).count() == 2
    assert arts == [
        ("art-a", "C21", "263", "263", None),
        ("art-b", "C21", "264", "264 · borderless", None),
    ]
    assert printings_from_scryfall(payloads)[1][3] == "ill-b"


def test_printings_keep_the_small_image() -> None:
    rows = printings_from_scryfall(
        [
            {
                "id": "art-a",
                "set": "c21",
                "collector_number": "263",
                "image_uris": {
                    "small": "https://example.test/small.jpg",
                    "normal": "https://example.test/normal.jpg",
                },
            },
            {
                "id": "art-face",
                "set": "c21",
                "collector_number": "264",
                "card_faces": [
                    {"image_uris": {"small": "https://example.test/face.jpg"}},
                ],
            },
        ]
    )

    assert rows[0][5] == "https://example.test/small.jpg"
    assert rows[1][5] == "https://example.test/face.jpg"


def test_list_prints_offline_without_cache_returns_empty(session: Session) -> None:
    prints = ScryfallService(session, client=_FakePrintsClient(fail=True)).list_prints("sol")

    assert prints == []
