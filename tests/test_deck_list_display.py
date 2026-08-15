from mtg_rebuilder.models.enums import DeckFormat, DeckStatus
from mtg_rebuilder.ui.deck_list_display import (
    DeckListRow,
    coerce_deck_format,
    coerce_deck_status,
    filter_deck_rows,
    sort_deck_rows,
)


def _row(
    deck_id: int,
    name: str,
    status: DeckStatus,
    sort_order: int,
    *,
    commander: str | None = None,
    deck_format: DeckFormat = DeckFormat.COMMANDER,
) -> DeckListRow:
    return DeckListRow(
        id=deck_id,
        name=name,
        status=status,
        sort_order=sort_order,
        is_locked=False,
        commander_name=commander,
        has_warning=False,
        tooltip="",
        format=deck_format,
    )


def test_coerce_deck_status_from_qt_userdata() -> None:
    # QComboBox returns StrEnum items as plain str.
    assert coerce_deck_status("ARMED") is DeckStatus.ARMED
    assert coerce_deck_status("DISMANTLED") is DeckStatus.DISMANTLED
    assert coerce_deck_status(DeckStatus.ARMED) is DeckStatus.ARMED
    assert coerce_deck_status(None) is None
    assert coerce_deck_status("nope") is None
    assert coerce_deck_status(1) is None


def test_coerce_deck_format_from_qt_userdata() -> None:
    assert coerce_deck_format("COMMANDER") is DeckFormat.COMMANDER
    assert coerce_deck_format("OTHER") is DeckFormat.OTHER
    assert coerce_deck_format(DeckFormat.COMMANDER) is DeckFormat.COMMANDER
    assert coerce_deck_format(None) is None
    assert coerce_deck_format("nope") is None
    assert coerce_deck_format(1) is None


def test_filter_deck_rows_by_status_and_search() -> None:
    rows = [
        _row(1, "Alpha", DeckStatus.ARMED, 0, commander="Kellan"),
        _row(2, "Bravo", DeckStatus.DISMANTLED, 1, commander="Anje"),
        _row(3, "Charlie", DeckStatus.ARMED, 2, commander="Ghen"),
    ]
    armed = filter_deck_rows(rows, status=DeckStatus.ARMED, needle="")
    assert [r.name for r in armed] == ["Alpha", "Charlie"]

    by_commander = filter_deck_rows(rows, status=None, needle="anje")
    assert [r.name for r in by_commander] == ["Bravo"]

    by_name = filter_deck_rows(rows, status=DeckStatus.ARMED, needle="char")
    assert [r.name for r in by_name] == ["Charlie"]


def test_filter_deck_rows_by_format() -> None:
    rows = [
        _row(1, "Alpha", DeckStatus.ARMED, 0, deck_format=DeckFormat.COMMANDER),
        _row(2, "Bravo", DeckStatus.DISMANTLED, 1, deck_format=DeckFormat.OTHER),
        _row(3, "Charlie", DeckStatus.ARMED, 2, deck_format=DeckFormat.COMMANDER),
    ]
    commander = filter_deck_rows(
        rows, status=None, needle="", deck_format=DeckFormat.COMMANDER
    )
    assert [r.name for r in commander] == ["Alpha", "Charlie"]

    other = filter_deck_rows(
        rows, status=None, needle="", deck_format=DeckFormat.OTHER
    )
    assert [r.name for r in other] == ["Bravo"]

    all_formats = filter_deck_rows(rows, status=None, needle="")
    assert [r.name for r in all_formats] == ["Alpha", "Bravo", "Charlie"]


def test_sort_deck_rows_number_name_status() -> None:
    rows = [
        _row(1, "Charlie", DeckStatus.ARMED, 2),
        _row(2, "Alpha", DeckStatus.DISMANTLED, 0),
        _row(3, "Bravo", DeckStatus.ARMED, 1),
    ]

    by_number = sort_deck_rows(
        rows,
        key="number",
        ascending=True,
        status_label=lambda s: s.value,
    )
    assert [r.name for r in by_number] == ["Alpha", "Bravo", "Charlie"]

    by_name_desc = sort_deck_rows(
        rows,
        key="name",
        ascending=False,
        status_label=lambda s: s.value,
    )
    assert [r.name for r in by_name_desc] == ["Charlie", "Bravo", "Alpha"]

    def label(status: DeckStatus) -> str:
        return "Armado" if status == DeckStatus.ARMED else "Desarmado"

    by_status = sort_deck_rows(
        rows, key="status", ascending=True, status_label=label
    )
    assert [r.name for r in by_status] == ["Charlie", "Bravo", "Alpha"]
