from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic.script import ScriptDirectory

from mtg_rebuilder.database.migrate import (
    BASELINE_REVISION,
    alembic_config,
    upgrade_database,
)


def _script_head() -> str:
    """Newest revision on disk, so adding migrations doesn't break the tests."""
    return ScriptDirectory.from_config(alembic_config("sqlite://")).get_current_head()


@pytest.fixture
def legacy_engine(tmp_path: Path):
    """A pre-Alembic cards table (missing image_uri_back / commander_legality)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE cards ("
                "oracle_id VARCHAR(36) PRIMARY KEY, "
                "name VARCHAR(255), "
                "image_uri VARCHAR(512))"
            )
        )
        conn.execute(
            text("INSERT INTO cards (oracle_id, name) VALUES ('a', 'Sol Ring')")
        )
        conn.execute(
            text(
                "CREATE TABLE decks ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL, "
                "status VARCHAR(10) NOT NULL)"
            )
        )
        conn.execute(
            text("INSERT INTO decks (id, name, status) VALUES (1, 'Beta', 'DISMANTLED')")
        )
        conn.execute(
            text("INSERT INTO decks (id, name, status) VALUES (2, 'Alpha', 'ARMED')")
        )
        conn.execute(
            text(
                "CREATE TABLE card_copies ("
                "id INTEGER PRIMARY KEY, "
                "card_id VARCHAR(36) NOT NULL, "
                "edition VARCHAR(16), language VARCHAR(8), "
                "foil BOOLEAN NOT NULL, condition VARCHAR(32), location VARCHAR(128))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE deck_cards ("
                "id INTEGER PRIMARY KEY, "
                "deck_id INTEGER NOT NULL, "
                "card_id VARCHAR(36) NOT NULL, "
                "quantity INTEGER NOT NULL, "
                "role VARCHAR(10) NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE card_assignments ("
                "id INTEGER PRIMARY KEY, "
                "card_copy_id INTEGER NOT NULL, "
                "deck_id INTEGER NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO card_copies (id, card_id, foil) VALUES (1, 'a', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO card_copies (id, card_id, foil) VALUES (2, 'a', 0)"
            )
        )
    return engine


def _card_columns(engine) -> set[str]:
    with engine.begin() as conn:
        return {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(cards)")).fetchall()
        }


def _copy_columns(engine) -> set[str]:
    with engine.begin() as conn:
        return {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(card_copies)")).fetchall()
        }


def _deck_columns(engine) -> set[str]:
    with engine.begin() as conn:
        return {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(decks)")).fetchall()
        }


def _index_names(engine, table: str) -> set[str]:
    with engine.begin() as conn:
        return {
            row[1]
            for row in conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
        }


def _alembic_version(engine) -> str | None:
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "alembic_version" not in tables:
            return None
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_fresh_database_runs_initial_migration(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")

    upgrade_database(engine)

    tables = set(inspect(engine).get_table_names())
    assert "cards" in tables
    assert "decks" in tables
    assert "alembic_version" in tables
    assert _alembic_version(engine) == _script_head()
    assert "image_uri_back" in _card_columns(engine)
    assert "commander_legality" in _card_columns(engine)
    assert "sort_order" in _deck_columns(engine)
    assert "format" in _deck_columns(engine)
    assert "ix_card_copies_card_id" in _index_names(engine, "card_copies")
    assert {"finish", "collector_number", "printing_id", "updated_at"} <= _copy_columns(
        engine
    )
    assert "card_printings" in tables
    assert "image_uri" in {
        col["name"] for col in inspect(engine).get_columns("card_printings")
    }
    assert not any("oracle" in name for name in _index_names(engine, "card_printings"))
    assert not any(
        token in name
        for name in _index_names(engine, "card_copies")
        for token in ("finish", "collector", "printing")
    )
    assert "ix_deck_cards_card_id" in _index_names(engine, "deck_cards")
    assert "ix_card_assignments_deck_id" in _index_names(engine, "card_assignments")
    assert {"ix_decks_status", "ix_decks_sort_order"} <= _index_names(engine, "decks")


def test_legacy_database_is_bridged_and_stamped(legacy_engine) -> None:
    upgrade_database(legacy_engine)

    assert "image_uri_back" in _card_columns(legacy_engine)
    assert "commander_legality" in _card_columns(legacy_engine)
    assert "sort_order" in _deck_columns(legacy_engine)
    assert _alembic_version(legacy_engine) == _script_head()

    with legacy_engine.begin() as conn:
        row = conn.execute(
            text("SELECT name, image_uri_back, commander_legality FROM cards WHERE oracle_id = 'a'")
        ).first()
        assert row == ("Sol Ring", None, None)
        orders = {
            name: order
            for name, order in conn.execute(
                text("SELECT name, sort_order FROM decks")
            ).fetchall()
        }
    # Bridged sort_order backfill orders by name: Alpha=0, Beta=1
    assert orders == {"Alpha": 0, "Beta": 1}


def test_upgrade_is_idempotent(legacy_engine) -> None:
    upgrade_database(legacy_engine)
    upgrade_database(legacy_engine)

    assert _alembic_version(legacy_engine) == _script_head()
    assert "image_uri_back" in _card_columns(legacy_engine)


def test_legacy_database_receives_migrations_past_the_baseline(legacy_engine) -> None:
    """Bridging stamps the baseline; later revisions must still be applied."""
    upgrade_database(legacy_engine)

    assert _script_head() != BASELINE_REVISION
    assert "card_prints" in set(inspect(legacy_engine).get_table_names())
    assert "house_bans" in set(inspect(legacy_engine).get_table_names())
    assert "is_locked" in _deck_columns(legacy_engine)
    assert "format" in _deck_columns(legacy_engine)
    assert "rarity" in _card_columns(legacy_engine)
    assert "rarity" in {
        col["name"] for col in inspect(legacy_engine).get_columns("card_prints")
    }
    assert "ix_card_copies_card_id" in _index_names(legacy_engine, "card_copies")
    assert "ix_decks_status" in _index_names(legacy_engine, "decks")
    assert {"finish", "collector_number", "printing_id", "updated_at"} <= _copy_columns(
        legacy_engine
    )
    assert "card_printings" in set(inspect(legacy_engine).get_table_names())
    with legacy_engine.begin() as conn:
        finishes = {
            copy_id: finish
            for copy_id, finish in conn.execute(
                text("SELECT id, finish FROM card_copies ORDER BY id")
            ).fetchall()
        }
    # The old foil flag defaulted to false for every copy. Only an explicit
    # true becomes a recorded foil; false stays unspecified.
    assert finishes == {1: "foil", 2: None}
