"""Resolve typed text against a filter picker's options (no Qt, so CI can test it).

The subtype and armed-deck pickers used to drop unresolvable input on the
floor: *Add* returned without a word, so an ambiguous or misspelled entry
looked like a dead button. Resolving here lets the dialog disable *Add* and say
why.
"""

from __future__ import annotations

from collections.abc import Container, Sequence
from dataclasses import dataclass
from enum import StrEnum

from mtg_rebuilder.i18n import Translator


class PickerStatus(StrEnum):
    EMPTY = "empty"
    OK = "ok"
    ALREADY = "already"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class PickerResolution:
    status: PickerStatus
    label: str = ""
    index: int = -1

    @property
    def can_add(self) -> bool:
        return self.status is PickerStatus.OK


def resolve_picker_text(
    options: Sequence[str], typed: str, selected: Container[str] = ()
) -> PickerResolution:
    """Match ``typed`` against ``options``: exact wins, else a unique substring."""
    text = typed.strip()
    if not text:
        return PickerResolution(PickerStatus.EMPTY)
    needle = text.casefold()
    exact: list[int] = []
    partial: list[int] = []
    for index, label in enumerate(options):
        folded = label.casefold()
        if folded == needle:
            exact.append(index)
        elif needle in folded:
            partial.append(index)
    candidates = exact or partial
    if not candidates:
        return PickerResolution(PickerStatus.NO_MATCH)
    if len(candidates) > 1:
        return PickerResolution(PickerStatus.AMBIGUOUS)
    index = candidates[0]
    label = options[index]
    if label in selected:
        return PickerResolution(PickerStatus.ALREADY, label, index)
    return PickerResolution(PickerStatus.OK, label, index)


def format_picker_hint(
    resolution: PickerResolution, typed: str, translator: Translator
) -> str:
    """Why *Add* is disabled, or empty when there is nothing to explain."""
    text = typed.strip()
    if resolution.status in (PickerStatus.EMPTY, PickerStatus.OK):
        return ""
    if resolution.status is PickerStatus.ALREADY:
        return translator.t("inventory.filters.picker_already").format(
            name=resolution.label
        )
    if resolution.status is PickerStatus.AMBIGUOUS:
        return translator.t("inventory.filters.picker_ambiguous").format(text=text)
    return translator.t("inventory.filters.picker_no_match").format(text=text)
