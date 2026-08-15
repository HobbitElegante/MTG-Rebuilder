# MTG Commander Collection Manager

Desktop application to manage a physical Magic: The Gathering Commander collection and compute optimal deck reassembly plans using integer linear programming (OR-Tools).

## Features

**MTG-Rebuilder** (repo / package / binaries). The window title remains *MTG Commander Collection Manager*.

Prebuilt **Downloads** below track **`v1.1.0`** once that tag is published (free-size **Edit list**, per-deck **format tag**, Decks **Format** filter, **Update list** → qty/Free dialog). Until then, `/releases/latest` may still show **v1.0.0**.

### Collection

- Physical inventory in SQLite, grouped by card: total / free / assigned
- Inventory table: Name · CMC · Colors (WUBRG) · **Rarity** (C/U/R/M; sort C→U→R→M) · Total · Free · Assigned · In decks; sortable columns; **read-only cells** (edit only via Edit copy count)
- Search by card name; **Filter** dialog for type, armed-deck exclusion, color identity (`id≤`), **rarity (C/U/R/M)**, and mana value
- **Image view** *(requires card images on)*: virtualized grid ≤5 faces/row; on-demand download as tiles appear; **Sort by** + Asc/Desc without leaving the grid (same order as the table); field list under the side preview
- Add a single card or paste a whole list (multi-format / Moxfield or Archidekt URL) into free inventory
- Optional **edition tracking**: turn it on in Browse → Customize to get an Edition column, per-copy set codes, and a prompt after rebuilding a deck
- Card image preview beside the table (on-demand download; flip for double-faced cards)

### Decks

- Import with auto-detect: Moxfield MTGO, Archidekt, Arena, MTGO `.dek`, or public Moxfield / Archidekt URL
- Armed / dismantled status with automatic physical-copy assignment
- **Format tag** per deck (default **EDH / Commander**; stub Other with no rules yet). Shown in the deck list and details; picker on import and Edit name / commander
- Command zone: commander plus optional Partner / Companion / Background
- **Edit list** (free size/quantities; `{current}/{target}` with a soft ⚠ if the format size does not match; never blocks save), **Update list** (paste/file/URL then the same qty + Free-copies table so you can add physical copies or keep inventory), export (5 formats), delete
- Search, filter by **format** (All / EDH·Commander for now) and status, ephemeral sort (number / name / armed status), and reorder decks (Move up/down when sorted by number ascending)
- Selected deck: commander preview, full card list, and preview of the selected card (Partner / Companion / Background appear in the list)
- Card list display controls above the selected-card preview: sort by mana value or alphabetically (ascending/descending) and **group by type** (Command zone / Creatures / Instants / … / Lands headers)
- Deck statistics around the commander: lands / x̄ mana value (with and without lands) / type breakdown / mana pips above, and a mana-curve bar chart below (creatures vs non-creature, lands excluded); both hide automatically when the window is small
- Advisory ⚠ that never blocks: Scryfall Commander legality, game-rule checks, and optional **house banlist** (Customize); legality/rules visibility is toggleable
- Lock / unlock a deck so Optimize will not dismantle it (ɸ in the list)

### Optimize

- ILP plan: minimize how many **armed** decks to dismantle to assemble a target
- **Armed set:** add decks you want armed at the same time (including already-armed ones to keep); viability is for the whole set
- **Locked decks** (Decks tab, ɸ): permanent — Optimize will not dismantle them; cards they hold still appear under Still missing
- Armed decks in the plan are kept without locking them in Decks (session-only keep)
- Equally optimal plans are ordered so the one drawing the most cards from a single donor comes first; every plan stays selectable
- Confirm / cancel to apply; searchable target picker; clear status when already armed or infeasible
- Free inventory + unlimited basics count toward coverage; tokens are ignored (not stored on lists)
- **Viable plans** sub-tab: explore which sets of N decks fit physical stock (names only). Cache per N/ɸ, background calculate, filter by deck (only decks that appear in results), collapsible combination groups, commander image grid / inline image view, **Send to assembly plan** (alphabetical queue)

### Browse & data

- Offline card cache via Scryfall bulk (`oracle_cards` / optional `unique_artwork`); Art Series excluded; reversible prints handled in unique-artwork sync
- Local JPEGs under `data/images/`; refresh legality + image URLs for the collection without a full re-bulk
- Browse: Overview, **Customize** (display incl. dark/light/system theme — default dark, warning toggles, house banlist), card search, availability (name filter), activity **History** (filter, load more, CSV, undo / redo last), Scryfall
- UI in English or Spanish; theme preference persisted (new installs default to dark)

## Download

Prebuilt binaries: **https://github.com/HobbitElegante/MTG-Rebuilder/releases/latest**

- Linux: `.AppImage` — `chmod +x` then run.
  - Optional application menu:
    ```bash
    chmod +x MTG-Rebuilder-*.AppImage
    ./scripts/install_linux_desktop.sh /path/to/MTG-Rebuilder-*.AppImage
    ```
    (`--uninstall` removes the menu entry and the copied AppImage; your database stays in the user-data folder.)
- Windows: `.zip` — unzip and run `MTG-Rebuilder.exe`.

Feedback: [Issues](https://github.com/HobbitElegante/MTG-Rebuilder/issues) · [Discussions](https://github.com/HobbitElegante/MTG-Rebuilder/discussions) · Support: [Ko-fi](https://ko-fi.com/hobbitelegante)

Local development setup is below.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Setup

```bash
cd MTG-Rebuilder
uv sync --all-extras
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uv run mtg-rebuilder
```

Or:

```bash
python -m mtg_rebuilder
```

In development, the SQLite database is created at `data/mtg_rebuilder.db` (gitignored) and optional card images under `data/images/`. Packaged builds (AppImage / Windows folder) store the same files in the platform user-data directory; override anytime with `MTG_REBUILDER_DATA_DIR`. On every launch, Alembic applies any pending schema migrations automatically (fresh clone → baseline schema; older local DBs → one-time bridge + stamp).

## Tests

```bash
uv run pytest
```

299 tests passing locally (includes path-migration cases after rename).

## First-time setup

1. Run the app.
2. **Browse → Scryfall → Download oracle-cards bulk pack** (one-time, ~170 MB, requires network).
3. Optional: **Use unique-artwork** for better default art; **Download images (collection)** for local JPEGs of owned/list cards.
4. Import decks from the **Decks** tab (**Import new list**). New lists default to **EDH / Commander**; you can change the format tag on import or later under **Edit name / commander**.
5. Optional: **Browse → Customize** → switch language or theme (dark default; also light / system), toggle images / edition tracking / deck warnings, or edit the house banlist (all persisted).

## Importing a deck

1. Open the **Decks** tab → **Import new list** (form fills the whole tab).
2. Enter deck name, **format** (default EDH / Commander), and optional commander; use **+** for Partner, Companion, or Background if needed (a Moxfield URL can fill commander/secondary for you).
3. Paste the list, a public **Moxfield** or **Archidekt** deck URL, or click **Load file** (`.txt` / `.dek`).
4. Click **Confirm list**. If you pasted a deck URL, the app downloads the deck, fills the form, and asks you to confirm again after review.
5. Choose **Armed** or **Dismantled**:
   - **Armed:** physical copies are created/assigned automatically. Shared cards across armed decks get additional copies.
   - **Dismantled:** mark which cards from the list you still have available (−/+) → free inventory copies.

Supported paste formats (auto-detected): Moxfield `Copy for MTGO`, Archidekt text, MTG Arena (`Commander` / `Deck` sections), MTGO `.dek` XML.

Export from Moxfield: `More → Export → Copy for MTGO` (or paste the deck URL). Archidekt: paste the public deck URL, or export text.

## Editing, updating, exporting, and deleting decks

- **Edit list:** table of cards with list quantity (−/+), free inventory (−/+), replace, and **Add** (no size cap). Header shows `{current}/{target}` for the deck’s format (e.g. 92/100 in Commander; Companion is excluded from the count) and a soft ⚠ if they differ — save is never blocked. Cards that are banned / not legal / restricted in Commander show ⚠ on the right of the Name column (tooltip; advisory only).
- **Update list:** opens the full-tab panel bound to the selected deck (name locked, format locked, command zone prefilled). Paste a list, load a file, or paste a Moxfield / Archidekt URL, then **Review update** opens the same qty + **Free** table as Edit list (plus before→after count, unrecognized lines, and a hint to raise Free only when you need new physical copies). **Apply update** writes the new list and any Free-copy changes. Armed decks are re-armed automatically.
- **Edit name / commander:** rename the deck; change the **format** tag; set or clear the commander; use **+** to add Partner, Companion, or Background (second card field). Cards must be in the local Scryfall cache.
- **Export list:** opens a dialog with a format picker (MTGO / Moxfield / Arena / Archidekt / MTGGoldfish); copy to clipboard.
- **Delete list:** choose how many removable copies to drop per card; copies on other armed decks are never removed.
- **Filter / sort / reorder:** search by deck or commander name; **Format** (All formats / EDH·Commander for now; more formats later); show All, Armed only, or Dismantled only; sort by number, name, or armed/dismantled (ascending/descending — display only; does not rewrite saved order). Move up / Move down persists custom order and is enabled only when sorted by number ascending (reorder does not refresh Inventory/Browse).
- Selected deck: summary under the deck list (format, coverage / commander / secondary); to the right, commander column · full card list · image of the selected card. Secondary command-zone cards are in the list (no dedicated preview column). The deck list shows `[EDH / Commander] [Armed]` (or Other) next to each name.
- Above the selected-card image (separated from the deck filter row by a divider): **Filter by** mana value / alphabetical plus an ascending/descending toggle, and **Group by type** — the list splits into Command zone / Creatures / Instants / Sorceries / Artifacts / Enchantments / Planeswalkers / Battles / Lands / Other headers (a multi-type card lands in its first bucket, e.g. artifact creatures under Creatures; any land under Lands). Display-only and per-session, like the deck sort.
- The commander column also shows deck statistics on top (lands with basics; x̄ mana value without and with lands — hover for “x̄ = average”; type breakdown in a two-column grid; mana pips) and a mana-curve chart at the bottom (X = mana value 0–7+, Y = card count; green = creatures, blue = non-creature; lands excluded). If the window is too short, stats and chart hide so the commander image keeps its space.
- Decks with format-legality or rule issues show ⚠ left of `[EDH / Commander] [Armed|Dismantled]` (hover for details). Rules follow the deck’s format tag (Commander = 100 / singleton / identity; Other = no checks yet).

Tip: **Edit list** can grow or shrink the list (add forgotten lands, change quantities). Use **Update list** when you want to paste/sync a whole list from Moxfield or a file and review Free copies at the same time. The edit dialog table grows when you resize the window.

## Inventory

1. Open the **Inventory** tab.
2. Table columns: **Name** · **CMC** · **Colors** · **Rarity** · **Total** · **Free** · **Assigned** · **In decks** (deck names only, or — if fully free). With edition tracking on, an **Edition** column appears. CMC is the numeric mana value (e.g. GGG → 3; hover the header for the full label). Colors show WUBRG identity (— if colorless). Name is the wide column.
3. Click a column header to sort (text A–Z / Z–A; numbers high→low first, then reverse). Hover **In decks** for the full list when a card is in several decks.
4. Use the search bar to filter by card name. **Filter** opens a dialog for type (search/add), hide cards in armed decks (all or specific), color identity at most (`id≤`), rarity (C/U/R/M), and mana-value comparisons.
5. **Image view** *(next to Filter; requires card images enabled in Customize)* replaces the table with a scrollable grid (up to five faces per row). Missing local JPEGs download in the background as tiles appear. While Image view is on, **Sort by** and ascending/descending reorder the grid using the same keys as the table headers. Select a tile to refresh the side preview and the field list under it.
6. **Add new card to collection** — search the local Scryfall cache and add free copies (−/+). Basics and tokens are excluded (unlimited / not trackable).
7. **Add list to collection** — opens a full-tab paste area (Load file · Confirm list · Cancel). After confirm, adjust how many copies to add per identified card (starts at 1; 0 or Remove excludes), replace mis-resolved cards, and on the right edit unrecognized lines then **Recheck** or **Remove** them. Confirm adds free inventory copies.
8. Select a row (or a grid tile) → **Edit copy count** — change total physical copies (floor = copies assigned to armed decks).
9. The panel on the right shows the selected card and inventory fields. Missing preview images are fetched from Scryfall in the background and cached; drag the splitter to resize it.

## Optimizer

1. Import decks and mark currently assembled ones as **Armed**. Optionally **Lock** (ɸ) decks you never want Optimize to dismantle.
2. For dismantled decks, register available copies during import or while editing.
3. Open **Optimize**, search a deck (armed or dismantled), and click **Add to plan**. Repeat to build the set you want armed together — add already-armed decks to keep them without locking in Decks.
4. With two or more decks, the summary shows whether the **whole set** can be armed at once (N unique donors, or infeasible). Inventory and dismantle panels are grouped per target (`For …` / `Para …`).
5. **Confirm plan** applies every viable step in order; **Cancel** clears the set.
6. If a step has multiple optimal dismantle sets, choose one from its dropdown before confirming.

## Offline Scryfall cache

1. Open **Browse → Scryfall**.
2. Click **Download oracle-cards bulk pack** (one-time, ~170 MB) for offline name resolution. When Scryfall publishes newer data, the button becomes **Update**.
3. Optional: **Use unique-artwork** (~250 MB) for better default card art (still one row per `oracle_id`).
4. Optional: **Download images (collection)** or **Download images (full cache)** — saves Scryfall `normal` JPEGs under `data/images/{oracle_id}.jpg` (skips files already on disk). Bulk download only fetches front faces; back faces arrive on demand when you flip a card.
5. After sync, imports and lookups work offline for cached cards.
6. Individual API lookups are also saved automatically when online.
7. **Refresh card data (collection)** — updates Commander legality and image links for cards you own or have on deck lists (batched Scryfall API; much faster than a full bulk re-download). Use this when banlists change, or after upgrading so ⚠ warnings and back-face images work.
8. **Browse → Cards:** type a name to search; the UI does not load the entire cached catalog at once. Selecting a row shows the card image on the right.

## Project layout

```
src/mtg_rebuilder/
  algorithms/     # ILP optimizer, Commander rules, format-rule profiles, card helpers
  api/            # Scryfall + Moxfield HTTP clients (bulk + CDN image download)
  database/       # SQLite + Alembic (session, migrate, alembic/versions)
  i18n/           # EN/ES translations
  models/         # SQLAlchemy models (ActivityEvent, Card.commander_legality/image_uri_back, …)
  repositories/   # Thin data-access layer (Card, Copy, Deck, Activity, Settings)
  services/       # Business logic / orchestration (uses repositories for SQL)
  ui/             # PySide6 desktop UI (+ deck_list_display, inventory_display, inventory_image_layout, card_preview, inventory_image_grid, …)
tests/
  fixtures/       # Sample exports (kellan, arena, archidekt, mtgo .dek)
scripts/          # build_linux.sh, build_windows.ps1, install_linux_desktop.sh
packaging/        # PyInstaller spec, AppImage .desktop + icon
alembic.ini       # Dev CLI for new revisions (`alembic -c alembic.ini …`)
```

**Changing the schema:** add a revision with `alembic -c alembic.ini revision --autogenerate -m "…"`, review it under `database/alembic/versions/`, then launch the app (migrations run on startup).

## Latest (v1.1.0)

**v1.1.0** folds the post-1.0 deck-format work into a minor release. The window title stays *MTG Commander Collection Manager*. Existing user data under `mtg-sorter` is still migrated automatically on first launch of a packaged build.

- Free-size **Edit list** (`{current}/{target}` soft ⚠; never blocks save)
- Per-deck **format tag** (default **EDH / Commander**; stub Other with no rules yet) — list/detail tag; picker on import and Edit name / commander
- Decks toolbar **Format** filter (All formats / EDH·Commander for now; in-memory with status + search)
- **Update list** → qty + Free-copies dialog after paste (same table as Edit list)
- **v1.0.0:** first stable **MTG-Rebuilder** rename; Inventory **Image view**; Linux `.desktop` install; Optimize **Viable plans**; ASCII **MTG-R**
- **v0.9.6:** Default theme dark; Availability name-only placeholder; Filter tooltips localized
- **v0.9.5:** Inventory rarity column/filter; Windows-safe combos; Issue templates
- **v0.9.4:** Customize language/theme dropdowns fixed on Windows

**Next:** commit/tag app icon · editions v2 · real rules for non-Commander formats · optional Scryfall inventory search · Optimize advanced (priorities / cards moved / plan stats / print preference).
