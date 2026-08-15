from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

import pytest

from mtg_rebuilder.models import Base, Card, CardAssignment, CardCopy, Deck, DeckCard
from mtg_rebuilder.models.enums import DeckCardRole, DeckStatus
from mtg_rebuilder.services.deck_service import DeckService, InventoryService
from mtg_rebuilder.services.import_service import ImportService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db_session:
        yield db_session


def test_list_trackable_cards_excludes_basic_lands(session: Session) -> None:
    land = Card(
        oracle_id="forest",
        name="Forest",
        is_basic_land=True,
        is_token=False,
    )
    ring = Card(
        oracle_id="sol",
        name="Sol Ring",
        is_basic_land=False,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([land, ring, deck])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=deck.id,
                card_id="forest",
                quantity=10,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=deck.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
        ]
    )
    session.flush()

    cards = ImportService(session, scryfall=_FakeScryfall(session)).list_trackable_cards(
        deck.id
    )

    assert len(cards) == 1
    assert cards[0].name == "Sol Ring"
    assert cards[0].quantity == 1


def test_apply_available_copies_adds_unassigned_inventory(session: Session) -> None:
    card = Card(
        oracle_id="sol",
        name="Sol Ring",
        is_basic_land=False,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([card, deck])
    session.flush()

    added = ImportService(session, scryfall=_FakeScryfall(session)).apply_available_copies(
        {"sol": 2}
    )

    assert added == 2
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 2


def test_apply_available_copies_stacks_on_existing_free_inventory(
    session: Session,
) -> None:
    card = Card(
        oracle_id="banishing",
        name="Banishing Light",
        is_basic_land=False,
        is_token=False,
    )
    session.add(card)
    session.flush()
    importer = ImportService(session, scryfall=_FakeScryfall(session))
    importer.apply_available_copies({"banishing": 1})

    added = importer.apply_available_copies({"banishing": 1})

    assert added == 1
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 2
    assert (
        session.scalar(
            select(func.count())
            .select_from(CardCopy)
            .where(
                CardCopy.card_id == "banishing",
                CardCopy.id.not_in(select(CardAssignment.card_copy_id)),
            )
        )
        == 2
    )


def test_armed_import_assigns_copies_before_status_is_set(session: Session) -> None:
    scryfall = _FakeScryfall(session)
    importer = ImportService(session, scryfall)
    result = importer.import_moxfield_text(
        deck_name="Test",
        text="1 Sol Ring",
        status=DeckStatus.ARMED,
    )

    DeckService(session).set_status(result.deck, DeckStatus.ARMED)

    assert result.deck.status == DeckStatus.ARMED
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 1
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 1


def test_armed_import_creates_second_copy_when_first_is_assigned(
    session: Session,
) -> None:
    scryfall = _FakeScryfall(session)
    session.add(
        Card(
            oracle_id="sol",
            name="Sol Ring",
            is_basic_land=False,
            is_token=False,
        )
    )
    kellan = Deck(name="Kellan", status=DeckStatus.DISMANTLED)
    session.add(kellan)
    session.flush()
    session.add(
        DeckCard(
            deck_id=kellan.id,
            card_id="sol",
            quantity=1,
            role=DeckCardRole.MAIN,
        )
    )
    session.flush()
    DeckService(session).set_status(kellan, DeckStatus.ARMED)

    importer = ImportService(session, scryfall)
    result = importer.import_moxfield_text(
        deck_name="Athreos",
        text="1 Sol Ring",
        status=DeckStatus.ARMED,
    )
    DeckService(session).set_status(result.deck, DeckStatus.ARMED)

    assert (
        session.scalar(
            select(func.count())
            .select_from(CardCopy)
            .where(CardCopy.card_id == "sol")
        )
        == 2
    )
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 2


def test_preview_inventory_list_identifies_merges_and_skips_basics(
    session: Session,
) -> None:
    session.add_all(
        [
            Card(
                oracle_id="sol",
                name="Sol Ring",
                is_basic_land=False,
                is_token=False,
            ),
            Card(
                oracle_id="forest",
                name="Forest",
                is_basic_land=True,
                is_token=False,
            ),
            Card(
                oracle_id="token-angel",
                name="Angel",
                is_basic_land=False,
                is_token=True,
            ),
        ]
    )
    session.flush()
    scryfall = _StrictFakeScryfall(session)
    text = "\n".join(
        [
            "2 Sol Ring",
            "1 Sol Ring",
            "10 Forest",
            "Token: 1 Angel",
            "1 Completely Fake Card Name XYZ",
            "not a valid card line!!!",
            "// Creatures",
        ]
    )

    preview = ImportService(session, scryfall).preview_inventory_list(text)

    assert len(preview.identified) == 1
    assert preview.identified[0].name == "Sol Ring"
    assert preview.identified[0].list_quantity == 3
    assert "1 Completely Fake Card Name XYZ" in preview.unresolved_lines
    assert "not a valid card line!!!" in preview.unresolved_lines
    assert all("Forest" not in line for line in preview.unresolved_lines)
    assert all("Angel" not in line for line in preview.unresolved_lines)


def test_preview_inventory_list_empty_unresolved_when_all_resolve(
    session: Session,
) -> None:
    session.add(
        Card(
            oracle_id="sol",
            name="Sol Ring",
            is_basic_land=False,
            is_token=False,
        )
    )
    session.flush()

    preview = ImportService(session, _StrictFakeScryfall(session)).preview_inventory_list(
        "1 Sol Ring"
    )

    assert len(preview.identified) == 1
    assert preview.unresolved_lines == []


def test_preview_deck_list_update_reports_added_removed_and_unresolved(
    session: Session,
) -> None:
    _add_cards(session, [("sol", "Sol Ring"), ("terror", "Terror"), ("vihaan", "Vihaan")])
    deck = _add_deck(session, "Vihaan", [("sol", 1), ("terror", 1)])

    preview = ImportService(session, _StrictFakeScryfall(session)).preview_deck_list_update(
        deck.id,
        "\n".join(["1 Sol Ring", "1 Vihaan", "1 Nonexistent Card"]),
    )

    assert [(change.name, change.before, change.after) for change in preview.added] == [
        ("Vihaan", 0, 1)
    ]
    assert [
        (change.name, change.before, change.after) for change in preview.removed
    ] == [("Terror", 1, 0)]
    assert preview.total_before == 2
    assert preview.total_after == 2
    assert preview.unresolved_lines == ["1 Nonexistent Card"]
    assert preview.has_changes


def test_preview_deck_list_update_reports_quantity_changes(session: Session) -> None:
    _add_cards(session, [("swamp", "Swamp")])
    deck = _add_deck(session, "Vihaan", [("swamp", 6)])

    preview = ImportService(session, _StrictFakeScryfall(session)).preview_deck_list_update(
        deck.id, "7 Swamp"
    )

    assert [(change.before, change.after, change.delta) for change in preview.added] == [
        (6, 7, 1)
    ]
    assert preview.removed == []


def test_preview_deck_list_update_builds_edit_rows_with_inventory(
    session: Session,
) -> None:
    _add_cards(session, [("sol", "Sol Ring"), ("terror", "Terror"), ("vihaan", "Vihaan")])
    deck = _add_deck(session, "Vihaan", [("sol", 1), ("terror", 1)])
    InventoryService(session).add_copy("sol", 2, record_activity=False)

    preview = ImportService(
        session, _StrictFakeScryfall(session)
    ).preview_deck_list_update(
        deck.id,
        "\n".join(["1 Sol Ring", "1 Vihaan"]),
        commander_name="Vihaan",
    )

    by_id = {row.oracle_id: row for row in preview.edit_rows}
    assert set(by_id) == {"sol", "vihaan"}
    assert by_id["sol"].quantity == 1
    assert by_id["sol"].free_copies == 2
    assert by_id["vihaan"].role == DeckCardRole.COMMANDER
    assert by_id["vihaan"].free_copies == 0


def test_preview_deck_list_update_without_changes(session: Session) -> None:
    _add_cards(session, [("sol", "Sol Ring")])
    deck = _add_deck(session, "Vihaan", [("sol", 1)])

    preview = ImportService(session, _StrictFakeScryfall(session)).preview_deck_list_update(
        deck.id, "1 Sol Ring"
    )

    assert not preview.has_changes


def test_replace_deck_list_swaps_cards_and_promotes_commander(session: Session) -> None:
    _add_cards(session, [("sol", "Sol Ring"), ("terror", "Terror"), ("vihaan", "Vihaan")])
    deck = _add_deck(session, "Vihaan", [("sol", 1), ("terror", 1)])

    warnings = ImportService(session, _StrictFakeScryfall(session)).replace_deck_list(
        deck.id,
        "\n".join(["1 Sol Ring", "1 Vihaan"]),
        commander_name="Vihaan",
    )

    assert warnings == []
    rows = {
        (row.card_id, row.role): row.quantity
        for row in session.scalars(
            select(DeckCard).where(DeckCard.deck_id == deck.id)
        ).all()
    }
    assert rows == {
        ("sol", DeckCardRole.MAIN): 1,
        ("vihaan", DeckCardRole.COMMANDER): 1,
    }


def test_replace_deck_list_keeps_armed_deck_assigned(session: Session) -> None:
    _add_cards(session, [("sol", "Sol Ring"), ("terror", "Terror")])
    deck = _add_deck(session, "Vihaan", [("sol", 1)])
    DeckService(session).set_status(deck, DeckStatus.ARMED)

    ImportService(session, _StrictFakeScryfall(session)).replace_deck_list(
        deck.id, "\n".join(["1 Sol Ring", "1 Terror"])
    )

    assert deck.status == DeckStatus.ARMED
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 2
    assert (
        session.scalar(
            select(func.count())
            .select_from(CardCopy)
            .where(CardCopy.card_id == "terror")
        )
        == 1
    )


def _add_cards(session: Session, cards: list[tuple[str, str]]) -> None:
    session.add_all(
        [
            Card(oracle_id=oracle_id, name=name, is_basic_land=False, is_token=False)
            for oracle_id, name in cards
        ]
    )
    session.flush()


def _add_deck(session: Session, name: str, cards: list[tuple[str, int]]) -> Deck:
    deck = Deck(name=name, status=DeckStatus.DISMANTLED)
    session.add(deck)
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=deck.id,
                card_id=oracle_id,
                quantity=quantity,
                role=DeckCardRole.MAIN,
            )
            for oracle_id, quantity in cards
        ]
    )
    session.flush()
    return deck


class _FakeScryfall:
    def __init__(self, session: Session) -> None:
        self._session = session

    def fetch_and_cache(self, name: str, *, prefer_token: bool = False) -> Card:
        card = self._session.scalar(select(Card).where(Card.name == name))
        if card is None:
            card = Card(
                oracle_id="sol",
                name="Sol Ring",
                is_basic_land=False,
                is_token=False,
            )
            self._session.add(card)
            self._session.flush()
        return card

    def lookup_local(self, name: str, *, prefer_token: bool = False) -> Card | None:
        return self._session.scalar(select(Card).where(Card.name == name))

    def close(self) -> None:
        return None


class _StrictFakeScryfall(_FakeScryfall):
    def fetch_and_cache(self, name: str, *, prefer_token: bool = False) -> Card:
        card = self._session.scalar(select(Card).where(Card.name == name))
        if card is None:
            raise LookupError(f"Card '{name}' not found")
        return card
