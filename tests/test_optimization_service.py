from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import pytest

from mtg_rebuilder.models import Base, Card, CardCopy, Deck, DeckCard
from mtg_rebuilder.models.enums import DeckCardRole, DeckStatus
from mtg_rebuilder.services.optimization_service import (
    OptimizationService,
    allocate_solution_cards,
    sort_solutions_by_concentration,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session


def test_plan_assembly_exposes_readable_card_and_deck_names(session: Session) -> None:
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    cultivate = Card(
        oracle_id="cultivate",
        name="Cultivate",
        is_basic_land=False,
        is_token=False,
    )
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    donor = Deck(name="Donor Deck", status=DeckStatus.ARMED)
    session.add_all([sol, cultivate, target, donor])
    session.flush()

    session.add_all(
        [
            DeckCard(
                deck_id=target.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=target.id,
                card_id="cultivate",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=donor.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            CardCopy(card_id="cultivate"),
        ]
    )
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.free_inventory_used == {"cultivate": 1}
    assert plan.card_names["cultivate"] == "Cultivate"
    assert plan.deck_names[str(donor.id)] == "Donor Deck"
    assert plan.result.minimum_decks_to_dismantle == 1
    assert any("Donor Deck" in label for label in plan.solution_labels.values())


def test_plan_assembly_skips_already_armed_target(session: Session) -> None:
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    target = Deck(name="Already Armed", status=DeckStatus.ARMED)
    donor = Deck(name="Donor Deck", status=DeckStatus.ARMED)
    session.add_all([sol, target, donor])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=target.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=donor.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
        ]
    )
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.already_armed is True
    assert plan.free_inventory_used == {}
    assert plan.still_missing == {}
    assert plan.result.minimum_decks_to_dismantle == 0
    assert plan.result.solutions == (frozenset(),)
    assert plan.solution_labels == {}


def test_plan_assembly_includes_basic_lands_in_free_inventory(
    session: Session,
) -> None:
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    forest = Card(
        oracle_id="forest",
        name="Forest",
        is_basic_land=True,
        is_token=False,
    )
    token = Card(
        oracle_id="token",
        name="Saproling",
        is_basic_land=False,
        is_token=True,
    )
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    session.add_all([sol, forest, token, target])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=target.id,
                card_id="sol",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=target.id,
                card_id="forest",
                quantity=12,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=target.id,
                card_id="token",
                quantity=3,
                role=DeckCardRole.TOKEN,
            ),
            CardCopy(card_id="sol"),
        ]
    )
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.free_inventory_used == {"sol": 1, "forest": 12}
    assert "token" not in plan.free_inventory_used
    assert plan.residual_needs == {}
    assert plan.still_missing == {}
    assert plan.card_names["forest"] == "Forest"
    assert plan.result.minimum_decks_to_dismantle == 0


def test_plan_assembly_names_still_missing_cards(session: Session) -> None:
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    session.add_all([sol, target])
    session.flush()
    session.add(
        DeckCard(
            deck_id=target.id,
            card_id="sol",
            quantity=1,
            role=DeckCardRole.MAIN,
        )
    )
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.still_missing == {"sol": 1}
    assert plan.card_names["sol"] == "Sol Ring"
    assert plan.result.solutions == ()
    by_deck, need_to_find = plan.missing_by_source()
    assert by_deck == {}
    assert need_to_find == {"sol": 1}


def test_missing_by_source_groups_armed_and_unfindable(session: Session) -> None:
    ring = Card(oracle_id="ring", name="Sol Ring", is_basic_land=False, is_token=False)
    rare = Card(oracle_id="rare", name="Rare Card", is_basic_land=False, is_token=False)
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    donor = Deck(name="Donor Deck", status=DeckStatus.ARMED)
    session.add_all([ring, rare, target, donor])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=target.id,
                card_id="ring",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=target.id,
                card_id="rare",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=donor.id,
                card_id="ring",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
        ]
    )
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.still_missing == {"ring": 1, "rare": 1}
    assert plan.result.solutions == ()
    by_deck, need_to_find = plan.missing_by_source()
    assert by_deck == {str(donor.id): {"ring": 1}}
    assert need_to_find == {"rare": 1}


def test_allocate_solution_cards_splits_needs_across_decks() -> None:
    residual = {"a": 2, "b": 1}
    supplies = {
        "1": {"a": 1, "b": 1},
        "2": {"a": 2},
    }
    names = {"1": "Alpha", "2": "Beta"}
    solution = frozenset({"1", "2"})

    taken = allocate_solution_cards(residual, supplies, names, solution)

    assert taken == {"1": {"a": 1, "b": 1}, "2": {"a": 1}}
    attributed = {}
    for cards in taken.values():
        for card_id, qty in cards.items():
            attributed[card_id] = attributed.get(card_id, 0) + qty
    assert attributed == residual


def test_plan_assembly_cards_taken_match_residual_needs(session: Session) -> None:
    ring = Card(oracle_id="ring", name="Sol Ring", is_basic_land=False, is_token=False)
    ramp = Card(oracle_id="ramp", name="Rampant Growth", is_basic_land=False, is_token=False)
    draw = Card(oracle_id="draw", name="Opt", is_basic_land=False, is_token=False)
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    athreos = Deck(name="Athreos Donor", status=DeckStatus.ARMED)
    ghen = Deck(name="Ghen Donor", status=DeckStatus.ARMED)
    session.add_all([ring, ramp, draw, target, athreos, ghen])
    session.flush()

    session.add_all(
        [
            DeckCard(deck_id=target.id, card_id="ring", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=target.id, card_id="ramp", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=target.id, card_id="draw", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=athreos.id, card_id="ring", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=ghen.id, card_id="ramp", quantity=1, role=DeckCardRole.MAIN),
            CardCopy(card_id="draw"),
        ]
    )
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.free_inventory_used == {"draw": 1}
    assert plan.residual_needs == {"ring": 1, "ramp": 1}
    assert plan.still_missing == {}
    assert plan.result.minimum_decks_to_dismantle == 2
    assert len(plan.result.solutions) == 1

    solution = plan.result.solutions[0]
    taken = plan.cards_taken_from_solution(solution)
    attributed: dict[str, int] = {}
    for cards in taken.values():
        for card_id, qty in cards.items():
            attributed[card_id] = attributed.get(card_id, 0) + qty
    assert attributed == plan.residual_needs


def test_sort_solutions_prefers_the_richest_single_donor() -> None:
    residual = {"a": 1, "b": 1, "c": 1}
    supplies = {
        "1": {"a": 1},
        "2": {"b": 1, "c": 1},
        "3": {"a": 1, "b": 1, "c": 1},
        "4": {"x": 1},
    }
    names = {"1": "Alpha", "2": "Beta", "3": "Gamma", "4": "Delta"}
    spread = frozenset({"1", "2"})
    concentrated = frozenset({"3", "4"})

    ordered = sort_solutions_by_concentration(
        residual, supplies, names, (spread, concentrated)
    )

    assert ordered == (concentrated, spread)


def test_sort_solutions_breaks_full_ties_by_label() -> None:
    residual = {"a": 1}
    supplies = {"1": {"a": 1}, "2": {"a": 1}}
    names = {"1": "Zed", "2": "Ada"}

    ordered = sort_solutions_by_concentration(
        residual, supplies, names, (frozenset({"1"}), frozenset({"2"}))
    )

    assert ordered == (frozenset({"2"}), frozenset({"1"}))


def test_plan_assembly_orders_solutions_without_dropping_any(session: Session) -> None:
    ring = Card(oracle_id="ring", name="Sol Ring", is_basic_land=False, is_token=False)
    tower = Card(oracle_id="tower", name="Command Tower", is_basic_land=False, is_token=False)
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    rich = Deck(name="Rich Donor", status=DeckStatus.ARMED)
    poor = Deck(name="Poor Donor", status=DeckStatus.ARMED)
    session.add_all([ring, tower, target, rich, poor])
    session.flush()
    session.add_all(
        [
            DeckCard(deck_id=target.id, card_id="ring", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=target.id, card_id="tower", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=rich.id, card_id="ring", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=rich.id, card_id="tower", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=poor.id, card_id="ring", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=poor.id, card_id="tower", quantity=1, role=DeckCardRole.MAIN),
        ]
    )
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.result.minimum_decks_to_dismantle == 1
    assert len(plan.result.solutions) == 2
    # Both donors cover everything, so the alphabetical label decides.
    assert plan.solution_labels[plan.result.solutions[0]] == "Poor Donor"


def test_apply_assembly_plan_dismantles_then_arms(session: Session) -> None:
    from mtg_rebuilder.models import CardAssignment

    ring = Card(oracle_id="ring", name="Sol Ring", is_basic_land=False, is_token=False)
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    donor = Deck(name="Donor", status=DeckStatus.ARMED)
    session.add_all([ring, target, donor])
    session.flush()
    session.add_all(
        [
            DeckCard(deck_id=target.id, card_id="ring", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=donor.id, card_id="ring", quantity=1, role=DeckCardRole.MAIN),
        ]
    )
    session.flush()
    copy = CardCopy(card_id="ring")
    session.add(copy)
    session.flush()
    session.add(CardAssignment(card_copy_id=copy.id, deck_id=donor.id))
    session.flush()

    service = OptimizationService(session)
    plan = service.plan_assembly(target.id)
    assert plan.result.solutions
    solution = plan.result.solutions[0]
    service.apply_assembly_plan(target.id, solution)
    session.refresh(target)
    session.refresh(donor)

    assert donor.status == DeckStatus.DISMANTLED
    assert target.status == DeckStatus.ARMED
    from sqlalchemy import func, select

    target_assigned = session.scalar(
        select(func.count())
        .select_from(CardAssignment)
        .where(CardAssignment.deck_id == target.id)
    )
    donor_assigned = session.scalar(
        select(func.count())
        .select_from(CardAssignment)
        .where(CardAssignment.deck_id == donor.id)
    )
    assert target_assigned == 1
    assert donor_assigned == 0


def test_locked_armed_deck_is_not_a_donor_but_shows_in_missing(
    session: Session,
) -> None:
    from mtg_rebuilder.models import CardAssignment

    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    target = Deck(name="Target", status=DeckStatus.DISMANTLED)
    locked = Deck(name="Locked Donor", status=DeckStatus.ARMED, is_locked=True)
    session.add_all([sol, target, locked])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=target.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
            DeckCard(
                deck_id=locked.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
        ]
    )
    copy = CardCopy(card_id="sol")
    session.add(copy)
    session.flush()
    session.add(CardAssignment(card_copy_id=copy.id, deck_id=locked.id))
    session.flush()

    plan = OptimizationService(session).plan_assembly(target.id)

    assert plan.still_missing == {"sol": 1}
    assert str(locked.id) not in plan.deck_supplies
    by_deck, need_to_find = plan.missing_by_source()
    assert str(locked.id) in by_deck
    assert need_to_find == {}


def test_plan_assembly_sequence_simulates_prior_steps(session: Session) -> None:
    from mtg_rebuilder.models import CardAssignment

    a = Card(oracle_id="a", name="Card A", is_basic_land=False, is_token=False)
    b = Card(oracle_id="b", name="Card B", is_basic_land=False, is_token=False)
    t1 = Deck(name="First", status=DeckStatus.DISMANTLED)
    t2 = Deck(name="Second", status=DeckStatus.DISMANTLED)
    donor = Deck(name="Donor", status=DeckStatus.ARMED)
    session.add_all([a, b, t1, t2, donor])
    session.flush()
    session.add_all(
        [
            DeckCard(deck_id=t1.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=t2.id, card_id="b", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=donor.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=donor.id, card_id="b", quantity=1, role=DeckCardRole.MAIN),
        ]
    )
    copies = [CardCopy(card_id="a"), CardCopy(card_id="b")]
    session.add_all(copies)
    session.flush()
    session.add_all(
        [
            CardAssignment(card_copy_id=copies[0].id, deck_id=donor.id),
            CardAssignment(card_copy_id=copies[1].id, deck_id=donor.id),
        ]
    )
    session.flush()

    plans = OptimizationService(session).plan_assembly_sequence([t1.id, t2.id])

    assert not plans[0].still_missing
    assert plans[0].result.minimum_decks_to_dismantle == 1
    assert not plans[1].still_missing
    assert plans[1].result.minimum_decks_to_dismantle == 0


def test_armed_deck_in_sequence_is_not_a_donor(session: Session) -> None:
    from mtg_rebuilder.models import CardAssignment
    from mtg_rebuilder.services.optimization_service import sequence_is_viable

    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    kept = Deck(name="Kept Armed", status=DeckStatus.ARMED)
    target = Deck(name="Needs Sol", status=DeckStatus.DISMANTLED)
    session.add_all([sol, kept, target])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=kept.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
            DeckCard(
                deck_id=target.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
        ]
    )
    copy = CardCopy(card_id="sol")
    session.add(copy)
    session.flush()
    session.add(CardAssignment(card_copy_id=copy.id, deck_id=kept.id))
    session.flush()

    plans = OptimizationService(session).plan_assembly_sequence([kept.id, target.id])

    assert plans[0].already_armed
    assert plans[1].still_missing == {"sol": 1}
    assert str(kept.id) not in plans[1].deck_supplies
    by_deck, _ = plans[1].missing_by_source()
    assert str(kept.id) in by_deck
    assert not sequence_is_viable(plans)


def test_prior_target_is_not_donor_for_later_step(session: Session) -> None:
    from mtg_rebuilder.models import CardAssignment
    from mtg_rebuilder.services.optimization_service import (
        sequence_is_viable,
        unique_donors_for_sequence,
    )

    a = Card(oracle_id="a", name="Card A", is_basic_land=False, is_token=False)
    b = Card(oracle_id="b", name="Card B", is_basic_land=False, is_token=False)
    t1 = Deck(name="First", status=DeckStatus.DISMANTLED)
    t2 = Deck(name="Second", status=DeckStatus.DISMANTLED)
    donor = Deck(name="Donor", status=DeckStatus.ARMED)
    session.add_all([a, b, t1, t2, donor])
    session.flush()
    # t1 needs A (on donor); t2 needs A as well — only one copy on donor.
    # After t1 arms, that copy is consumed; t1 must not be dismantled for t2.
    session.add_all(
        [
            DeckCard(deck_id=t1.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=t2.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=donor.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=donor.id, card_id="b", quantity=1, role=DeckCardRole.MAIN),
        ]
    )
    copies = [CardCopy(card_id="a"), CardCopy(card_id="b")]
    session.add_all(copies)
    session.flush()
    session.add_all(
        [
            CardAssignment(card_copy_id=copies[0].id, deck_id=donor.id),
            CardAssignment(card_copy_id=copies[1].id, deck_id=donor.id),
        ]
    )
    session.flush()

    plans = OptimizationService(session).plan_assembly_sequence([t1.id, t2.id])

    assert not plans[0].still_missing
    assert str(t1.id) not in plans[1].deck_supplies
    assert plans[1].still_missing == {"a": 1}
    assert not sequence_is_viable(plans)
    assert unique_donors_for_sequence(plans) == frozenset({str(donor.id)})


def test_unique_donors_counts_union_across_viable_steps(session: Session) -> None:
    from mtg_rebuilder.models import CardAssignment
    from mtg_rebuilder.services.optimization_service import (
        sequence_is_viable,
        unique_donors_for_sequence,
    )

    a = Card(oracle_id="a", name="Card A", is_basic_land=False, is_token=False)
    b = Card(oracle_id="b", name="Card B", is_basic_land=False, is_token=False)
    t1 = Deck(name="First", status=DeckStatus.DISMANTLED)
    t2 = Deck(name="Second", status=DeckStatus.DISMANTLED)
    d1 = Deck(name="Donor A", status=DeckStatus.ARMED)
    d2 = Deck(name="Donor B", status=DeckStatus.ARMED)
    session.add_all([a, b, t1, t2, d1, d2])
    session.flush()
    session.add_all(
        [
            DeckCard(deck_id=t1.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=t2.id, card_id="b", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=d1.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=d2.id, card_id="b", quantity=1, role=DeckCardRole.MAIN),
        ]
    )
    copies = [CardCopy(card_id="a"), CardCopy(card_id="b")]
    session.add_all(copies)
    session.flush()
    session.add_all(
        [
            CardAssignment(card_copy_id=copies[0].id, deck_id=d1.id),
            CardAssignment(card_copy_id=copies[1].id, deck_id=d2.id),
        ]
    )
    session.flush()

    plans = OptimizationService(session).plan_assembly_sequence([t1.id, t2.id])

    assert sequence_is_viable(plans)
    assert unique_donors_for_sequence(plans) == frozenset({str(d1.id), str(d2.id)})


def test_list_viable_plans_fixed_n_and_max(session: Session) -> None:
    a = Card(oracle_id="a", name="A", is_basic_land=False, is_token=False)
    b = Card(oracle_id="b", name="B", is_basic_land=False, is_token=False)
    c = Card(oracle_id="c", name="C", is_basic_land=False, is_token=False)
    d1 = Deck(name="Alpha", status=DeckStatus.DISMANTLED)
    d2 = Deck(name="Bravo", status=DeckStatus.DISMANTLED)
    d3 = Deck(name="Charlie", status=DeckStatus.DISMANTLED)
    session.add_all([a, b, c, d1, d2, d3])
    session.flush()
    session.add_all(
        [
            DeckCard(deck_id=d1.id, card_id="a", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=d2.id, card_id="b", quantity=1, role=DeckCardRole.MAIN),
            DeckCard(deck_id=d3.id, card_id="c", quantity=1, role=DeckCardRole.MAIN),
            CardCopy(card_id="a"),
            CardCopy(card_id="b"),
            CardCopy(card_id="c"),
        ]
    )
    session.flush()

    service = OptimizationService(session)
    pairs = service.list_viable_plans(n=2)
    assert pairs.size == 2
    assert len(pairs.plans) == 3
    labels = {plan.label() for plan in pairs.plans}
    assert labels == {"Alpha · Bravo", "Alpha · Charlie", "Bravo · Charlie"}

    maximum = service.list_viable_plans(n=None)
    assert maximum.size == 3
    assert len(maximum.plans) == 1
    assert maximum.plans[0].label() == "Alpha · Bravo · Charlie"


def test_list_viable_plans_ignore_finish(session: Session) -> None:
    """Two copies with different finishes are still stock 2 for the same card."""
    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    alpha = Deck(name="Alpha", status=DeckStatus.DISMANTLED)
    bravo = Deck(name="Bravo", status=DeckStatus.DISMANTLED)
    session.add_all([sol, alpha, bravo])
    session.flush()
    copies = [
        CardCopy(card_id="sol"),
        CardCopy(card_id="sol"),
    ]
    session.add_all(
        [
            DeckCard(
                deck_id=alpha.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
            DeckCard(
                deck_id=bravo.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
            *copies,
        ]
    )
    session.flush()

    service = OptimizationService(session)
    blank = service.list_viable_plans(n=2)
    copies[0].finish = "foil"
    copies[1].finish = "etched"
    session.flush()
    marked = service.list_viable_plans(n=2)

    assert [plan.label() for plan in marked.plans] == [
        plan.label() for plan in blank.plans
    ]
    assert marked.plans[0].label() == "Alpha · Bravo"


def test_list_viable_plans_respect_locked(session: Session) -> None:
    from mtg_rebuilder.models import CardAssignment

    sol = Card(oracle_id="sol", name="Sol Ring", is_basic_land=False, is_token=False)
    cultivate = Card(
        oracle_id="cultivate", name="Cultivate", is_basic_land=False, is_token=False
    )
    free_deck = Deck(name="Needs Sol", status=DeckStatus.DISMANTLED)
    other = Deck(name="Needs Cultivate", status=DeckStatus.DISMANTLED)
    locked = Deck(name="Locked", status=DeckStatus.ARMED, is_locked=True)
    session.add_all([sol, cultivate, free_deck, other, locked])
    session.flush()
    session.add_all(
        [
            DeckCard(
                deck_id=free_deck.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
            DeckCard(
                deck_id=other.id,
                card_id="cultivate",
                quantity=1,
                role=DeckCardRole.MAIN,
            ),
            DeckCard(
                deck_id=locked.id, card_id="sol", quantity=1, role=DeckCardRole.MAIN
            ),
        ]
    )
    copies = [CardCopy(card_id="sol"), CardCopy(card_id="cultivate")]
    session.add_all(copies)
    session.flush()
    session.add(CardAssignment(card_copy_id=copies[0].id, deck_id=locked.id))
    session.flush()

    service = OptimizationService(session)
    global_pairs = service.list_viable_plans(n=2, respect_locked=False)
    global_labels = {plan.label() for plan in global_pairs.plans}
    assert "Needs Cultivate · Needs Sol" in global_labels
    assert "Locked · Needs Cultivate" in global_labels

    hybrid = service.list_viable_plans(n=2, respect_locked=True)
    hybrid_labels = {plan.label() for plan in hybrid.plans}
    # Sol reserved by locked → Needs Sol + Needs Cultivate fails
    assert "Needs Cultivate · Needs Sol" not in hybrid_labels
    assert "Locked · Needs Cultivate" in hybrid_labels
