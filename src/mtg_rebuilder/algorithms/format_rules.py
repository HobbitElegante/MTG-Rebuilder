"""Per-format advisory rule profiles (non-blocking).

Commander reuses :mod:`commander_rules`. Other formats return no issues yet
but expose ``target_size`` / ``evaluate`` so UI and services can dispatch
without hard-coding Commander everywhere.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mtg_rebuilder.algorithms.commander_rules import (
    COMMANDER_DECK_SIZE,
    CommanderCard,
    CommanderRuleIssue,
    evaluate_deck,
)
from mtg_rebuilder.models.enums import DeckFormat


@dataclass(frozen=True)
class FormatProfile:
    format: DeckFormat
    target_size: int | None
    evaluate: Callable[[list[CommanderCard]], list[CommanderRuleIssue]]


def _no_rules(_cards: list[CommanderCard]) -> list[CommanderRuleIssue]:
    return []


def profile_for(deck_format: DeckFormat) -> FormatProfile:
    """Return the advisory rules profile for ``deck_format``."""
    if deck_format is DeckFormat.COMMANDER:
        return FormatProfile(
            format=DeckFormat.COMMANDER,
            target_size=COMMANDER_DECK_SIZE,
            evaluate=evaluate_deck,
        )
    return FormatProfile(
        format=deck_format,
        target_size=None,
        evaluate=_no_rules,
    )
