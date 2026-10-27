from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

import pytest

from mtg_rebuilder.models import Base, Card, CardAssignment, CardCopy, Deck, DeckCard
from mtg_rebuilder.models.enums import DeckCardRole, DeckStatus
from mtg_rebuilder.services.deck_service import (
    CardListStock,
    DeckService,
    FreeCoverage,
    InventoryService,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session


def test_armed_deck_creates_assignments_from_list(session: Session) -> None:
    card = Card(
        oracle_id="sol",
        name="Sol Ring",
        is_basic_land=False,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([card, deck])
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="sol",
            quantity=2,
            role=DeckCardRole.MAIN,
        )
    )
    session.flush()

    DeckService(session).set_status(deck, DeckStatus.ARMED)

    assert deck.status == DeckStatus.ARMED
    assert (
        session.scalar(select(func.count()).select_from(CardAssignment)) == 2
    )
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 2


def test_armed_deck_uses_free_inventory_before_creating_copies(
    session: Session,
) -> None:
    card = Card(
        oracle_id="sol",
        name="Sol Ring",
        is_basic_land=False,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([card, deck])
    session.flush()
    InventoryService(session).add_copy("sol", quantity=1)
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="sol",
            quantity=1,
            role=DeckCardRole.MAIN,
        )
    )
    session.flush()

    DeckService(session).set_status(deck, DeckStatus.ARMED)

    assert session.scalar(select(func.count()).select_from(CardCopy)) == 1
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 1


def test_dismantled_deck_releases_assignments(session: Session) -> None:
    card = Card(
        oracle_id="sol",
        name="Sol Ring",
        is_basic_land=False,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([card, deck])
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="sol",
            quantity=1,
            role=DeckCardRole.MAIN,
        )
    )
    session.flush()

    service = DeckService(session)
    service.set_status(deck, DeckStatus.ARMED)
    service.set_status(deck, DeckStatus.DISMANTLED)

    assert deck.status == DeckStatus.DISMANTLED
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 0
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 1
    assert InventoryService(session).free_counts() == {"sol": 1}


def test_armed_deck_skips_basic_lands(session: Session) -> None:
    land = Card(
        oracle_id="forest",
        name="Forest",
        is_basic_land=True,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([land, deck])
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="forest",
            quantity=10,
            role=DeckCardRole.MAIN,
        )
    )
    session.flush()

    DeckService(session).set_status(deck, DeckStatus.ARMED)

    assert session.scalar(select(func.count()).select_from(CardCopy)) == 0
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 0


def test_delete_deck_removes_list_and_frees_assigned_copies(session: Session) -> None:
    card = Card(
        oracle_id="sol",
        name="Sol Ring",
        is_basic_land=False,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([card, deck])
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="sol",
            quantity=1,
            role=DeckCardRole.MAIN,
        )
    )
    session.flush()

    service = DeckService(session)
    service.set_status(deck, DeckStatus.ARMED)
    deck_id = deck.id

    assert service.delete_deck(deck_id) is True

    assert session.get(Deck, deck_id) is None
    assert session.scalar(select(func.count()).select_from(DeckCard)) == 0
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 0
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 1
    assert InventoryService(session).free_counts() == {"sol": 1}


def test_delete_deck_can_remove_selected_copies(session: Session) -> None:
    card = Card(
        oracle_id="sol",
        name="Sol Ring",
        is_basic_land=False,
        is_token=False,
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    other = Deck(name="Other", status=DeckStatus.ARMED)
    session.add_all([card, deck, other])
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="sol",
            quantity=1,
            role=DeckCardRole.MAIN,
        )
    )
    free_copy = CardCopy(card_id="sol")
    other_copy = CardCopy(card_id="sol")
    session.add_all([free_copy, other_copy])
    session.flush()
    session.add(CardAssignment(card_copy_id=other_copy.id, deck_id=other.id))
    session.flush()

    service = DeckService(session)
    impact = {item.oracle_id: item for item in service.deck_delete_impact(deck.id)}
    assert impact["sol"].total_copies == 2
    assert impact["sol"].removable_copies == 1

    assert service.delete_deck(deck.id, {"sol": 1}) is True

    assert session.scalar(select(func.count()).select_from(CardCopy)) == 1
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 1
    assert InventoryService(session).free_counts() == {}


def test_apply_deck_edit_replace_keeps_outgoing_copies_and_creates_free(
    session: Session,
) -> None:
    from mtg_rebuilder.services.deck_service import DeckEditLine

    old = Card(oracle_id="old", name="Old Card", is_basic_land=False, is_token=False)
    new = Card(oracle_id="new", name="New Card", is_basic_land=False, is_token=False)
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([old, new, deck])
    session.flush()
    session.add(
        DeckCard(deck_id=deck.id, card_id="old", quantity=1, role=DeckCardRole.MAIN)
    )
    session.add(CardCopy(card_id="old"))
    session.flush()

    DeckService(session).apply_deck_edit(
        deck.id,
        [DeckEditLine(oracle_id="new", quantity=1, role=DeckCardRole.MAIN)],
        create_free_copies={"new": 1},
    )

    assert session.scalar(select(func.count()).select_from(DeckCard)) == 1
    assert session.scalar(select(DeckCard.card_id)) == "new"
    free = InventoryService(session).free_counts()
    assert free.get("old") == 1
    assert free.get("new") == 1


def test_apply_deck_edit_replace_can_remove_outgoing_copies(session: Session) -> None:
    from mtg_rebuilder.services.deck_service import DeckEditLine

    old = Card(oracle_id="old", name="Old Card", is_basic_land=False, is_token=False)
    new = Card(oracle_id="new", name="New Card", is_basic_land=False, is_token=False)
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([old, new, deck])
    session.flush()
    session.add(
        DeckCard(deck_id=deck.id, card_id="old", quantity=1, role=DeckCardRole.MAIN)
    )
    session.add(CardCopy(card_id="old"))
    session.flush()

    DeckService(session).apply_deck_edit(
        deck.id,
        [DeckEditLine(oracle_id="new", quantity=1, role=DeckCardRole.MAIN)],
        remove_copies={"old": 1},
    )

    assert InventoryService(session).free_counts() == {}
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 0


def test_apply_deck_edit_armed_roundtrip(session: Session) -> None:
    from mtg_rebuilder.services.deck_service import DeckEditLine

    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    signet = Card(
        oracle_id="signet", name="Arcane Signet", is_basic_land=False, is_token=False
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED)
    session.add_all([sol, signet, deck])
    session.flush()
    session.add(
        DeckCard(deck_id=deck.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN)
    )
    session.flush()

    service = DeckService(session)
    service.set_status(deck, DeckStatus.ARMED)
    service.apply_deck_edit(
        deck.id,
        [DeckEditLine(oracle_id="signet", quantity=1, role=DeckCardRole.MAIN)],
        create_free_copies={"signet": 1},
    )

    assert deck.status == DeckStatus.ARMED
    assert session.scalar(select(func.count()).select_from(CardAssignment)) == 1
    assigned = session.scalar(
        select(CardCopy.card_id)
        .join(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
        .where(CardAssignment.deck_id == deck.id)
    )
    assert assigned == "signet"
    assert InventoryService(session).free_counts().get("sol") == 1


def test_free_coverage_toward_deck_counts_matching_free_copies(
    session: Session,
) -> None:
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    cultivate = Card(
        oracle_id="cultivate",
        name="Cultivate",
        is_basic_land=False,
        is_token=False,
    )
    forest = Card(
        oracle_id="forest",
        name="Forest",
        is_basic_land=True,
        is_token=False,
    )
    deck = Deck(name="Target", status=DeckStatus.DISMANTLED)
    session.add_all([sol, cultivate, forest, deck])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=deck.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
            DeckCard(
                deck_id=deck.id,
                card_id="cultivate",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=deck.id, card_id="forest", quantity=10, role=DeckCardRole.MAIN
            ),
            CardCopy(card_id="sol"),
            CardCopy(card_id="sol"),
        ]
    )
    session.flush()

    assert DeckService(session).free_coverage_toward_deck(deck.id) == FreeCoverage(
        covered=1, required=2
    )


def test_set_total_copies_adds_and_removes_free_inventory(session: Session) -> None:
    session.add(
        Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    )
    session.flush()
    inventory = InventoryService(session)
    inventory.add_copy("sol", 2)

    inventory.set_total_copies("sol", 5)
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 5
    assert inventory.free_counts() == {"sol": 5}

    inventory.set_total_copies("sol", 1)
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 1
    assert inventory.free_counts() == {"sol": 1}


def test_set_total_copies_cannot_go_below_assigned(session: Session) -> None:
    card = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    deck = Deck(name="Armed", status=DeckStatus.ARMED)
    session.add_all([card, deck])
    session.flush()
    copies = [CardCopy(card_id="sol"), CardCopy(card_id="sol"), CardCopy(card_id="sol")]
    session.add_all(copies)
    session.flush()
    session.add(CardAssignment(card_copy_id=copies[0].id, deck_id=deck.id))
    session.flush()

    with pytest.raises(ValueError, match="assigned"):
        InventoryService(session).set_total_copies("sol", 0)

    InventoryService(session).set_total_copies("sol", 1)
    assert session.scalar(select(func.count()).select_from(CardCopy)) == 1
    assert InventoryService(session).free_counts() == {}


def test_rename_deck(session: Session) -> None:
    deck = Deck(name="Old", status=DeckStatus.DISMANTLED, sort_order=0)
    session.add(deck)
    session.flush()

    DeckService(session).rename_deck(deck.id, "  New Name  ")
    assert deck.name == "New Name"

    with pytest.raises(ValueError, match="empty"):
        DeckService(session).rename_deck(deck.id, "   ")


def test_set_commander_promotes_and_demotes(session: Session) -> None:
    athreos = Card(
        oracle_id="ath", name="Athreos", is_basic_land=False, is_token=False
    )
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED, sort_order=0)
    session.add_all([athreos, sol, deck])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=deck.id,
                card_id="ath",
                quantity=1,
                role=DeckCardRole.COMMANDER,
            ),
            DeckCard(
                deck_id=deck.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
        ]
    )
    session.flush()

    service = DeckService(session)
    assert service.commander_name(deck.id) == "Athreos"

    service.set_commander(deck.id, "sol")
    assert service.commander_name(deck.id) == "Sol Ring"
    roles = {
        (card.card_id, card.role)
        for card in session.scalars(
            select(DeckCard).where(DeckCard.deck_id == deck.id)
        ).all()
    }
    assert ("sol", DeckCardRole.COMMANDER) in roles
    assert ("ath", DeckCardRole.MAIN) in roles

    service.set_commander(deck.id, None)
    assert service.commander_name(deck.id) is None


def test_set_commander_adds_missing_card(session: Session) -> None:
    commander = Card(
        oracle_id="cmd", name="Kellan", is_basic_land=False, is_token=False
    )
    deck = Deck(name="Test", status=DeckStatus.DISMANTLED, sort_order=0)
    session.add_all([commander, deck])
    session.flush()

    DeckService(session).set_commander(deck.id, "cmd")
    assert DeckService(session).commander_name(deck.id) == "Kellan"
    entry = session.scalar(
        select(DeckCard).where(
            DeckCard.deck_id == deck.id,
            DeckCard.role == DeckCardRole.COMMANDER,
        )
    )
    assert entry is not None
    assert entry.quantity == 1


def test_set_secondary_command_zone_partner(session: Session) -> None:
    commander = Card(
        oracle_id="cmd", name="Kellan", is_basic_land=False, is_token=False
    )
    partner = Card(
        oracle_id="prt", name="Rograkh", is_basic_land=False, is_token=False
    )
    background = Card(
        oracle_id="bg", name="Folk Hero", is_basic_land=False, is_token=False
    )
    deck = Deck(name="Partners", status=DeckStatus.DISMANTLED, sort_order=0)
    session.add_all([commander, partner, background, deck])
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="cmd",
            quantity=1,
            role=DeckCardRole.COMMANDER,
        )
    )
    session.flush()

    service = DeckService(session)
    service.set_secondary_command_zone(deck.id, DeckCardRole.PARTNER, "prt")
    assert service.secondary_command_zone(deck.id) == (
        DeckCardRole.PARTNER,
        "Rograkh",
    )

    service.set_secondary_command_zone(deck.id, DeckCardRole.BACKGROUND, "bg")
    assert service.secondary_command_zone(deck.id) == (
        DeckCardRole.BACKGROUND,
        "Folk Hero",
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(DeckCard)
            .where(
                DeckCard.deck_id == deck.id,
                DeckCard.role == DeckCardRole.PARTNER,
            )
        )
        == 0
    )

    service.set_secondary_command_zone(deck.id, None, None)
    assert service.secondary_command_zone(deck.id) is None


def test_command_zone_cards_lists_commander_first(session: Session) -> None:
    commander = Card(
        oracle_id="cmd", name="Ishai", is_basic_land=False, is_token=False
    )
    partner = Card(
        oracle_id="prt", name="Rograkh", is_basic_land=False, is_token=False
    )
    filler = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    deck = Deck(name="Partners", status=DeckStatus.DISMANTLED, sort_order=0)
    session.add_all([commander, partner, filler, deck])
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
        )
    )
    session.flush()

    service = DeckService(session)
    assert service.command_zone_cards(deck.id) == []

    service.set_commander(deck.id, "cmd")
    service.set_secondary_command_zone(deck.id, DeckCardRole.PARTNER, "prt")

    assert service.command_zone_cards(deck.id) == [
        ("cmd", "Ishai"),
        ("prt", "Rograkh"),
    ]


def test_list_decks_filter_and_move(session: Session) -> None:
    a = Deck(name="Alpha", status=DeckStatus.ARMED, sort_order=0)
    b = Deck(name="Bravo", status=DeckStatus.DISMANTLED, sort_order=1)
    c = Deck(name="Charlie", status=DeckStatus.ARMED, sort_order=2)
    session.add_all([a, b, c])
    session.flush()

    service = DeckService(session)
    assert [d.name for d in service.list_decks()] == ["Alpha", "Bravo", "Charlie"]
    assert [d.name for d in service.list_decks(status=DeckStatus.ARMED)] == [
        "Alpha",
        "Charlie",
    ]

    assert service.move_deck(c.id, direction=-1, status=DeckStatus.ARMED) is True
    assert [d.name for d in service.list_decks(status=DeckStatus.ARMED)] == [
        "Charlie",
        "Alpha",
    ]
    assert [d.name for d in service.list_decks()] == ["Charlie", "Bravo", "Alpha"]

    assert service.move_deck(c.id, direction=-1, status=DeckStatus.ARMED) is False


def test_deck_card_summaries_orders_command_zone_first(session: Session) -> None:
    commander = Card(
        oracle_id="cmd", name="Kellan", is_basic_land=False, is_token=False
    )
    partner = Card(
        oracle_id="prt", name="Rograkh", is_basic_land=False, is_token=False
    )
    main_b = Card(
        oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False
    )
    main_a = Card(
        oracle_id="arc", name="Arcane Signet", is_basic_land=False, is_token=False
    )
    token = Card(
        oracle_id="tok", name="Treasure", is_basic_land=False, is_token=True
    )
    deck = Deck(name="Summaries", status=DeckStatus.DISMANTLED, sort_order=0)
    session.add_all([commander, partner, main_a, main_b, token, deck])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=deck.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=deck.id,
                card_id="arc",
                quantity=2,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=deck.id,
                card_id="cmd",
                quantity=1,
                role=DeckCardRole.COMMANDER,
            ),
            DeckCard(
                deck_id=deck.id,
                card_id="prt",
                quantity=1,
                role=DeckCardRole.PARTNER,
            ),
            DeckCard(
                deck_id=deck.id,
                card_id="tok",
                quantity=1,
                role=DeckCardRole.TOKEN,
            ),
        ]
    )
    session.flush()

    summaries = DeckService(session).deck_card_summaries(deck.id)
    assert [row.oracle_id for row in summaries] == ["cmd", "prt", "arc", "sol"]
    assert summaries[2].quantity == 2
    assert all(row.role != DeckCardRole.TOKEN for row in summaries)


def test_card_list_stock_counts_copies_and_lists(session: Session) -> None:
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    forest = Card(
        oracle_id="forest", name="Forest", is_basic_land=True, is_token=False
    )
    armed = Deck(name="Armed", status=DeckStatus.DISMANTLED, sort_order=0)
    other = Deck(name="Other", status=DeckStatus.DISMANTLED, sort_order=1)
    session.add_all([sol, forest, armed, other])
    session.flush()
    InventoryService(session).add_copy("sol", quantity=3)
    session.add_all(
        [
            DeckCard(
                deck_id=armed.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=armed.id,
                card_id="forest",
                quantity=10,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=other.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            # Same card, second role: still one list.
            DeckCard(
                deck_id=other.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.COMMANDER,
            ),
        ]
    )
    session.flush()

    service = DeckService(session)
    service.set_status(armed, DeckStatus.ARMED)
    stock = service.card_list_stock(["sol", "forest", "missing"])

    assert stock["sol"] == CardListStock(
        total_copies=3, free_copies=2, decks_using=2
    )
    assert stock["forest"] == CardListStock(
        total_copies=0, free_copies=0, decks_using=1
    )
    assert stock["missing"] == CardListStock(
        total_copies=0, free_copies=0, decks_using=0
    )
    assert service.card_list_stock([]) == {}
    forest_row = next(
        row
        for row in service.deck_card_summaries(armed.id)
        if row.oracle_id == "forest"
    )
    assert forest_row.is_basic_land is True
