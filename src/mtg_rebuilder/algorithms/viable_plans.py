"""Enumerate simultaneous deck sets that fit physical collection stock.

Unlike Plan de Armado (ILP over donors), this only checks whether the summed
list demand of N decks fits total copies — optional hybrid that reserves
copies assigned to locked (ɸ) decks so they cannot cover other decks.
"""

from __future__ import annotations

from collections.abc import Callable

# Soft cap for UI listing — beyond this, return early (truncated=True).
DEFAULT_LIST_LIMIT = 500

# Nodes of the search tree between two ``should_stop`` polls.
STOP_CHECK_INTERVAL = 2048


def sum_requirements(
    deck_ids: tuple[int, ...] | list[int],
    requirements_by_deck: dict[int, dict[str, int]],
) -> dict[str, int]:
    """Sum list demand by oracle_id across decks (basics/tokens already excluded)."""
    total: dict[str, int] = {}
    for deck_id in deck_ids:
        for card_id, qty in requirements_by_deck.get(deck_id, {}).items():
            if qty > 0:
                total[card_id] = total.get(card_id, 0) + qty
    return total


def is_combination_viable(
    demand: dict[str, int],
    stock: dict[str, int],
) -> bool:
    """Global: every card's demand ≤ total physical copies."""
    for card_id, required in demand.items():
        if required > 0 and stock.get(card_id, 0) < required:
            return False
    return True


def _assigned_all_locked(
    locked_ids: set[int],
    locked_assigned_by_deck: dict[int, dict[str, int]],
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for deck_id in locked_ids:
        for card_id, qty in locked_assigned_by_deck.get(deck_id, {}).items():
            if qty > 0:
                totals[card_id] = totals.get(card_id, 0) + qty
    return totals


def _pool_after_locks(
    stock: dict[str, int],
    assigned_all_locked: dict[str, int],
) -> dict[str, int]:
    """Physical copies usable as shared pool once locked assignments are reserved."""
    pool: dict[str, int] = {}
    card_ids = set(stock) | set(assigned_all_locked)
    for card_id in card_ids:
        value = stock.get(card_id, 0) - assigned_all_locked.get(card_id, 0)
        pool[card_id] = value if value > 0 else 0
    return pool


def _deck_pool_demand(
    deck_id: int,
    requirements_by_deck: dict[int, dict[str, int]],
    locked_ids: set[int],
    locked_assigned_by_deck: dict[int, dict[str, int]],
) -> dict[str, int]:
    """How much this deck draws from the shared pool when selected.

    Unlocked: full list demand. Locked: only shortfall beyond its own assignments.
    """
    req = requirements_by_deck.get(deck_id, {})
    if deck_id not in locked_ids:
        return {card_id: qty for card_id, qty in req.items() if qty > 0}
    assigned = locked_assigned_by_deck.get(deck_id, {})
    shortfall: dict[str, int] = {}
    for card_id, qty in req.items():
        need = qty - assigned.get(card_id, 0)
        if need > 0:
            shortfall[card_id] = need
    return shortfall


def is_combination_viable_respecting_locks(
    combo: tuple[int, ...] | list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    locked_ids: set[int],
    locked_assigned_by_deck: dict[int, dict[str, int]],
    *,
    pool: dict[str, int] | None = None,
    pool_demand_by_deck: dict[int, dict[str, int]] | None = None,
) -> bool:
    """Hybrid: locked assigned copies cannot cover other decks' demand.

    Per oracle_id::

        pool = total - assigned_to_all_locked
        ok ⇔ Σ pool_demand(d) for d in combo ≤ pool
        where unlocked pool_demand = req, locked = max(0, req - assigned)
    """
    if pool is None:
        assigned_all = _assigned_all_locked(locked_ids, locked_assigned_by_deck)
        pool = _pool_after_locks(stock, assigned_all)
    if pool_demand_by_deck is None:
        pool_demand_by_deck = {
            deck_id: _deck_pool_demand(
                deck_id, requirements_by_deck, locked_ids, locked_assigned_by_deck
            )
            for deck_id in combo
        }

    need: dict[str, int] = {}
    for deck_id in combo:
        for card_id, qty in pool_demand_by_deck.get(deck_id, {}).items():
            need[card_id] = need.get(card_id, 0) + qty
    for card_id, required in need.items():
        if required > pool.get(card_id, 0):
            return False
    return True


def _capacity_and_demands(
    deck_ids: list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    *,
    respect_locks: bool,
    locked_ids: set[int],
    locked_assigned_by_deck: dict[int, dict[str, int]],
) -> tuple[dict[str, int], list[list[tuple[str, int]]]]:
    """Capacity per card plus what each deck draws from it, in ``deck_ids`` order.

    Both modes reduce to the same test — a set of decks fits when its summed
    demand stays within capacity — so the search itself never needs to know
    whether locks are being respected.
    """
    if respect_locks and locked_ids:
        capacity = _pool_after_locks(
            stock, _assigned_all_locked(locked_ids, locked_assigned_by_deck)
        )
        per_deck = [
            _deck_pool_demand(
                deck_id, requirements_by_deck, locked_ids, locked_assigned_by_deck
            )
            for deck_id in deck_ids
        ]
    else:
        capacity = stock
        per_deck = [requirements_by_deck.get(deck_id, {}) for deck_id in deck_ids]
    demands = [
        [(card_id, qty) for card_id, qty in demand.items() if qty > 0]
        for demand in per_deck
    ]
    return capacity, demands


def _search_combinations(
    ordered: list[int],
    demands: list[list[tuple[str, int]]],
    capacity: dict[str, int],
    *,
    n: int,
    limit: int | None,
    should_stop: Callable[[], bool] | None,
) -> tuple[list[tuple[int, ...]], bool]:
    """Depth-first walk over size-``n`` combinations, skipping dead branches.

    Demand accumulates as decks are picked, so a prefix that already exceeds
    capacity for one card prunes every combination extending it instead of
    re-summing each one. Results come out in the same order as
    ``itertools.combinations`` over ``ordered``.
    """
    total = len(ordered)
    found: list[tuple[int, ...]] = []
    used: dict[str, int] = {}
    picked: list[int] = []
    stopped = False
    polls_left = 0

    def walk(start: int, remaining: int) -> bool:
        """Pick one more deck; True means enumeration is over (limit or stop)."""
        nonlocal stopped, polls_left
        if remaining == 0:
            found.append(tuple(picked))
            return limit is not None and len(found) >= limit
        # Stop early enough to still fit the decks left to pick.
        for index in range(start, total - remaining + 1):
            if should_stop is not None:
                if polls_left <= 0:
                    if should_stop():
                        stopped = True
                        return True
                    polls_left = STOP_CHECK_INTERVAL
                polls_left -= 1

            demand = demands[index]
            added = 0
            for card_id, qty in demand:
                running = used.get(card_id, 0) + qty
                if running > capacity.get(card_id, 0):
                    break
                used[card_id] = running
                added += 1

            done = False
            if added == len(demand):
                picked.append(ordered[index])
                done = walk(index + 1, remaining - 1)
                picked.pop()
            for position in range(added):
                card_id, qty = demand[position]
                used[card_id] -= qty
            if done:
                return True
        return False

    walk(0, n)
    return found, stopped or (limit is not None and len(found) >= limit)


def enumerate_viable_combinations(
    deck_ids: list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    *,
    n: int,
    respect_locks: bool = False,
    locked_ids: set[int] | None = None,
    locked_assigned_by_deck: dict[int, dict[str, int]] | None = None,
    limit: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[list[tuple[int, ...]], bool]:
    """Viable combinations of size ``n``.

    Returns ``(combos, truncated)``. When ``limit`` is set, stops after that
    many hits (``truncated=True`` if more may exist).
    """
    if n < 1 or n > len(deck_ids):
        return [], False
    ordered = sorted(deck_ids)
    capacity, demands = _capacity_and_demands(
        ordered,
        requirements_by_deck,
        stock,
        respect_locks=respect_locks,
        locked_ids=locked_ids or set(),
        locked_assigned_by_deck=locked_assigned_by_deck or {},
    )
    return _search_combinations(
        ordered,
        demands,
        capacity,
        n=n,
        limit=limit,
        should_stop=should_stop,
    )


def any_viable_combination(
    deck_ids: list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    *,
    n: int,
    respect_locks: bool = False,
    locked_ids: set[int] | None = None,
    locked_assigned_by_deck: dict[int, dict[str, int]] | None = None,
) -> bool:
    """True if at least one size-``n`` combination fits (short-circuit)."""
    combos, _ = enumerate_viable_combinations(
        deck_ids,
        requirements_by_deck,
        stock,
        n=n,
        respect_locks=respect_locks,
        locked_ids=locked_ids,
        locked_assigned_by_deck=locked_assigned_by_deck,
        limit=1,
    )
    return bool(combos)


def solve_max_viable_size(
    deck_ids: list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    *,
    respect_locks: bool = False,
    locked_ids: set[int] | None = None,
    locked_assigned_by_deck: dict[int, dict[str, int]] | None = None,
    min_size: int = 2,
) -> int:
    """Largest M via SCIP ILP; 0 if none ≥ ``min_size`` (or solver unavailable)."""
    if len(deck_ids) < min_size:
        return 0
    locks = locked_ids or set()
    assigned = locked_assigned_by_deck or {}

    try:
        from ortools.linear_solver import pywraplp
    except ImportError:
        return find_max_viable_size_scan(
            deck_ids,
            requirements_by_deck,
            stock,
            respect_locks=respect_locks,
            locked_ids=locks,
            locked_assigned_by_deck=assigned,
            min_size=min_size,
        )

    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        return find_max_viable_size_scan(
            deck_ids,
            requirements_by_deck,
            stock,
            respect_locks=respect_locks,
            locked_ids=locks,
            locked_assigned_by_deck=assigned,
            min_size=min_size,
        )

    variables = {
        deck_id: solver.BoolVar(f"d_{deck_id}") for deck_id in deck_ids
    }

    if respect_locks and locks:
        assigned_all = _assigned_all_locked(locks, assigned)
        pool = _pool_after_locks(stock, assigned_all)
        coeffs = {
            deck_id: _deck_pool_demand(
                deck_id, requirements_by_deck, locks, assigned
            )
            for deck_id in deck_ids
        }
        card_ids = set(pool)
        for cards in coeffs.values():
            card_ids.update(cards)
        for card_id in card_ids:
            constraint = solver.Constraint(0, pool.get(card_id, 0))
            for deck_id, cards in coeffs.items():
                qty = cards.get(card_id, 0)
                if qty:
                    constraint.SetCoefficient(variables[deck_id], qty)
    else:
        card_ids: set[str] = set()
        for cards in requirements_by_deck.values():
            card_ids.update(cards)
        for card_id in card_ids:
            constraint = solver.Constraint(0, stock.get(card_id, 0))
            for deck_id in deck_ids:
                qty = requirements_by_deck.get(deck_id, {}).get(card_id, 0)
                if qty:
                    constraint.SetCoefficient(variables[deck_id], qty)

    objective = solver.Objective()
    for variable in variables.values():
        objective.SetCoefficient(variable, 1)
    objective.SetMaximization()

    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL:
        return 0
    max_size = int(round(objective.Value()))
    return max_size if max_size >= min_size else 0


def find_max_viable_size_scan(
    deck_ids: list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    *,
    respect_locks: bool = False,
    locked_ids: set[int] | None = None,
    locked_assigned_by_deck: dict[int, dict[str, int]] | None = None,
    min_size: int = 2,
) -> int:
    """Brute-force max size (existence scan). Prefer ``solve_max_viable_size``."""
    if len(deck_ids) < min_size:
        return 0
    locks = locked_ids or set()
    assigned = locked_assigned_by_deck or {}
    max_found = 0
    for n in range(min_size, len(deck_ids) + 1):
        if any_viable_combination(
            deck_ids,
            requirements_by_deck,
            stock,
            n=n,
            respect_locks=respect_locks,
            locked_ids=locks,
            locked_assigned_by_deck=assigned,
        ):
            max_found = n
        else:
            break
    return max_found


def find_max_viable_size(
    deck_ids: list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    *,
    respect_locks: bool = False,
    locked_ids: set[int] | None = None,
    locked_assigned_by_deck: dict[int, dict[str, int]] | None = None,
    min_size: int = 2,
) -> int:
    """Largest M ≥ ``min_size`` with ≥1 viable combo; else 0."""
    return solve_max_viable_size(
        deck_ids,
        requirements_by_deck,
        stock,
        respect_locks=respect_locks,
        locked_ids=locked_ids,
        locked_assigned_by_deck=locked_assigned_by_deck,
        min_size=min_size,
    )


def enumerate_max_viable_combinations(
    deck_ids: list[int],
    requirements_by_deck: dict[int, dict[str, int]],
    stock: dict[str, int],
    *,
    respect_locks: bool = False,
    locked_ids: set[int] | None = None,
    locked_assigned_by_deck: dict[int, dict[str, int]] | None = None,
    min_size: int = 2,
    limit: int | None = DEFAULT_LIST_LIMIT,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[int, list[tuple[int, ...]], bool]:
    """Return (M, combos of size M, truncated). M=0 and [] if none ≥ min_size."""
    m = find_max_viable_size(
        deck_ids,
        requirements_by_deck,
        stock,
        respect_locks=respect_locks,
        locked_ids=locked_ids,
        locked_assigned_by_deck=locked_assigned_by_deck,
        min_size=min_size,
    )
    if m < min_size:
        return 0, [], False
    if should_stop is not None and should_stop():
        return m, [], True
    combos, truncated = enumerate_viable_combinations(
        deck_ids,
        requirements_by_deck,
        stock,
        n=m,
        respect_locks=respect_locks,
        locked_ids=locked_ids,
        locked_assigned_by_deck=locked_assigned_by_deck,
        limit=limit,
        should_stop=should_stop,
    )
    return m, combos, truncated
