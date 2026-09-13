"""Tests for the filter picker resolution behind the *Add* button feedback."""

from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.ui.filter_picker import (
    PickerStatus,
    format_picker_hint,
    resolve_picker_text,
)

OPTIONS = ("Elf", "Elemental", "Equipment", "Goblin")


def test_blank_text_is_empty_not_an_error() -> None:
    resolution = resolve_picker_text(OPTIONS, "   ")
    assert resolution.status is PickerStatus.EMPTY
    assert not resolution.can_add


def test_matching_ignores_case() -> None:
    resolution = resolve_picker_text(OPTIONS, "elf")
    assert resolution.status is PickerStatus.OK
    assert resolution.label == "Elf"
    assert resolution.index == 0


def test_exact_match_beats_a_partial_one() -> None:
    resolution = resolve_picker_text(("Elf", "Elf Warrior"), "Elf")
    assert resolution.status is PickerStatus.OK
    assert resolution.label == "Elf"


def test_unique_substring_resolves() -> None:
    resolution = resolve_picker_text(OPTIONS, "quip")
    assert resolution.status is PickerStatus.OK
    assert resolution.label == "Equipment"


def test_several_substring_matches_are_ambiguous() -> None:
    resolution = resolve_picker_text(OPTIONS, "El")
    assert resolution.status is PickerStatus.AMBIGUOUS
    assert not resolution.can_add


def test_unknown_text_does_not_match() -> None:
    resolution = resolve_picker_text(OPTIONS, "Sliver")
    assert resolution.status is PickerStatus.NO_MATCH
    assert not resolution.can_add


def test_already_selected_is_reported_separately() -> None:
    resolution = resolve_picker_text(OPTIONS, "Goblin", selected={"Goblin"})
    assert resolution.status is PickerStatus.ALREADY
    assert resolution.label == "Goblin"
    assert not resolution.can_add


def test_hints_are_silent_only_when_there_is_nothing_to_say() -> None:
    translator = Translator("en")
    assert not format_picker_hint(
        resolve_picker_text(OPTIONS, ""), "", translator
    )
    assert not format_picker_hint(
        resolve_picker_text(OPTIONS, "Elf"), "Elf", translator
    )


def test_each_failure_explains_itself() -> None:
    translator = Translator("en")
    ambiguous = format_picker_hint(
        resolve_picker_text(OPTIONS, "El"), "El", translator
    )
    missing = format_picker_hint(
        resolve_picker_text(OPTIONS, "Sliver"), "Sliver", translator
    )
    already = format_picker_hint(
        resolve_picker_text(OPTIONS, "Elf", selected={"Elf"}), "Elf", translator
    )

    assert "El" in ambiguous
    assert "Sliver" in missing
    assert "Elf" in already
    assert len({ambiguous, missing, already}) == 3


def test_hints_are_translated() -> None:
    resolution = resolve_picker_text(OPTIONS, "Sliver")
    english = format_picker_hint(resolution, "Sliver", Translator("en"))
    spanish = format_picker_hint(resolution, "Sliver", Translator("es"))
    assert english and spanish
    assert english != spanish
