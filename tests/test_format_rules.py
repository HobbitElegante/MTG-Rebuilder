"""Format tag profiles and DeckService rule dispatch."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import pytest

from mtg_rebuilder.algorithms.commander_rules import (
    COMMANDER_DECK_SIZE,
    CommanderCard,
    CommanderRuleKind,
    ROLE_COMMANDER,
    ROLE_MAIN,
)
from mtg_rebuilder.algorithms.format_rules import profile_for
from mtg_rebuilder.database.migrate import upgrade_database
from mtg_rebuilder.models import Base, Card, Deck, DeckCard
from mtg_rebuilder.models.enums import DeckCardRole, DeckFormat, DeckStatus
from mtg_rebuilder.services.deck_service import DeckEditLine, DeckService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session


def test_profile_for_commander_has_target_and_rules() -> None:
    profile = profile_for(DeckFormat.COMMANDER)
    assert profile.target_size == COMMANDER_DECK_SIZE
    cards = [
        CommanderCard(
            oracle_id="cmd",
            name="Commander",
            role=ROLE_COMMANDER,
            color_identity="B",
            oracle_text=None,
            type_line="Legendary Creature",
            quantity=1,
            is_basic_land=False,
        ),
        CommanderCard(
            oracle_id="a",
            name="Spell",
            role=ROLE_MAIN,
            color_identity="B",
            oracle_text=None,
            type_line="Sorcery",
            quantity=50,
            is_basic_land=False,
        ),
    ]
    kinds = {issue.kind for issue in profile.evaluate(cards)}
    assert CommanderRuleKind.DECK_SIZE in kinds


def test_profile_for_other_has_no_rules_yet() -> None:
    profile = profile_for(DeckFormat.OTHER)
    assert profile.target_size is None
    cards = [
        CommanderCard(
            oracle_id="cmd",
            name="Commander",
            role=ROLE_COMMANDER,
            color_identity="B",
            oracle_text=None,
            type_line="Legendary Creature",
            quantity=1,
            is_basic_land=False,
        ),
        CommanderCard(
            oracle_id="a",
            name="Spell",
            role=ROLE_MAIN,
            color_identity="B",
            oracle_text=None,
            type_line="Sorcery",
            quantity=50,
            is_basic_land=False,
        ),
    ]
    assert profile.evaluate(cards) == []


def test_new_deck_defaults_to_commander_format(session: Session) -> None:
    deck = Deck(name="Default", status=DeckStatus.DISMANTLED)
    session.add(deck)
    session.flush()
    assert deck.format is DeckFormat.COMMANDER


def test_set_format_persists(session: Session) -> None:
    deck = Deck(name="Tagged", status=DeckStatus.DISMANTLED)
    session.add(deck)
    session.flush()
    DeckService(session).set_format(deck.id, DeckFormat.OTHER)
    session.refresh(deck)
    assert deck.format is DeckFormat.OTHER


def test_rule_issues_empty_for_other_format_even_when_undersized(
    session: Session,
) -> None:
    session.add(
        Card(
            oracle_id="ghen",
            name="Ghen, Arcanum Weaver",
            is_basic_land=False,
            is_token=False,
            color_identity="WBR",
            type_line="Legendary Creature — Human Shaman",
        )
    )
    deck = Deck(
        name="Short other",
        status=DeckStatus.DISMANTLED,
        format=DeckFormat.OTHER,
    )
    session.add(deck)
    session.flush()
    session.add(
        DeckCard(
            deck_id=deck.id,
            card_id="ghen",
            quantity=1,
            role=DeckCardRole.COMMANDER,
        )
    )
    session.flush()

    service = DeckService(session)
    assert service.commander_rule_issues(deck.id) == []
    assert service.rule_issues(deck.id) == []


def test_apply_deck_edit_can_grow_list_past_original_size(session: Session) -> None:
    session.add_all(
        [
            Card(
                oracle_id="cmd",
                name="Commander",
                is_basic_land=False,
                is_token=False,
            ),
            Card(
                oracle_id="land",
                name="Swamp",
                is_basic_land=True,
                is_token=False,
            ),
        ]
    )
    deck = Deck(name="Grow", status=DeckStatus.DISMANTLED)
    session.add(deck)
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

    DeckService(session).apply_deck_edit(
        deck.id,
        [
            DeckEditLine(
                oracle_id="cmd",
                quantity=1,
                role=DeckCardRole.COMMANDER,
            ),
            DeckEditLine(
                oracle_id="land",
                quantity=40,
                role=DeckCardRole.MAIN,
            ),
        ],
    )
    rows = DeckService(session).deck_edit_rows(deck.id)
    assert sum(row.quantity for row in rows) == 41


def test_migration_adds_format_default_commander(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'format.db'}")
    upgrade_database(engine)
    with engine.begin() as conn:
        columns = {
            row[1]: row
            for row in conn.execute(text("PRAGMA table_info(decks)")).fetchall()
        }
        assert "format" in columns
        conn.execute(
            text(
                "INSERT INTO decks (name, status, sort_order, is_locked) "
                "VALUES ('Legacy', 'DISMANTLED', 0, 0)"
            )
        )
        fmt = conn.execute(
            text("SELECT format FROM decks WHERE name = 'Legacy'")
        ).scalar()
    assert fmt == "COMMANDER"
