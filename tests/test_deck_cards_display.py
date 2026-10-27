from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.models.enums import DeckCardRole
from mtg_rebuilder.services.deck_service import CardListStock, DeckCardSummary
from mtg_rebuilder.ui.deck_cards_display import (
    COMMAND_GROUP,
    format_card_stock_text,
    group_deck_cards,
    primary_card_type,
    sort_deck_cards,
)


def _card(
    name: str,
    *,
    cmc: float | None = None,
    type_line: str | None = None,
    role: DeckCardRole = DeckCardRole.MAIN,
    quantity: int = 1,
) -> DeckCardSummary:
    return DeckCardSummary(
        oracle_id=f"oid-{name}",
        name=name,
        quantity=quantity,
        role=role,
        cmc=cmc,
        type_line=type_line,
    )


def test_primary_card_type_precedence() -> None:
    assert primary_card_type("Creature — Elf") == "Creature"
    # Multi-type cards bucket once, creatures first.
    assert primary_card_type("Artifact Creature — Golem") == "Creature"
    assert primary_card_type("Legendary Enchantment Creature — God") == "Creature"
    assert primary_card_type("Artifact — Equipment") == "Artifact"
    # Any land goes to the Land bucket, even artifact lands.
    assert primary_card_type("Artifact Land") == "Land"
    assert primary_card_type("Basic Land — Island") == "Land"
    # DFCs classify by their front face.
    assert primary_card_type("Sorcery // Land") == "Sorcery"
    assert primary_card_type("Kindred Sorcery — Elf") == "Sorcery"
    assert primary_card_type(None) == "Other"
    assert primary_card_type("Conspiracy") == "Other"


def test_sort_deck_cards_alphabetical_pins_command_zone() -> None:
    cards = [
        _card("Zephyr", cmc=1.0, type_line="Instant"),
        _card("Anvil", cmc=2.0, type_line="Artifact"),
        _card(
            "Kellan",
            cmc=3.0,
            type_line="Legendary Creature — Human",
            role=DeckCardRole.COMMANDER,
        ),
    ]
    asc = sort_deck_cards(cards, key="alphabetical", ascending=True)
    assert [c.name for c in asc] == ["Kellan", "Anvil", "Zephyr"]

    desc = sort_deck_cards(cards, key="alphabetical", ascending=False)
    # Commander stays first; only the main cards flip.
    assert [c.name for c in desc] == ["Kellan", "Zephyr", "Anvil"]


def test_sort_deck_cards_by_mana_value_with_name_tiebreak() -> None:
    cards = [
        _card("Bolt", cmc=1.0, type_line="Instant"),
        _card("Wrath", cmc=4.0, type_line="Sorcery"),
        _card("Anvil", cmc=1.0, type_line="Artifact"),
        _card("Island", cmc=None, type_line="Basic Land — Island"),
    ]
    asc = sort_deck_cards(cards, key="mana_value", ascending=True)
    # Missing cmc counts as 0; ties read alphabetically in both directions.
    assert [c.name for c in asc] == ["Island", "Anvil", "Bolt", "Wrath"]

    desc = sort_deck_cards(cards, key="mana_value", ascending=False)
    assert [c.name for c in desc] == ["Wrath", "Anvil", "Bolt", "Island"]


def test_group_deck_cards_by_type() -> None:
    cards = [
        _card("Sol Ring", cmc=1.0, type_line="Artifact"),
        _card("Llanowar Elves", cmc=1.0, type_line="Creature — Elf Druid"),
        _card("Ornithopter", cmc=0.0, type_line="Artifact Creature — Thopter"),
        _card("Forest", cmc=None, type_line="Basic Land — Forest"),
        _card(
            "Ghen",
            cmc=3.0,
            type_line="Legendary Creature — Orc Shaman",
            role=DeckCardRole.COMMANDER,
        ),
    ]
    groups = group_deck_cards(cards, key="alphabetical", ascending=True)
    assert [group for group, _ in groups] == [COMMAND_GROUP, "Creature", "Artifact", "Land"]
    contents = {group: [c.name for c in members] for group, members in groups}
    assert contents[COMMAND_GROUP] == ["Ghen"]
    assert contents["Creature"] == ["Llanowar Elves", "Ornithopter"]
    assert contents["Artifact"] == ["Sol Ring"]
    assert contents["Land"] == ["Forest"]


def test_group_deck_cards_sorts_within_groups() -> None:
    cards = [
        _card("Wrath of God", cmc=4.0, type_line="Sorcery"),
        _card("Ponder", cmc=1.0, type_line="Sorcery"),
        _card("Blasphemous Act", cmc=9.0, type_line="Sorcery"),
    ]
    groups = group_deck_cards(cards, key="mana_value", ascending=False)
    assert groups[0][0] == "Sorcery"
    assert [c.name for c in groups[0][1]] == [
        "Blasphemous Act",
        "Wrath of God",
        "Ponder",
    ]


def test_format_card_stock_text_counts_and_basics() -> None:
    stock = CardListStock(total_copies=4, free_copies=1, decks_using=3)
    english = format_card_stock_text(stock, Translator("en"), is_basic_land=False)
    assert english == (
        "Copies in inventory: 4\nFree copies: 1\nDecks using it: 3"
    )
    spanish = format_card_stock_text(stock, Translator("es"), is_basic_land=False)
    assert spanish == (
        "Copias en inventario: 4\nCopias libres: 1\nMazos que la usan: 3"
    )
    basic = format_card_stock_text(
        CardListStock(total_copies=0, free_copies=0, decks_using=8),
        Translator("es"),
        is_basic_land=True,
    )
    assert basic == (
        "Copias en inventario: ilimitadas\n"
        "Copias libres: ilimitadas\n"
        "Mazos que la usan: 8"
    )
