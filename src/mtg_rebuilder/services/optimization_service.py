from dataclasses import dataclass, replace
from collections.abc import Callable

from sqlalchemy.orm import Session

from mtg_rebuilder.algorithms.deck_optimizer import DeckSupply, OptimizationResult, find_all_optimal_solutions
from mtg_rebuilder.algorithms.viable_plans import (
    DEFAULT_LIST_LIMIT,
    enumerate_max_viable_combinations,
    enumerate_viable_combinations,
)
from mtg_rebuilder.models.enums import ActivityEventType, DeckStatus
from mtg_rebuilder.repositories import CardRepository, CopyRepository
from mtg_rebuilder.services.activity_service import ActivityService
from mtg_rebuilder.services.deck_service import DeckService, InventoryService


def allocate_solution_cards(
    residual_needs: dict[str, int],
    deck_supplies: dict[str, dict[str, int]],
    deck_names: dict[str, str],
    solution: frozenset[str],
) -> dict[str, dict[str, int]]:
    """Greedy stable allocation of residual needs to decks in a solution.

    Decks are processed in name order; cards within a deck by card id.
    Only cards required by the target (residual after free inventory) are
    attributed — not the full donor deck list.
    """
    remaining = {card_id: qty for card_id, qty in residual_needs.items() if qty > 0}
    ordered_decks = sorted(
        (deck_id for deck_id in solution if deck_id in deck_supplies),
        key=lambda deck_id: deck_names.get(deck_id, deck_id).lower(),
    )
    taken: dict[str, dict[str, int]] = {}
    for deck_id in ordered_decks:
        supply = deck_supplies[deck_id]
        for card_id in sorted(supply.keys()):
            need = remaining.get(card_id, 0)
            if need <= 0:
                continue
            available = supply.get(card_id, 0)
            if available <= 0:
                continue
            use = min(need, available)
            taken.setdefault(deck_id, {})[card_id] = use
            remaining[card_id] = need - use
    return taken


def sort_solutions_by_concentration(
    residual_needs: dict[str, int],
    deck_supplies: dict[str, dict[str, int]],
    deck_names: dict[str, str],
    solutions: tuple[frozenset[str], ...],
) -> tuple[frozenset[str], ...]:
    """Order equally optimal solutions; none are dropped.

    All solutions dismantle the same number of decks, so the tie-break prefers
    the one where a single donor covers the most cards the target needs: fewer
    boxes to dig through for the same result. The user can still pick any of
    them in the UI.
    """

    def key(solution: frozenset[str]) -> tuple[int, str]:
        taken = allocate_solution_cards(
            residual_needs, deck_supplies, deck_names, solution
        )
        best_donor = max((sum(cards.values()) for cards in taken.values()), default=0)
        label = ", ".join(deck_names.get(deck_id, deck_id) for deck_id in sorted(solution))
        return (-best_donor, label.casefold())

    return tuple(sorted(solutions, key=key))


def remaining_after_allocation(
    needs: dict[str, int],
    taken: dict[str, dict[str, int]],
) -> dict[str, int]:
    """Subtract allocated quantities from needs; drop zeros."""
    leftover = dict(needs)
    for cards in taken.values():
        for card_id, qty in cards.items():
            leftover[card_id] = leftover.get(card_id, 0) - qty
            if leftover.get(card_id, 0) <= 0:
                leftover.pop(card_id, None)
    return {card_id: qty for card_id, qty in leftover.items() if qty > 0}


@dataclass(frozen=True)
class MovedCopy:
    """A copy the target deck now holds that has no edition recorded.

    Other traits are whatever was already on the copy, so the prompt can show
    them. They do not decide whether the copy is listed.
    """

    copy_id: int
    oracle_id: str
    card_name: str
    finish: str | None = None
    language: str | None = None
    condition: str | None = None
    collector_number: str | None = None
    printing_id: str | None = None


@dataclass(frozen=True)
class ViablePlan:
    """One simultaneous set of decks that fits physical stock (names for UI)."""

    deck_ids: tuple[int, ...]
    deck_names: tuple[str, ...]

    def label(self, sep: str = " · ") -> str:
        return sep.join(self.deck_names)


@dataclass(frozen=True)
class ViablePlansResult:
    """Result of listing viable simultaneous sets.

    ``size`` is the combination size shown (requested N, or max M when
    ``n`` was None). Zero means no grouping of 2+ decks fits.
    ``truncated`` means listing stopped early (too many hits for the UI).
    """

    size: int
    plans: tuple[ViablePlan, ...]
    truncated: bool = False


@dataclass(frozen=True)
class AssemblyPlan:
    target_deck_id: int
    target_deck_name: str
    result: OptimizationResult
    free_inventory_used: dict[str, int]
    still_missing: dict[str, int]
    residual_needs: dict[str, int]
    deck_supplies: dict[str, dict[str, int]]
    solution_labels: dict[frozenset[str], str]
    card_names: dict[str, str]
    deck_names: dict[str, str]
    already_armed: bool = False
    # Armed decks including locked — used only to explain “still missing”.
    visibility_supplies: dict[str, dict[str, int]] | None = None

    def cards_taken_from_solution(
        self, solution: frozenset[str]
    ) -> dict[str, dict[str, int]]:
        return allocate_solution_cards(
            self.residual_needs,
            self.deck_supplies,
            self.deck_names,
            solution,
        )

    def missing_by_source(
        self,
    ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
        """Group unmet needs by armed decks vs not findable anywhere.

        Returns ``(by_deck, need_to_find)`` where ``by_deck`` maps armed deck
        ids to cards they could cover from ``still_missing``, and
        ``need_to_find`` is the remainder not present in free inventory or
        any armed deck. Locked decks appear here even though they are not
        dismantle candidates.
        """
        if not self.still_missing:
            return {}, {}
        supplies = self.visibility_supplies or self.deck_supplies
        all_armed = frozenset(supplies.keys())
        by_deck = allocate_solution_cards(
            self.still_missing,
            supplies,
            self.deck_names,
            all_armed,
        )
        need_to_find = remaining_after_allocation(self.still_missing, by_deck)
        return by_deck, need_to_find


def simulate_apply_plan(
    free: dict[str, int],
    donor_supplies: dict[int, dict[str, int]],
    visibility_supplies: dict[int, dict[str, int]],
    target_deck_id: int,
    requirements: dict[str, int],
    solution: frozenset[str],
) -> tuple[dict[str, int], dict[int, dict[str, int]], dict[int, dict[str, int]]]:
    """Advance count-level inventory as if Confirm had run for one step.

    The newly armed target is recorded in visibility (for missing explanations)
    but is **not** added to the donor pool — the sequence keeps every planned
    deck armed at once, so later steps must not dismantle prior targets.
    """
    free = dict(free)
    donors = {deck_id: dict(cards) for deck_id, cards in donor_supplies.items()}
    visible = {
        deck_id: dict(cards) for deck_id, cards in visibility_supplies.items()
    }
    for deck_key in solution:
        deck_id = int(deck_key)
        supply = donors.pop(deck_id, {})
        visible.pop(deck_id, None)
        for card_id, qty in supply.items():
            free[card_id] = free.get(card_id, 0) + qty
    for card_id, qty in requirements.items():
        remaining = free.get(card_id, 0) - qty
        if remaining > 0:
            free[card_id] = remaining
        else:
            free.pop(card_id, None)
    visible[target_deck_id] = dict(requirements)
    return free, donors, visible


def sequence_is_viable(plans: list[AssemblyPlan]) -> bool:
    """True when every step is keep-armed or has a feasible dismantle plan."""
    return all(
        plan.already_armed
        or (not plan.still_missing and bool(plan.result.solutions))
        for plan in plans
    )


def unique_donors_for_sequence(
    plans: list[AssemblyPlan],
    chosen_solutions: dict[int, frozenset[str]] | None = None,
) -> frozenset[str]:
    """Union of chosen (or suggested) donor ids across viable assembly steps."""
    chosen = chosen_solutions or {}
    donors: set[str] = set()
    for plan in plans:
        if plan.already_armed or plan.still_missing or not plan.result.solutions:
            continue
        solution = chosen.get(plan.target_deck_id, plan.result.solutions[0])
        donors.update(solution)
    return frozenset(donors)


class OptimizationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._decks = DeckService(session)
        self._inventory = InventoryService(session)
        self._cards = CardRepository(session)
        self._copies = CopyRepository(session)

    def plan_assembly(self, target_deck_id: int) -> AssemblyPlan:
        free = self._inventory.free_counts()
        donors = self._decks.armed_deck_supplies(
            exclude_deck_id=target_deck_id, include_locked=False
        )
        visible = self._decks.armed_deck_supplies(
            exclude_deck_id=target_deck_id, include_locked=True
        )
        return self._plan_from_state(target_deck_id, free, donors, visible)

    def plan_assembly_sequence(
        self,
        target_deck_ids: list[int],
        chosen_solutions: dict[int, frozenset[str]] | None = None,
    ) -> list[AssemblyPlan]:
        """Plan each target in order for a simultaneous armed set.

        Decks in ``target_deck_ids`` are keep-armed for the whole sequence: they
        are never dismantle candidates. Already-armed entries are skipped (kept).
        Successful steps update free inventory as if Confirm ran, without adding
        the new target to the donor pool so later steps cannot dismantle it.
        """
        chosen = chosen_solutions or {}
        keep_ids = set(target_deck_ids)
        free = self._inventory.free_counts()
        donors = self._decks.armed_deck_supplies(include_locked=False)
        visible = self._decks.armed_deck_supplies(include_locked=True)
        plans: list[AssemblyPlan] = []
        for target_id in target_deck_ids:
            step_donors = {
                deck_id: cards
                for deck_id, cards in donors.items()
                if deck_id not in keep_ids
            }
            plan = self._plan_from_state(target_id, free, step_donors, visible)
            plans.append(plan)
            if plan.already_armed or plan.still_missing or not plan.result.solutions:
                continue
            solution = chosen.get(target_id, plan.result.solutions[0])
            requirements = self._decks.deck_requirements(target_id)
            free, donors, visible = simulate_apply_plan(
                free, donors, visible, target_id, requirements, solution
            )
        return plans

    def _plan_from_state(
        self,
        target_deck_id: int,
        free: dict[str, int],
        donor_supplies: dict[int, dict[str, int]],
        visibility_supplies: dict[int, dict[str, int]],
    ) -> AssemblyPlan:
        target = self._decks.get_deck(target_deck_id)
        if target is None:
            raise ValueError(f"Deck {target_deck_id} not found")

        if target.status == DeckStatus.ARMED:
            return AssemblyPlan(
                target_deck_id=target.id,
                target_deck_name=target.name,
                result=OptimizationResult(
                    minimum_decks_to_dismantle=0,
                    solutions=(frozenset(),),
                    unmet_needs={},
                ),
                free_inventory_used={},
                still_missing={},
                residual_needs={},
                deck_supplies={},
                solution_labels={},
                card_names={},
                deck_names={},
                already_armed=True,
            )

        requirements = self._decks.deck_requirements(target_deck_id)
        needs: dict[str, int] = {}
        free_used: dict[str, int] = {}
        for card_id, required in requirements.items():
            available = free.get(card_id, 0)
            used = min(required, available)
            if used:
                free_used[card_id] = used
            remaining = required - used
            if remaining > 0:
                needs[card_id] = remaining

        for card_id, qty in self._decks.deck_basic_lands(target_deck_id).items():
            if qty > 0:
                free_used[card_id] = qty

        supplies: dict[str, DeckSupply] = {}
        deck_names: dict[str, str] = {}
        deck_supplies: dict[str, dict[str, int]] = {}
        for deck_id, cards in donor_supplies.items():
            if deck_id == target_deck_id:
                continue
            deck = self._decks.get_deck(deck_id)
            name = deck.name if deck is not None else str(deck_id)
            deck_key = str(deck_id)
            supplies[deck_key] = DeckSupply(
                deck_id=deck_key,
                deck_name=name,
                cards=cards,
            )
            deck_names[deck_key] = name
            deck_supplies[deck_key] = dict(cards)

        visibility: dict[str, dict[str, int]] = {}
        for deck_id, cards in visibility_supplies.items():
            if deck_id == target_deck_id:
                continue
            deck = self._decks.get_deck(deck_id)
            name = deck.name if deck is not None else str(deck_id)
            deck_key = str(deck_id)
            deck_names[deck_key] = name
            visibility[deck_key] = dict(cards)

        result = find_all_optimal_solutions(needs, supplies)
        result = replace(
            result,
            solutions=sort_solutions_by_concentration(
                needs, deck_supplies, deck_names, result.solutions
            ),
        )

        labels = {
            solution: ", ".join(
                supplies[deck_id].deck_name for deck_id in sorted(solution)
            )
            for solution in result.solutions
        }

        card_ids = set(free_used) | set(result.unmet_needs) | set(needs)
        for cards in deck_supplies.values():
            card_ids.update(cards)
        for cards in visibility.values():
            card_ids.update(cards)
        card_names = self._card_names(card_ids)

        return AssemblyPlan(
            target_deck_id=target.id,
            target_deck_name=target.name,
            result=result,
            free_inventory_used=free_used,
            still_missing=result.unmet_needs,
            residual_needs=needs,
            deck_supplies=deck_supplies,
            solution_labels=labels,
            card_names=card_names,
            deck_names=deck_names,
            visibility_supplies=visibility,
        )

    def apply_assembly_plan(
        self,
        target_deck_id: int,
        solution: frozenset[str],
    ) -> list[MovedCopy]:
        """Dismantle each deck in ``solution``, then arm the target.

        Returns the copies that ended up in the target without a recorded
        edition, so the UI can offer to fill them in.
        """
        target = self._decks.get_deck(target_deck_id)
        if target is None:
            raise ValueError(f"Deck {target_deck_id} not found")
        if target.status == DeckStatus.ARMED:
            raise ValueError("Target deck is already armed")

        donor_names: list[str] = []
        donor_ids: list[int] = []
        for deck_key in sorted(solution):
            try:
                deck_id = int(deck_key)
            except ValueError as exc:
                raise ValueError(f"Invalid deck id in solution: {deck_key}") from exc
            deck = self._decks.get_deck(deck_id)
            if deck is None:
                raise ValueError(f"Deck {deck_id} not found")
            if deck.is_locked:
                raise ValueError(f"Deck {deck.name} is locked")
            if deck.status != DeckStatus.ARMED:
                raise ValueError(f"Deck {deck.name} is not armed")
            donor_names.append(deck.name)
            donor_ids.append(deck_id)
            self._decks.set_status(deck, DeckStatus.DISMANTLED, record_activity=False)

        self._session.refresh(target)
        self._decks.set_status(target, DeckStatus.ARMED, record_activity=False)
        ActivityService(self._session).record(
            ActivityEventType.PLAN_APPLIED,
            "history.event.plan_applied",
            {
                "deck_id": target.id,
                "deck_name": target.name,
                "donor_deck_ids": donor_ids,
                "donor_names": donor_names,
            },
        )
        return [
            MovedCopy(
                copy_id=copy.id,
                oracle_id=copy.card_id,
                card_name=card_name,
                finish=copy.finish,
                language=copy.language,
                condition=copy.condition,
                collector_number=copy.collector_number,
                printing_id=copy.printing_id,
            )
            for copy, card_name in self._copies.list_unspecified_for_deck(target.id)
        ]

    def list_viable_plans(
        self,
        *,
        n: int | None = None,
        respect_locked: bool = False,
        limit: int = DEFAULT_LIST_LIMIT,
        should_stop: Callable[[], bool] | None = None,
    ) -> ViablePlansResult:
        """List simultaneous deck sets that fit total physical stock.

        ``n`` selects a fixed size; ``n=None`` finds the maximum viable size
        (≥2) and returns combinations of that size (ties included, capped).
        """
        decks = self._decks.list_decks()
        deck_ids = [deck.id for deck in decks]
        names = {deck.id: deck.name for deck in decks}
        requirements = {
            deck.id: self._decks.deck_requirements(deck.id) for deck in decks
        }
        stock = self._copies.counts_by_card()
        locked_ids: set[int] = set()
        locked_assigned: dict[int, dict[str, int]] = {}
        if respect_locked:
            locked_ids = {deck.id for deck in decks if deck.is_locked}
            for deck_id in locked_ids:
                req = requirements.get(deck_id, {})
                locked_assigned[deck_id] = self._copies.assigned_counts_for_deck(
                    deck_id, req.keys()
                )

        if n is None:
            size, combos, truncated = enumerate_max_viable_combinations(
                deck_ids,
                requirements,
                stock,
                respect_locks=respect_locked,
                locked_ids=locked_ids,
                locked_assigned_by_deck=locked_assigned,
                limit=limit,
                should_stop=should_stop,
            )
        else:
            size = n
            combos, truncated = enumerate_viable_combinations(
                deck_ids,
                requirements,
                stock,
                n=n,
                respect_locks=respect_locked,
                locked_ids=locked_ids,
                locked_assigned_by_deck=locked_assigned,
                limit=limit,
                should_stop=should_stop,
            )

        plans: list[ViablePlan] = []
        for combo in combos:
            ordered = tuple(
                sorted(combo, key=lambda deck_id: names.get(deck_id, "").casefold())
            )
            plans.append(
                ViablePlan(
                    deck_ids=ordered,
                    deck_names=tuple(
                        names.get(deck_id, str(deck_id)) for deck_id in ordered
                    ),
                )
            )
        plans.sort(key=lambda plan: tuple(name.casefold() for name in plan.deck_names))
        result_size = size if combos else (0 if n is None else n)
        return ViablePlansResult(
            size=result_size, plans=tuple(plans), truncated=truncated and bool(combos)
        )

    def _card_names(self, card_ids: set[str]) -> dict[str, str]:
        return self._cards.names_by_ids(card_ids)
