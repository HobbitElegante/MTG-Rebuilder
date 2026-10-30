from pathlib import Path

import pytest

import httpx

from mtg_rebuilder.api.archidekt_client import deck_export_from_payload as archidekt_export
from mtg_rebuilder.api.moxfield_client import (
    MoxfieldClient,
    MoxfieldError,
    deck_export_from_payload,
)
from mtg_rebuilder.models.enums import DeckCardRole
from mtg_rebuilder.services.decklist_parser import (
    DecklistFormat,
    detect_format,
    extract_archidekt_deck_id,
    extract_moxfield_deck_id,
    parse_decklist,
    parse_moxfield_line,
)


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("line", "expected_name"),
    [
        ("1 Catalog (PLST) SOI-51", "Catalog"),
        ("1 Clear the Mind (PLST) RNA-34", "Clear the Mind"),
        ("1 Deep Freeze (PLST) DOM-50", "Deep Freeze"),
        ("1 Turn Aside (PLST) EMN-78", "Turn Aside"),
        ("1 Borrowing 100,000 Arrows (PLST) A25-45", "Borrowing 100,000 Arrows"),
        ("1 Amoeboid Changeling (PLST) LRW-51", "Amoeboid Changeling"),
        ("1 Urza's Power Plant (CHR) 115a", "Urza's Power Plant"),
        ("1 Consider (PW22) 1", "Consider"),
        ("1 Opt (J25) 339 *F*", "Opt"),
        ("1x Sol Ring (C21) [Ramp]", "Sol Ring"),
        ("1 Sol Ring", "Sol Ring"),
    ],
)
def test_parse_strips_set_and_collector_number(line: str, expected_name: str) -> None:
    parsed = parse_moxfield_line(line)
    assert parsed is not None
    assert parsed.name == expected_name
    assert parsed.quantity == 1


def test_moxfield_export_keeps_collector_number_and_foil() -> None:
    payload = {
        "publicId": "pub",
        "name": "Foils",
        "mainboard": {
            "Sol Ring": {
                "quantity": 1,
                "card": {
                    "name": "Sol Ring",
                    "set": "c21",
                    "cn": "263",
                    "finish": "foil",
                },
            },
            "Arcane Signet": {
                "quantity": 1,
                "card": {"name": "Arcane Signet", "set": "c21", "finish": "nonfoil"},
            },
        },
    }
    export = deck_export_from_payload(payload)
    assert "1 Sol Ring (C21) 263 *F*" in export.list_text
    assert "1 Arcane Signet" in export.list_text
    parsed = {line.name: line for line in parse_decklist(export.list_text)}
    assert parsed["Sol Ring"].foil is True
    assert parsed["Sol Ring"].collector_number == "263"
    assert parsed["Arcane Signet"].foil is False


def test_archidekt_export_keeps_collector_number_and_foil() -> None:
    payload = {
        "id": 1,
        "name": "Numbers",
        "categories": [{"name": "Land", "includedInDeck": True}],
        "cards": [
            {
                "quantity": 1,
                "foil": True,
                "categories": ["Land"],
                "card": {
                    "oracleCard": {"name": "Command Tower"},
                    "edition": {"editioncode": "c21"},
                    "collectorNumber": "284",
                },
            }
        ],
    }
    export = archidekt_export(payload)
    assert "1 Command Tower (C21) 284 *F*" in export.list_text
    parsed = parse_decklist(export.list_text)
    assert parsed[0].collector_number == "284"
    assert parsed[0].foil is True


def test_parse_kellan_deck_export() -> None:
    text = (FIXTURES / "kellan_deck.txt").read_text(encoding="utf-8")
    parsed = parse_decklist(text)

    assert len(parsed) == 79
    assert parsed[0].name == "Adarkar Wastes"
    assert parsed[0].quantity == 1

    forests = [line for line in parsed if line.name == "Forest"]
    assert len(forests) == 1
    assert forests[0].quantity == 10

    assert parsed[-1].name == "Kellan, the Kid"
    assert parsed[-1].quantity == 1


def test_parse_role_prefix() -> None:
    text = "Commander: 1 Atraxa, Praetors' Voice\n1 Sol Ring"
    parsed = parse_decklist(text)
    assert parsed[0].role == DeckCardRole.COMMANDER
    assert parsed[0].name == "Atraxa, Praetors' Voice"
    assert parsed[1].name == "Sol Ring"


def test_skips_blank_and_comment_lines() -> None:
    text = "// Sideboard\n\n1 Sol Ring\n"
    parsed = parse_decklist(text)
    assert len(parsed) == 1
    assert parsed[0].name == "Sol Ring"


def test_detect_and_parse_arena_fixture() -> None:
    text = (FIXTURES / "arena_sample.txt").read_text(encoding="utf-8")
    assert detect_format(text) == DecklistFormat.ARENA
    parsed = parse_decklist(text)
    names = {line.name: line for line in parsed}
    assert names["Atraxa, Praetors' Voice"].role == DeckCardRole.COMMANDER
    assert "Sol Ring" in names
    assert "Negate" not in names  # sideboard skipped


def test_detect_and_parse_archidekt_fixture() -> None:
    text = (FIXTURES / "archidekt_sample.txt").read_text(encoding="utf-8")
    assert detect_format(text) == DecklistFormat.ARCHIDEKT
    parsed = parse_decklist(text)
    names = {line.name for line in parsed}
    assert names == {
        "Sol Ring",
        "Arcane Signet",
        "Birds of Paradise",
        "Eternal Witness",
        "Lightning Greaves",
    }


def test_detect_and_parse_mtgo_dek_fixture() -> None:
    text = (FIXTURES / "mtgo_sample.dek").read_text(encoding="utf-8")
    assert detect_format(text) == DecklistFormat.MTGO_DEK
    parsed = parse_decklist(text)
    names = {line.name: line.quantity for line in parsed}
    assert names == {"Sol Ring": 1, "Arcane Signet": 1}


def test_extract_moxfield_deck_id() -> None:
    assert (
        extract_moxfield_deck_id("https://www.moxfield.com/decks/AbC_123-xyz")
        == "AbC_123-xyz"
    )
    assert extract_moxfield_deck_id("1 Sol Ring") is None
    assert detect_format("https://moxfield.com/decks/abc") == DecklistFormat.MOXFIELD_URL
    assert parse_decklist("https://moxfield.com/decks/abc") == []


def test_extract_archidekt_deck_id() -> None:
    assert (
        extract_archidekt_deck_id("https://www.archidekt.com/decks/7031486/buffs")
        == "7031486"
    )
    assert extract_archidekt_deck_id("https://archidekt.com/decks/42") == "42"
    assert extract_archidekt_deck_id("1 Sol Ring") is None
    assert (
        detect_format("https://archidekt.com/decks/7031486/yuriko")
        == DecklistFormat.ARCHIDEKT_URL
    )
    assert parse_decklist("https://archidekt.com/decks/7031486") == []


def test_deck_export_from_archidekt_payload() -> None:
    payload = {
        "id": 99,
        "name": "Archidekt Test",
        "categories": [
            {"name": "Commander", "includedInDeck": True},
            {"name": "Maybeboard", "includedInDeck": False},
            {"name": "Sideboard", "includedInDeck": True},
            {"name": "Tokens", "includedInDeck": True},
            {"name": "Land", "includedInDeck": True},
        ],
        "cards": [
            {
                "quantity": 1,
                "companion": False,
                "categories": ["Commander"],
                "card": {
                    "oracleCard": {"name": "Tymna the Weaver"},
                    "edition": {"editioncode": "c16"},
                },
            },
            {
                "quantity": 1,
                "companion": False,
                "categories": ["Commander"],
                "card": {
                    "oracleCard": {"name": "Kraum, Ludevic's Opus"},
                    "edition": {"editioncode": "c16"},
                },
            },
            {
                "quantity": 1,
                "companion": False,
                "categories": ["Land"],
                "card": {
                    "oracleCard": {"name": "Command Tower"},
                    "edition": {"editioncode": "c21"},
                },
            },
            {
                "quantity": 1,
                "companion": False,
                "categories": ["Maybeboard", "Land"],
                "card": {"oracleCard": {"name": "Fabled Passage"}},
            },
            {
                "quantity": 1,
                "companion": False,
                "categories": ["Sideboard"],
                "card": {"oracleCard": {"name": "Duress"}},
            },
            {
                "quantity": 1,
                "companion": True,
                "categories": ["Sideboard"],
                "card": {"oracleCard": {"name": "Lurrus of the Dream-Den"}},
            },
            {
                "quantity": 2,
                "companion": False,
                "categories": ["Tokens"],
                "card": {"oracleCard": {"name": "Treasure"}},
            },
        ],
    }
    export = archidekt_export(payload)
    assert export.name == "Archidekt Test"
    assert export.commander_name == "Tymna the Weaver"
    assert export.secondary_role == "partner"
    assert export.secondary_name == "Kraum, Ludevic's Opus"
    assert "Commander: 1 Tymna the Weaver (C16)" in export.list_text
    assert "Partner: 1 Kraum, Ludevic's Opus (C16)" in export.list_text
    assert "Companion: 1 Lurrus of the Dream-Den" in export.list_text
    assert "1 Command Tower (C21)" in export.list_text
    assert "Fabled Passage" not in export.list_text
    assert "Duress" not in export.list_text
    assert "Treasure" not in export.list_text
    parsed = parse_decklist(export.list_text)
    roles = {line.name: line.role for line in parsed}
    assert roles["Tymna the Weaver"] == DeckCardRole.COMMANDER
    assert roles["Kraum, Ludevic's Opus"] == DeckCardRole.PARTNER
    assert roles["Lurrus of the Dream-Den"] == DeckCardRole.COMPANION


def test_deck_export_from_moxfield_payload() -> None:
    payload = {
        "publicId": "pub1",
        "name": "Test Deck",
        "commanders": {
            "Atraxa, Praetors' Voice": {
                "quantity": 1,
                "card": {"name": "Atraxa, Praetors' Voice"},
            }
        },
        "companions": {},
        "mainboard": {
            "Sol Ring": {"quantity": 1, "card": {"name": "Sol Ring"}},
            "Arcane Signet": {"quantity": 1, "card": {"name": "Arcane Signet"}},
        },
        "tokens": [
            {
                "name": "Angel",
                "isToken": True,
                "type_line": "Token Creature — Angel",
            },
        ],
    }
    export = deck_export_from_payload(payload)
    assert export.name == "Test Deck"
    assert export.commander_name == "Atraxa, Praetors' Voice"
    assert "Commander: 1 Atraxa, Praetors' Voice" in export.list_text
    assert "1 Sol Ring" in export.list_text
    # Tokens are ignored — not stored on deck lists.
    assert "Token:" not in export.list_text
    assert "Angel" not in export.list_text
    parsed = parse_decklist(export.list_text)
    assert any(line.role == DeckCardRole.COMMANDER for line in parsed)


def test_deck_export_from_moxfield_v3_boards_payload() -> None:
    payload = {
        "publicId": "pub2",
        "name": "V3 Deck",
        "boards": {
            "commanders": {
                "count": 1,
                "cards": {
                    "Kellan": {
                        "quantity": 1,
                        "card": {"name": "Kellan, the Fae-Blooded"},
                    }
                },
            },
            "mainboard": {
                "count": 1,
                "cards": {
                    "sol": {"quantity": 1, "card": {"name": "Sol Ring"}},
                },
            },
            "tokens": {
                "count": 1,
                "cards": {
                    "treasure": {
                        "quantity": 2,
                        "card": {"name": "Treasure"},
                    }
                },
            },
            "companions": {"count": 0, "cards": {}},
            "backgrounds": {"count": 0, "cards": {}},
        },
    }
    export = deck_export_from_payload(payload)
    assert export.commander_name == "Kellan, the Fae-Blooded"
    assert "Commander: 1 Kellan, the Fae-Blooded" in export.list_text
    assert "1 Sol Ring" in export.list_text
    assert "Token:" not in export.list_text
    assert "Treasure" not in export.list_text


def test_moxfield_client_maps_403_to_friendly_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"title": "Forbidden"})

    client = MoxfieldClient(
        httpx.Client(
            base_url="https://api2.moxfield.com",
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        with pytest.raises(MoxfieldError) as raised:
            client.fetch_deck("abc")
    finally:
        client.close()
    assert raised.value.code == "forbidden"


def test_moxfield_client_retries_403_with_browser_headers() -> None:
    seen_agents: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_agents.append(request.headers.get("user-agent", ""))
        if "Chrome/" in request.headers.get("user-agent", ""):
            return httpx.Response(
                200,
                json={
                    "publicId": "abc",
                    "name": "Rocco",
                    "boards": {
                        "commanders": {
                            "count": 1,
                            "cards": {
                                "r": {
                                    "quantity": 1,
                                    "card": {"name": "Rocco, Cabaretti Caterer"},
                                }
                            },
                        },
                        "mainboard": {"count": 0, "cards": {}},
                    },
                },
            )
        return httpx.Response(403, json={"title": "Forbidden"})

    client = MoxfieldClient(
        httpx.Client(
            base_url="https://api2.moxfield.com",
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        payload = client.fetch_deck("abc")
    finally:
        client.close()

    assert payload["name"] == "Rocco"
    assert len(seen_agents) >= 2
    assert any("Chrome/" in agent for agent in seen_agents)


def test_moxfield_client_maps_404_to_friendly_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"title": "Not Found"})

    client = MoxfieldClient(
        httpx.Client(
            base_url="https://api2.moxfield.com",
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        with pytest.raises(MoxfieldError) as raised:
            client.fetch_deck("missing")
    finally:
        client.close()
    assert raised.value.code == "not_found"
