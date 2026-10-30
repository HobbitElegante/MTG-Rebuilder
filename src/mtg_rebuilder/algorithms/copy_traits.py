"""Physical-copy traits that do not affect oracle identity.

Plans count copies by ``oracle_id``. These fields describe one card: finish,
language, condition, collector number, and which Scryfall printing it is.
Empty means the user has not recorded it yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from mtg_rebuilder.config import UNSPECIFIED_EDITION_LABEL

FINISH_VALUES = ("nonfoil", "foil", "etched", "glossy")
CONDITION_VALUES = ("NM", "LP", "MP", "HP", "DMG")
LANGUAGE_VALUES = ("en", "es", "fr", "de", "it", "pt", "ja", "ko", "zhs", "zht", "ru")


@dataclass(frozen=True)
class CopyTraits:
    """One copy's recorded print facts. ``None`` is unspecified."""

    edition: str | None = None
    finish: str | None = None
    language: str | None = None
    condition: str | None = None
    collector_number: str | None = None
    printing_id: str | None = None


def normalize_edition(value: str | None) -> str | None:
    """Set codes are stored uppercase. Blank and ``-`` mean unspecified."""
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned or cleaned == UNSPECIFIED_EDITION_LABEL:
        return None
    return cleaned[:16]


def normalize_finish(value: str | None) -> str | None:
    """Scryfall finish, or unspecified. Unknown text is dropped."""
    if value is None:
        return None
    cleaned = value.strip().casefold()
    if not cleaned or cleaned == UNSPECIFIED_EDITION_LABEL:
        return None
    if cleaned not in FINISH_VALUES:
        return None
    return cleaned


def normalize_language(value: str | None) -> str | None:
    """Short language code. Blank means unspecified."""
    if value is None:
        return None
    cleaned = value.strip().casefold()
    if not cleaned or cleaned == UNSPECIFIED_EDITION_LABEL:
        return None
    if len(cleaned) > 8 or not cleaned.isalnum():
        return None
    return cleaned


def normalize_condition(value: str | None) -> str | None:
    """Collector grade, or unspecified. Unknown text is dropped."""
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned or cleaned == UNSPECIFIED_EDITION_LABEL:
        return None
    if cleaned not in CONDITION_VALUES:
        return None
    return cleaned


def normalize_collector_number(value: str | None) -> str | None:
    """Collector number as printed. Case is kept (``115a``, ``101★``)."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned == UNSPECIFIED_EDITION_LABEL:
        return None
    return cleaned[:32]


def normalize_printing_id(value: str | None) -> str | None:
    """Scryfall card id of this printing. Blank means no art chosen."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned == UNSPECIFIED_EDITION_LABEL:
        return None
    return cleaned[:36]


def normalize_copy_traits(traits: CopyTraits) -> CopyTraits:
    return CopyTraits(
        edition=normalize_edition(traits.edition),
        finish=normalize_finish(traits.finish),
        language=normalize_language(traits.language),
        condition=normalize_condition(traits.condition),
        collector_number=normalize_collector_number(traits.collector_number),
        printing_id=normalize_printing_id(traits.printing_id),
    )


def sorted_trait_counts(
    counts: dict[str | None, int],
) -> tuple[tuple[str | None, int], ...]:
    """Most copies first; unspecified last."""
    return tuple(
        sorted(
            counts.items(),
            key=lambda item: (item[0] is None, -item[1], item[0] or ""),
        )
    )


def format_trait_summary(
    counts: tuple[tuple[str | None, int], ...],
) -> str | None:
    """``foil`` when they all match, ``foil x2, - x1`` when mixed.

    ``None`` when every copy is unspecified, so the line can be omitted.
    """
    known = [(value, count) for value, count in counts if value]
    if not known:
        return None
    unspecified = sum(count for value, count in counts if not value)
    if len(known) == 1 and unspecified == 0:
        return known[0][0]
    parts = [f"{value} x{count}" for value, count in known]
    if unspecified:
        parts.append(f"{UNSPECIFIED_EDITION_LABEL} x{unspecified}")
    return ", ".join(parts)


def uppercase_codes(
    counts: tuple[tuple[str | None, int], ...],
) -> tuple[tuple[str | None, int], ...]:
    """Show language abbreviations as ``EN``, ``ZHS``. Storage stays lowercase."""
    return tuple(
        (value.upper() if value else value, count) for value, count in counts
    )


def format_copy_trait_line(
    finishes: tuple[tuple[str | None, int], ...],
    languages: tuple[tuple[str | None, int], ...],
    conditions: tuple[tuple[str | None, int], ...],
    collector_numbers: tuple[tuple[str | None, int], ...],
) -> str | None:
    """One preview line, or ``None`` when no copy has any of these recorded."""
    parts: list[str] = []
    for counts in (
        finishes,
        uppercase_codes(languages),
        conditions,
        collector_numbers,
    ):
        text = format_trait_summary(counts)
        if text:
            parts.append(text)
    if not parts:
        return None
    return " · ".join(parts)


def preferred_printing_id(
    copies: list[tuple[str | None, datetime | None, int]],
) -> str | None:
    """Printing of the copy updated last, among copies that have one.

    Each row is ``(printing_id, updated_at, copy_id)``. A missing timestamp
    (rows saved before that column existed) loses to any real update, and
    among those the higher copy id wins.
    """
    best_rank: tuple[int, datetime, int] | None = None
    best_id: str | None = None
    for printing_id, updated_at, copy_id in copies:
        if not printing_id:
            continue
        if updated_at is None:
            rank = (0, datetime.min.replace(tzinfo=timezone.utc), copy_id)
        else:
            stamp = updated_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            rank = (1, stamp, copy_id)
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_id = printing_id
    return best_id


def assign_printing(
    *,
    chosen_id: str | None,
    chosen_set: str | None,
    chosen_collector: str | None,
) -> tuple[str | None, str | None, str | None]:
    """A print chosen in the grid sets the set, number, and printing id.

    Returns ``(edition, collector_number, printing_id)``. A picture keeps all
    three. A typed set and number (no picture) keeps those two and clears the
    id. Choosing unspecified passes three empty values and clears the row.
    """
    return chosen_set, chosen_collector, chosen_id


def merge_printing_choice(
    *,
    edition: str | None,
    collector_number: str | None,
    chosen_id: str | None,
    chosen_set: str | None,
    chosen_collector: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Picking an art sets the printing id.

    Set and collector number are filled only where they are still empty, so a
    choice does not overwrite something the user already recorded. Picking
    unspecified clears the art and leaves set and collector number alone.
    """
    if not chosen_id:
        return edition, collector_number, None
    return (
        edition or chosen_set,
        collector_number or chosen_collector,
        chosen_id,
    )
