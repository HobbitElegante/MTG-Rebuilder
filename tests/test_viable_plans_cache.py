"""Tests for Planes viables cache fingerprint and filtering."""

from mtg_rebuilder.services.optimization_service import ViablePlan, ViablePlansResult
from mtg_rebuilder.services.settings_service import SettingsService
from mtg_rebuilder.services.viable_plans_cache import (
    CacheFreshness,
    CollectionFingerprint,
    ViablePlansCacheStore,
    build_deck_signature,
    compare_fingerprints,
    co_occurring_deck_ids,
    filter_plans_containing,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import pytest

from mtg_rebuilder.models import Base


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session


def test_compare_fingerprints_mandatory_on_fewer_copies() -> None:
    cached = CollectionFingerprint(copy_count=100, deck_sig="abc")
    current = CollectionFingerprint(copy_count=90, deck_sig="abc")
    assert compare_fingerprints(cached, current) == CacheFreshness.MANDATORY


def test_compare_fingerprints_optional_on_more_copies_or_deck_change() -> None:
    cached = CollectionFingerprint(copy_count=100, deck_sig="abc")
    assert (
        compare_fingerprints(
            cached, CollectionFingerprint(copy_count=110, deck_sig="abc")
        )
        == CacheFreshness.OPTIONAL
    )
    assert (
        compare_fingerprints(
            cached, CollectionFingerprint(copy_count=100, deck_sig="xyz")
        )
        == CacheFreshness.OPTIONAL
    )


def test_compare_fingerprints_fresh() -> None:
    fp = CollectionFingerprint(copy_count=50, deck_sig="same")
    assert compare_fingerprints(fp, fp) == CacheFreshness.FRESH


def test_filter_plans_containing() -> None:
    plans = (
        ViablePlan(deck_ids=(1, 2), deck_names=("A", "B")),
        ViablePlan(deck_ids=(2, 3), deck_names=("B", "C")),
        ViablePlan(deck_ids=(1, 3), deck_names=("A", "C")),
    )
    assert len(filter_plans_containing(plans, ())) == 3
    filtered = filter_plans_containing(plans, (1,))
    assert [plan.deck_names for plan in filtered] == [("A", "B"), ("A", "C")]


def test_filter_plans_containing_requires_every_deck() -> None:
    plans = (
        ViablePlan(deck_ids=(1, 2, 3), deck_names=("A", "B", "C")),
        ViablePlan(deck_ids=(1, 2, 4), deck_names=("A", "B", "D")),
        ViablePlan(deck_ids=(1, 3, 4), deck_names=("A", "C", "D")),
    )
    assert [p.deck_ids for p in filter_plans_containing(plans, (1, 2))] == [
        (1, 2, 3),
        (1, 2, 4),
    ]
    assert [p.deck_ids for p in filter_plans_containing(plans, (2, 1, 4))] == [
        (1, 2, 4)
    ]
    assert filter_plans_containing(plans, (2, 3, 4)) == ()


def test_co_occurring_deck_ids() -> None:
    plans = (
        ViablePlan(deck_ids=(1, 2, 3), deck_names=("A", "B", "C")),
        ViablePlan(deck_ids=(1, 2, 4), deck_names=("A", "B", "D")),
        ViablePlan(deck_ids=(3, 4, 5), deck_names=("C", "D", "E")),
    )
    assert co_occurring_deck_ids(plans) == frozenset({1, 2, 3, 4, 5})
    assert co_occurring_deck_ids(plans, (1,)) == frozenset({2, 3, 4})
    assert co_occurring_deck_ids(plans, (1, 2)) == frozenset({3, 4})
    assert co_occurring_deck_ids(plans, (1, 2, 3)) == frozenset()
    assert co_occurring_deck_ids(plans, (1, 5)) == frozenset()
    assert co_occurring_deck_ids(()) == frozenset()


def test_cache_store_roundtrip(session: Session) -> None:
    store = ViablePlansCacheStore(SettingsService(session))
    fp = CollectionFingerprint(copy_count=10, deck_sig=build_deck_signature(
        [(1, "Alpha", 90, False), (2, "Bravo", 90, True)]
    ))
    result = ViablePlansResult(
        size=2,
        plans=(
            ViablePlan(deck_ids=(1, 2), deck_names=("Alpha", "Bravo")),
        ),
        truncated=False,
    )
    store.put_entry(2, False, result, fp)
    loaded = store.get_entry(2, False)
    assert loaded is not None
    assert loaded.size == 2
    assert loaded.plans[0].deck_names == ("Alpha", "Bravo")
    assert store.freshness_for(2, False, fp) == CacheFreshness.FRESH
    assert store.get_entry(2, True) is None  # different ɸ key

    # Other N keeps its own fingerprint independently
    store.put_entry(
        3,
        False,
        ViablePlansResult(size=3, plans=(), truncated=False),
        fp,
    )
    fewer = CollectionFingerprint(copy_count=5, deck_sig=fp.deck_sig)
    assert store.freshness_for(2, False, fewer) == CacheFreshness.MANDATORY
    removed = store.clear_entries_with_mandatory(fewer)
    assert "2:0" in removed
    assert "3:0" in removed
    assert store.get_entry(2, False) is None
