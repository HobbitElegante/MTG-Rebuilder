from enum import StrEnum


class DeckStatus(StrEnum):
    ARMED = "ARMED"
    DISMANTLED = "DISMANTLED"


class DeckFormat(StrEnum):
    """Game format tag for a deck list (rules profiles hang off this)."""

    COMMANDER = "COMMANDER"
    OTHER = "OTHER"


class DeckCardRole(StrEnum):
    MAIN = "MAIN"
    COMMANDER = "COMMANDER"
    PARTNER = "PARTNER"
    COMPANION = "COMPANION"
    BACKGROUND = "BACKGROUND"
    TOKEN = "TOKEN"


class ActivityEventType(StrEnum):
    COPIES_ADDED = "COPIES_ADDED"
    COPIES_REMOVED = "COPIES_REMOVED"
    DECK_ARMED = "DECK_ARMED"
    DECK_DISMANTLED = "DECK_DISMANTLED"
    DECK_IMPORTED = "DECK_IMPORTED"
    DECK_DELETED = "DECK_DELETED"
    DECK_LIST_EDITED = "DECK_LIST_EDITED"
    PLAN_APPLIED = "PLAN_APPLIED"
    ACTIVITY_UNDONE = "ACTIVITY_UNDONE"


class ActivityCategory(StrEnum):
    INVENTORY = "inventory"
    DECKS = "decks"
