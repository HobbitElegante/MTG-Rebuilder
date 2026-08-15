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
    return engine


def _card_columns(engine) -> set[str]:
    with engine.begin() as conn:
        return {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(cards)")).fetchall()
        }


def _deck_columns(engine) -> set[str]:
    with engine.begin() as conn:
        return {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(decks)")).fetchall()
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
