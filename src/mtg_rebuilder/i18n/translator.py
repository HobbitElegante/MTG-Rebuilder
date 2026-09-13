from mtg_rebuilder.config import DEFAULT_LOCALE

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app.title": "MTG Commander Collection Manager",
        "tab.inventory": "Inventory",
        "tab.decks": "Decks",
        "tab.optimize": "Optimize",
        "tab.browse": "Browse",
        "inventory.search": "Search card on Scryfall",
        "inventory.add": "Add to inventory",
        "inventory.quantity": "Quantity",
        "inventory.empty": "No unassigned copies in inventory.",
        "inventory.summary.title": "Collection summary",
        "inventory.summary.empty": "No physical copies registered yet. Import a deck to start mapping your collection.",
        "inventory.summary.body": (
            "{unique} unique cards · {copies} physical copies · "
            "{free} free · {assigned} assigned to armed decks"
        ),
        "inventory.search.collection": (
            "Search collection (name or Scryfall syntax, e.g. t:creature c:r)…"
        ),
        "inventory.search.name": "Filter collection by card name…",
        "inventory.search.scryfall": "Scryfall syntax (e.g. id<=rb t:creature)…",
        "inventory.search.scryfall_mode": "Scryfall",
        "inventory.search.scryfall_mode_tip": (
            "Enables Scryfall syntax in the search box. Nothing is queried until "
            "you press the Scryfall logo — results are limited to cards you own."
        ),
        "inventory.search.scryfall_run": "Run Scryfall search on your collection",
        "inventory.search.scryfall_idle": (
            "Scryfall mode on — type a query, then press the Scryfall logo. "
            "Only cards in your collection are kept."
        ),
        "inventory.search.scryfall_busy": "Searching Scryfall…",
        "inventory.search.scryfall_applied": (
            "Scryfall “{query}” → {count} card(s) in your collection"
        ),
        "inventory.search.scryfall_failed": "Scryfall search failed: {error}",
        "inventory.search.hint": "Type a card name to check whether you have free copies.",
        "inventory.search.offline_filters": (
            "Ignored filters [{filters}]: require an internet connection"
        ),
        "inventory.filters.toggle": "Filter",
        "inventory.filters.toggle_count": "Filter ({count})",
        "inventory.view.images": "Image view",
        "inventory.view.images_active": "Image view ✓",
        "inventory.view.sort_by": "Sort by",
        "inventory.view.loading_image": "Oops! The image is still loading",
        "inventory.view.missing_image": (
            "Remember to update your collection images"
        ),
        "inventory.view.details_empty": "Select a card to see its details.",
        "inventory.filters.title": "Inventory filters",
        "inventory.filters.close": "Close",
        "inventory.filters.availability": "Availability",
        "inventory.filters.availability_hint": (
            "Free copies are the ones not assigned to an armed deck."
        ),
        "inventory.filters.only_free": "Only cards with free copies",
        "inventory.filters.type": "Type",
        "inventory.filters.type_hint": (
            "Check one or more types; a card matching any of them is kept (OR)."
        ),
        "inventory.filters.subtypes": "Subtype",
        "inventory.filters.subtypes_hint": (
            "Whatever follows the em dash of a type line: Elf, Equipment, Aura… "
            "Only subtypes present in your collection are offered. "
            "Any of them matches (OR), and they narrow the checked types."
        ),
        "inventory.filters.subtypes_search": "Find a subtype (Elf, Aura…)",
        "inventory.filters.subtypes_selected": "Selected subtypes",
        "inventory.filters.subtypes_add": "Add",
        "inventory.filters.decks": "Armed decks",
        "inventory.filters.decks_hint": (
            "Hide cards with a physical copy assigned to armed decks. "
            "Use the checkbox for all armed decks, or add specific decks."
        ),
        "inventory.filters.decks_any_armed": "Hide cards in any armed deck",
        "inventory.filters.decks_search": "Find an armed deck…",
        "inventory.filters.decks_selected": "Excluded decks",
        "inventory.filters.decks_add": "Add",
        "inventory.filters.picker_no_match": "Nothing matches “{text}”.",
        "inventory.filters.picker_ambiguous": (
            "Several options match “{text}” — keep typing."
        ),
        "inventory.filters.picker_already": "“{name}” is already on the list.",
        "inventory.filters.colors": "Color identity",
        "inventory.filters.colors_hint": (
            "Compare the checked letters as at most (id≤), exactly, or at least. "
            "No letters means no filter, so cards with no color at all need the "
            "colorless switch."
        ),
        "inventory.filters.colors_mode": "Match",
        "inventory.filters.colors_mode.at_most": "At most these colors (id≤)",
        "inventory.filters.colors_mode.exact": "Exactly these colors (id=)",
        "inventory.filters.colors_mode.at_least": "At least these colors (id≥)",
        "inventory.filters.colors_colorless": "Only colorless cards",
        "inventory.filters.color.W": "W: White",
        "inventory.filters.color.U": "U: Blue",
        "inventory.filters.color.B": "B: Black",
        "inventory.filters.color.R": "R: Red",
        "inventory.filters.color.G": "G: Green",
        "inventory.filters.rarity": "Rarity",
        "inventory.filters.rarity_hint": (
            "Match any selected rarity (C/U/R/M). Empty or all four = no filter. "
            "Needs Scryfall data; with editions on, uses the copy’s set when known."
        ),
        "inventory.filters.rarity.C": "C: Common",
        "inventory.filters.rarity.U": "U: Uncommon",
        "inventory.filters.rarity.R": "R: Rare",
        "inventory.filters.rarity.M": "M: Mythic rare",
        "inventory.filters.cmc": "Mana value",
        "inventory.filters.cmc_hint": (
            "Add one or more comparisons; all must match (AND)."
        ),
        "inventory.filters.cmc_add": "Add",
        "inventory.filters.cmc_remove": "Remove",
        "inventory.filters.cmc_duplicate": (
            "“MV {op} {value}” is already on the list."
        ),
        "inventory.filters.cmc_conflict": (
            "“MV {op} {value}” would match no cards with the other conditions."
        ),
        "inventory.filters.cmc_duplicates": (
            "Duplicate mana-value conditions; remove one."
        ),
        "inventory.filters.cmc_impossible": (
            "These mana-value conditions match no cards."
        ),
        "inventory.filters.clear": "Clear filters",
        "inventory.filters.chip_remove_tip": "Remove this filter",
        "inventory.filters.chips_clear": "Clear all",
        "inventory.filters.chip.only_free": "With free copies",
        "inventory.filters.chip.type": "Type: {name}",
        "inventory.filters.chip.subtype": "Subtype: {name}",
        "inventory.filters.chip.any_armed": "Not in armed decks",
        "inventory.filters.chip.deck": "Not in: {name}",
        "inventory.filters.chip.colors_at_most": "Colors ≤ {colors}",
        "inventory.filters.chip.colors_exact": "Colors = {colors}",
        "inventory.filters.chip.colors_at_least": "Colors ≥ {colors}",
        "inventory.filters.chip.colorless": "Colorless",
        "inventory.filters.chip.rarity": "Rarity: {codes}",
        "inventory.filters.chip.cmc": "MV {op} {value}",
        "inventory.add_new": "Add new card to collection",
        "inventory.add_list": "Add list to collection",
        "inventory.add_list.title": "Add list to collection",
        "inventory.add_list.dialog_title": "Open deck list",
        "inventory.add_list.identified": "Identified cards",
        "inventory.add_list.unresolved": "Unrecognized lines",
        "inventory.add_list.unresolved.hint": (
            "Edit a line and press Recheck, or Remove to discard it."
        ),
        "inventory.add_list.unresolved.line": "Line",
        "inventory.add_list.recheck": "Recheck",
        "inventory.add_list.recheck.failed": (
            "Still unrecognized. Fix the name (e.g. “1 Correct Card Name”) and try again."
        ),
        "inventory.add_list.recheck.skipped": (
            "That line resolved to a basic land or token, which is not tracked in inventory."
        ),
        "inventory.add_list.add": "Add",
        "inventory.add_list.remove": "Remove",
        "inventory.add_list.confirm": "Add copies",
        "inventory.add_list.empty": "No cards found in that list.",
        "inventory.add_list.placeholder": (
            "Paste Moxfield / Archidekt / Arena / MTGO (.dek), or a Moxfield / Archidekt deck URL…"
        ),
        "inventory.add_list.url_failed": "Could not download that deck:\n{error}",
        "inventory.add_list.not_trackable": (
            "Basics and tokens are not tracked in inventory. Choose another card."
        ),
        "inventory.edit_copies": "Edit copy count",
        "inventory.add_dialog.title": "Add card to collection",
        "inventory.add_dialog.search": "Search card name",
        "inventory.add_dialog.copies": "Copies to add",
        "inventory.add_dialog.confirm": "Add copies",
        "inventory.add_dialog.no_selection": "Select a card from the search results.",
        "inventory.edit_dialog.title": "Edit copy count",
        "inventory.edit_dialog.card": "Card",
        "inventory.edit_dialog.total": "Total copies",
        "inventory.edit_dialog.assigned_note": (
            "{count} cop(y/ies) are assigned to armed decks and cannot be removed here."
        ),
        "inventory.status.available": "Available — {count} free",
        "inventory.status.unavailable": "Not available — all {count} assigned",
        "inventory.not_owned": "That card is not in your collection.",
        "inventory.matches": "{count} matching cards in your collection.",
        "inventory.table.total": "Total",
        "inventory.table.free": "Free",
        "inventory.table.assigned": "Assigned",
        "inventory.table.decks": "In decks",
        "inventory.table.cmc": "CMC",
        "inventory.table.cmc_tip": "Mana value (converted mana cost)",
        "inventory.table.color": "Colors",
        "inventory.table.rarity": "Rarity",
        "inventory.table.rarity_tip": "C common · U uncommon · R rare · M mythic (sort C→U→R→M)",
        "inventory.table.edition": "Edition",
        "inventory.table.colorless": "—",
        "inventory.table.no_decks": "—",
        "inventory.editions.title": "Editions",
        "inventory.editions.hint": (
            "Assign a set code to each physical copy. Leave “-” for copies you "
            "have not identified yet."
        ),
        "inventory.editions.copy": "Copy",
        "inventory.editions.edition": "Edition",
        "inventory.editions.copy_label": "Copy {number} — {where}",
        "inventory.editions.apply_all": "Apply to all",
        "inventory.editions.prompt_title": "Editions of the cards you moved",
        "inventory.editions.prompt_hint": (
            "These copies are now in {deck} and have no edition recorded. Fill in "
            "the ones you know; the rest stay as “-”."
        ),
        "inventory.editions.skip": "Skip",
        "decks.import": "Import new list",
        "decks.name": "Deck name",
        "decks.format": "Format",
        "decks.format.commander": "EDH / Commander",
        "decks.format.other": "Other (no rules yet)",
        "decks.commander": "Commander name (optional)",
        "decks.import.placeholder": (
            "Paste Moxfield / Archidekt / Arena / MTGO (.dek), or a Moxfield / Archidekt deck URL…"
        ),
        "decks.import.url_failed": "Could not download that deck:\n{error}",
        "decks.import.url_filled": "Loaded deck from URL. Review and confirm again.",
        "import.moxfield.forbidden": (
            "Moxfield blocked the download (403).\n\n"
            "The deck may be private, or Moxfield rejected the request from this "
            "network.\n\n"
            "Open the deck in your browser → More → Export → Copy for MTGO, then "
            "paste that text here."
        ),
        "import.moxfield.not_found": (
            "Moxfield could not find that deck.\n\n"
            "It may be private or deleted. Paste More → Export → Copy for MTGO "
            "instead."
        ),
        "import.moxfield.http": (
            "Moxfield returned an error (HTTP {status}).\n\n"
            "Paste More → Export → Copy for MTGO instead."
        ),
        "import.moxfield.bad_response": (
            "Moxfield returned an unexpected response.\n\n"
            "Paste More → Export → Copy for MTGO instead."
        ),
        "import.url.network": (
            "Could not reach the deck site (network error).\n\n"
            "Check your connection, or paste the exported list instead of the URL."
        ),
        "decks.status.armed": "Armed",
        "decks.status.dismantled": "Dismantled",
        "decks.legality.warning": "⚠",
        "decks.legality.banned": "banned",
        "decks.legality.not_legal": "not legal",
        "decks.legality.restricted": "restricted",
        "decks.legality.tooltip_header": "Commander format warnings (advisory — does not block assembly):",
        "decks.legality.tooltip_line": "• {name} — {status}",
        "decks.legality.card_tooltip": "{name} is {status} in Commander (advisory).",
        "decks.rules.tooltip_header": "Commander rule warnings (advisory — does not block assembly):",
        "decks.rules.color_identity": "• {name} ({colors}) is outside the color identity {allowed}",
        "decks.rules.pairing": "• {name} is not a legal second commander for {commander}",
        "decks.rules.missing_data": "• {name} — no cached Scryfall data, color identity unchecked",
        "decks.rules.singleton": "• {name} appears {qty} times (Commander allows up to {limit})",
        "decks.rules.deck_size": "• Deck list has {count} cards (expected {expected}; Companion is outside)",
        "decks.rules.colorless": "colorless",
        "decks.lock": "Lock deck",
        "decks.unlock": "Unlock deck",
        "decks.locked.icon": "ɸ",
        "decks.locked.tooltip": "Locked — Optimize will not dismantle this deck",
        "decks.set_armed": "Mark armed",
        "decks.set_dismantled": "Mark dismantled",
        "decks.export_list": "Export list",
        "decks.export.title": "Export “{name}”",
        "decks.export.hint": (
            "Choose a format, then copy the list and paste it into Moxfield, Arena, "
            "Archidekt, MTGGoldfish, or another tool."
        ),
        "decks.export.format": "Format",
        "decks.export.format.mtgo": "MTGO",
        "decks.export.format.moxfield": "Moxfield",
        "decks.export.format.arena": "Arena",
        "decks.export.format.archidekt": "Archidekt",
        "decks.export.format.mtggoldfish": "MTGGoldfish",
        "decks.export.copy": "Copy to clipboard",
        "decks.export.copied": "Copied to clipboard.",
        "decks.empty": "No decks imported yet.",
        "decks.empty_filtered": "No decks match this filter.",
        "decks.details": "{name}: {count} list entries",
        "decks.details.armed": "{count} list entries — complete",
        "decks.details.dismantled": (
            "{count} list entries — {available}/{needed} trackable cards available"
        ),
        "decks.details.commander": "Commander: {name}",
        "decks.details.commander_none": "Commander: not set",
        "decks.details.secondary": "{role}: {name}",
        "decks.details.format": "Format: {name}",
        "decks.role.partner": "Partner",
        "decks.role.companion": "Companion",
        "decks.role.background": "Background",
        "decks.import.status.title": "Deck status",
        "decks.import.status.question": "Is this deck currently armed or dismantled?",
        "decks.import.available.title": "Available cards",
        "decks.import.available.question": (
            "Which cards from this list do you still have available in your collection?"
        ),
        "decks.import.available.in_list": "In list",
        "decks.import.available.available": "Available",
        "decks.import.available.all": "Mark all available",
        "decks.list.title": "Your decks",
        "decks.filter.label": "Show",
        "decks.filter.all": "All decks",
        "decks.filter.armed": "Armed only",
        "decks.filter.dismantled": "Dismantled only",
        "decks.filter.format.all": "All formats",
        "decks.search": "Search by deck or commander…",
        "decks.sort.by": "Sort",
        "decks.sort.number": "Number",
        "decks.sort.name": "Name",
        "decks.sort.status": "Armed / Dismantled",
        "decks.sort.asc": "Ascending",
        "decks.sort.desc": "Descending",
        "decks.cards.title": "Deck list",
        "decks.cards.empty": "No cards in this deck",
        "decks.cards.line": "{qty}× {name}",
        "decks.cards.line_role": "{qty}× {name} ({role})",
        "decks.cards.filter_by": "Filter by",
        "decks.cards.sort.mana_value": "Mana value",
        "decks.cards.sort.alphabetical": "Alphabetical",
        "decks.cards.group_by_type": "Group by type",
        "decks.cards.group_header": "{name}:",
        "decks.cards.group.command_zone": "Command zone",
        "decks.cards.group.other": "Other",
        "decks.stats.lands": "Lands: {count} ({basic} basic)",
        "decks.stats.avg_no_lands": "x̄ mana value (no lands): {value}",
        "decks.stats.avg_with_lands": "x̄ mana value (with lands): {value}",
        "decks.stats.avg_tooltip": "x̄ = average",
        "decks.stats.types_title": "Types:",
        "decks.stats.pips": "Mana pips: {value}",
        "decks.stats.unknown": "{count} card(s) without cached data",
        "decks.stats.type.creature": "Creatures",
        "decks.stats.type.instant": "Instants",
        "decks.stats.type.sorcery": "Sorceries",
        "decks.stats.type.artifact": "Artifacts",
        "decks.stats.type.enchantment": "Enchantments",
        "decks.stats.type.planeswalker": "Planeswalkers",
        "decks.stats.type.battle": "Battles",
        "decks.stats.type.land": "Lands",
        "decks.stats.curve.title": "Mana curve (lands excluded)",
        "decks.stats.curve.creatures": "Creatures",
        "decks.stats.curve.spells": "Non-creature",
        "decks.stats.curve.empty": "No mana curve data",
        "decks.move_up": "Move up",
        "decks.move_down": "Move down",
        "decks.edit_details": "Edit name / commander",
        "decks.details_edit.title": "Edit deck details",
        "decks.details_edit.commander": "Commander",
        "decks.details_edit.add_secondary": "Add Partner, Companion, or Background",
        "decks.details_edit.remove_secondary": "Remove secondary card",
        "decks.details_edit.secondary_placeholder": "{role} name",
        "decks.details_edit.secondary_required": "Enter a card name for {role}, or remove it.",
        "decks.details_edit.hint": (
            "Leave commander empty to clear it. Use + to add a Partner, Companion, "
            "or Background. Cards must exist in the local Scryfall cache; if they "
            "are not on the list yet, they will be added."
        ),
        "decks.details_edit.name_required": "Deck name cannot be empty.",
        "decks.details_edit.commander_not_found": (
            "Card “{name}” was not found in the local card cache."
        ),
        "decks.edit_list": "Edit list",
        "decks.update_list": "Update list",
        "decks.update.title": "Update list — {name}",
        "decks.update.submit": "Review update",
        "decks.update.summary": "Cards in list: {before} → {after}",
        "decks.update.added": "Cards to add ({count})",
        "decks.update.removed": "Cards to remove ({count})",
        "decks.update.unresolved": (
            "Unrecognized lines ({count}) — they will be left out of the list"
        ),
        "decks.update.no_changes": "The list already matches; nothing to update.",
        "decks.update.armed_warning": (
            "This deck is armed: applying the update reassigns its physical copies, "
            "creating copies for cards that are new to the list."
        ),
        "decks.update.apply": "Apply update",
        "decks.update.copies_hint": (
            "Free = copies already in inventory. Raise it only if you need to add "
            "physical copies (for example the lands that were missing from the list)."
        ),
        "decks.delete_list": "Delete list",
        "decks.delete.confirm.title": "Delete deck list",
        "decks.delete.confirm.question": (
            "Delete “{name}”? Choose below how many physical copies to remove "
            "with the list."
        ),
        "decks.delete.copies.hint": (
            "You can remove all removable copies, some, or none. "
            "If Quitar stays at 0, those copies belong to other armed decks."
        ),
        "decks.delete.copies.inventory": "In inventory",
        "decks.delete.copies.inventory_elsewhere": "{total} ({elsewhere} in other decks)",
        "decks.delete.copies.elsewhere_tip": (
            "{count} cop(y/ies) assigned to other armed decks and cannot be removed here."
        ),
        "decks.delete.copies.remove": "Remove",
        "decks.delete.copies.remaining": "Remaining",
        "decks.delete.copies.keep_all": "Keep all copies",
        "decks.delete.copies.remove_all": "Remove all removable",
        "decks.show_import": "Import new list",
        "decks.load_file": "Load file",
        "decks.submit_import": "Confirm list",
        "decks.cancel_import": "Cancel",
        "decks.load_file.dialog_title": "Open deck list",
        "decks.edit.title": "Edit deck list",
        "decks.edit.save": "Save list",
        "decks.edit.total": "Cards in list: {current} / {target}",
        "decks.edit.total_only": "Cards in list: {current}",
        "decks.edit.size_mismatch": (
            "List size is {current}; this format expects {target}. Saving is still allowed."
        ),
        "decks.edit.slots": "Open slots: {slots}",
        "decks.edit.free": "Free",
        "decks.edit.replace": "Replace",
        "decks.edit.add": "Add card",
        "decks.edit.add.title": "Add card to list",
        "decks.edit.replace.title": "Replace card",
        "decks.edit.search": "Search card name",
        "decks.edit.quantity": "Quantity in list",
        "decks.edit.available": "Available copies (0 = missing)",
        "decks.edit.remove_outgoing": "Also remove copies of the outgoing card",
        "decks.edit.remove_outgoing_qty": "Copies to remove",
        "decks.edit.pick": "Use selected card",
        "decks.edit.no_selection": "Select a card from the search results.",
        "decks.edit.over_target": "List total cannot exceed the original size.",
        "optimize.target": "Deck to assemble",
        "optimize.target.search": "Type deck or commander name…",
        "optimize.target.armed_suffix": "(armed)",
        "optimize.add": "Add to plan",
        "optimize.queue": "Assembly set",
        "optimize.queue.remove": "Remove from set",
        "optimize.queue.viable": "viable",
        "optimize.queue.missing": "missing cards",
        "optimize.queue.armed": "already armed",
        "optimize.queue.kept": "kept armed",
        "optimize.run": "Find optimal dismantle plan",
        "optimize.no_solutions": "No feasible dismantle plan found.",
        "optimize.no_solutions_set": "This set cannot all be armed at once.",
        "optimize.already_armed": "This deck is already armed — nothing to optimize.",
        "optimize.multiple": "Multiple optimal plans — choose one:",
        "optimize.solution.suggested": "suggested",
        "optimize.from_inventory": "Cards covered by free inventory",
        "optimize.decks_to_dismantle": "Decks to dismantle",
        "optimize.section_for": "---------- For {deck} ----------",
        "optimize.summary.dismantle": "Dismantle {count} deck(s) to assemble this list",
        "optimize.summary.inventory_only": "Assemble from free inventory — no decks to dismantle",
        "optimize.summary.dismantle_set": "Dismantle {count} deck(s) to arm this set",
        "optimize.summary.inventory_only_set": "Arm this set from free inventory — no decks to dismantle",
        "optimize.missing": "Still missing",
        "optimize.missing.need_to_find": "Need to find",
        "optimize.unit.cards": "cards",
        "optimize.unit.decks": "decks",
        "optimize.confirm": "Confirm plan",
        "optimize.cancel": "Cancel",
        "optimize.apply.confirm_title": "Apply assembly plan?",
        "optimize.apply.confirm_body": "This will dismantle:\n{decks}\n\nand arm:\n{target}",
        "optimize.apply.confirm_body_set": "This will dismantle:\n{decks}\n\nand arm:\n{targets}",
        "optimize.apply.success": "Plan applied: donor decks dismantled and target armed.",
        "optimize.apply.success_set": "Plan applied: donors dismantled and the set armed.",
        "optimize.card_qty": "{name} × {qty}",
        "optimize.section.assembly": "Assembly plan",
        "optimize.section.viable_plans": "Viable sets",
        "optimize.viable.max": "Largest viable set",
        "optimize.viable.n": "{n} decks",
        "optimize.viable.respect_locked": "Respect locked decks (ɸ)",
        "optimize.viable.respect_locked.tip": "Copies assigned to locked decks cannot cover other decks in the set.",
        "optimize.viable.count": "{k} viable combination(s)",
        "optimize.viable.count_truncated": "Showing first {k} viable combination(s)…",
        "optimize.viable.count_max": "Maximum {n} decks · {k} combination(s)",
        "optimize.viable.count_max_truncated": "Maximum {n} decks · showing first {k}…",
        "optimize.viable.empty": "No viable combinations of this size.",
        "optimize.viable.empty_max": "No set of 2+ decks fits the collection.",
        "optimize.viable.hint": "Sets of decks your collection can have armed at once (physical copies only).",
        "optimize.viable.computing": "Calculating…",
        "optimize.viable.calculate": "Calculate combinations",
        "optimize.viable.recalculate": "Recalculate",
        "optimize.viable.recalculate_required": "Recalculate (required)",
        "optimize.viable.not_calculated": "Not calculated yet for this size — press Calculate.",
        "optimize.viable.stale_optional": "collection changed; recalculate recommended",
        "optimize.viable.stale_mandatory": "Copies were removed — recalculate required for this size.",
        "optimize.viable.filter": "Show combinations with deck",
        "optimize.viable.filter.search": "Type deck or commander name…",
        "optimize.viable.filter.all": "All decks",
        "optimize.viable.count_filtered": "{shown} of {total} combination(s) include this deck",
        "optimize.viable.combination": "Combination #{n}",
        "optimize.viable.send_to_assembly": "Send to assembly plan",
        "optimize.viable.expand_all": "Expand all",
        "menu.language": "Language",
        "config.language": "Language",
        "config.theme": "Theme",
        "language.en": "English",
        "language.es": "Español",
        "theme.system": "System",
        "theme.light": "Light",
        "theme.dark": "Dark",
        "common.refresh": "Refresh",
        "common.error": "Error",
        "common.success": "Success",
        "browse.section.overview": "Overview",
        "browse.section.customize": "Customize",
        "browse.section.cards": "Cards",
        "browse.section.decks": "Decks",
        "browse.section.availability": "Availability",
        "browse.section.history": "History",
        "browse.section.scryfall": "Scryfall",
        "browse.history.filter": "Filter",
        "browse.history.filter.all": "All",
        "browse.history.filter.inventory": "Inventory",
        "browse.history.filter.decks": "Decks",
        "browse.history.when": "When",
        "browse.history.event": "Event",
        "browse.history.empty": "No activity recorded yet.",
        "browse.history.load_more": "Load more",
        "browse.history.export": "Export CSV",
        "browse.history.undo": "Undo last",
        "browse.history.undo.confirm": (
            "Undo the most recent change?"
        ),
        "browse.history.redo": "Redo last",
        "browse.history.redo.confirm": (
            "Redo the change that was just undone?"
        ),
        "history.event.copies_added": "Added {name} × {qty_delta}",
        "history.event.copies_removed": "Removed {name} × {qty_delta}",
        "history.event.deck_armed": "Armed {deck_name}",
        "history.event.deck_dismantled": "Dismantled {deck_name}",
        "history.event.deck_imported": "Imported {deck_name}",
        "history.event.deck_deleted": "Deleted {deck_name}",
        "history.event.deck_list_edited": "Edited list: {deck_name}",
        "history.event.plan_applied": (
            "Applied plan: armed {deck_name}"
            "{donors_suffix}"
        ),
        "history.event.plan_applied.donors": " (dismantled {donors})",
        "history.event.undone": "Undid: {detail}",
        "browse.overview.greeting": (
            " __  __  _______   _____         _____  \n"
            "|  \\/  ||__   __| / ____|       |  __ \\ \n"
            "| \\  / |   | |   | |  __ ______ | |__) |\n"
            "| |\\/| |   | |   | | |_ |______| |  _  / \n"
            "| |  | |   | |   | |__| |        | | \\ \\ \n"
            "|_|  |_|   |_|    \\_____|        |_|  \\_\\"
        ),
        "browse.overview.tagline": "Commander Collection Manager",
        "browse.overview.body": (
            "Cached cards: {cards}\n"
            "Physical copies: {copies} ({unassigned} unassigned)\n"
            "Decks: {decks} ({armed} armed)\n"
            "Deck list entries: {deck_cards}\n"
            "Copy assignments: {assignments}"
        ),
        "browse.cards.search": "Filter cards by name",
        "browse.cards.name": "Name",
        "browse.cards.type": "Type",
        "browse.cards.cmc": "CMC",
        "browse.cards.copies": "Copies",
        "browse.cards.flags": "Flags",
        "browse.cards.flag.basic": "basic",
        "browse.cards.flag.token": "token",
        "browse.overview.show_images": "Show card images",
        "browse.overview.welcome_separator": "-----",
        "browse.overview.welcome": (
            "Welcome!\n"
            "If this is your first time here, we recommend these steps:\n"
            "1. Download the Scryfall bulk pack so you can search and resolve cards offline\n"
            "2. Import into Inventory the list of free cards in your personal bulk\n"
            "3. Import into Decks the lists for your armed and dismantled decks "
            "(this also adds copies to your inventory)\n"
            "4. Download images for the cards in your collection\n"
            "5. Use the Optimize tool to see whether you need more copies in your bulk"
        ),
        "browse.overview.track_editions": "Track card editions",
        "browse.overview.track_editions_hint": (
            "Adds an Edition column to Inventory and asks for set codes after "
            "reassembling a deck. Copies with no edition yet show as “-”."
        ),
        "browse.customize.display": "Display",
        "browse.customize.warnings": "Deck warnings",
        "browse.customize.show_images": "Show card images",
        "browse.customize.track_editions": "Track card editions",
        "browse.customize.track_editions_hint": (
            "Adds an Edition column to Inventory and asks for set codes after "
            "reassembling a deck. Copies with no edition yet show as “-”."
        ),
        "browse.customize.show_legality_warnings": (
            "Show Scryfall Commander legality warnings (⚠)"
        ),
        "browse.customize.show_rule_warnings": (
            "Show Commander game-rule warnings (⚠)"
        ),
        "browse.customize.house_ban.title": "House banlist",
        "browse.customize.house_ban.hint": (
            "Cards on this list always show an advisory ⚠ on decks that include them."
        ),
        "browse.customize.house_ban.add": "Add card…",
        "browse.customize.house_ban.remove": "Remove selected",
        "decks.legality.house_banned": "house banned",
        "preview.title": "Card image",
        "preview.empty": "Select a card to preview it.",
        "preview.loading": "Loading image…",
        "preview.missing": "No image available.",
        "preview.flip": "Flip card",
        "browse.decks.quantity": "Qty",
        "browse.decks.role": "Role",
        "browse.inventory.copy": "Copy #",
        "browse.inventory.copies": "Copies",
        "browse.inventory.mixed": "{free} free · {decks}",
        "browse.inventory.assigned": "Assigned to",
        "browse.inventory.free": "Free",
        "browse.scryfall.sync_download": "Download oracle-cards bulk pack",
        "browse.scryfall.sync_update": "Update oracle-cards bulk pack",
        "browse.scryfall.sync_current": "oracle-cards up to date",
        "browse.scryfall.sync_resync": "Re-sync oracle-cards bulk pack",
        "browse.scryfall.sync_unique": "Use unique-artwork (better art)",
        "browse.scryfall.images_collection": "Download images (collection)",
        "browse.scryfall.images_cached": "Download images (full cache)",
        "browse.scryfall.card_data_refresh": "Refresh card data (collection)",
        "browse.scryfall.card_data_starting": "Refreshing card data…",
        "browse.scryfall.card_data_done": (
            "Updated Commander legalities and image links for "
            "{count:,} collection cards."
        ),
        "browse.scryfall.starting": "Starting Scryfall sync…",
        "browse.scryfall.done": "Imported {count:,} cards from {pack}.",
        "browse.scryfall.sync_failed": (
            "Could not sync the Scryfall bulk pack.\n\n{detail}"
        ),
        "browse.scryfall.images_failed": (
            "Could not download card images.\n\n{detail}"
        ),
        "browse.scryfall.card_data_failed": (
            "Could not refresh card data.\n\n{detail}"
        ),
        "browse.scryfall.network_failed": (
            "Could not reach Scryfall.\n\n"
            "Check your internet connection and try again."
        ),
        "browse.scryfall.images_starting": "Starting image download…",
        "browse.scryfall.images_done": (
            "Images: {downloaded:,} downloaded, {skipped:,} already local."
        ),
        "browse.scryfall.never": "Never",
        "browse.scryfall.none": "None",
        "browse.scryfall.update_yes": "Yes — newer pack on Scryfall",
        "browse.scryfall.update_no": "No",
        "browse.scryfall.update_unknown": "Unknown (offline)",
        "browse.scryfall.status": (
            "Cached cards in database: {cached}\n"
            "Local pack: {pack}\n"
            "Scryfall bulk updated at: {bulk_updated}\n"
            "Last local sync: {last_synced}\n"
            "Cards processed in last sync: {imported}\n"
            "Update available: {update_available}\n"
            "Collection images on disk: {images_collection}\n"
            "Cache images on disk: {images_cached}"
        ),
        "browse.scryfall.info": (
            "Individual API lookups are saved in the local Card cache. "
            "Download oracle-cards once for offline name resolution, or "
            "unique-artwork for better default card art. "
            "Image download saves Scryfall normal JPEGs under data/images/ "
            "(collection or full cache). "
            "Refresh Commander legalities updates format status for cards you "
            "own or have on deck lists (faster than a full bulk sync). "
            "Mana symbols are Scryfall SVGs bundled with the app; Scryfall is "
            "not affiliated with or endorsed by this software."
        ),
        "browse.scryfall.confirm_unique_title": "Use unique-artwork?",
        "browse.scryfall.confirm_unique_body": (
            "This downloads the unique-artwork bulk pack (~250 MB) and updates "
            "local card art URLs. Continue?"
        ),
        "browse.scryfall.confirm_images_title": "Download full cache images?",
        "browse.scryfall.confirm_images_body": (
            "This may download tens of thousands of images and take a long time. "
            "Continue?"
        ),
    },
    "es": {
        "app.title": "Gestor de Colección Commander MTG",
        "tab.inventory": "Inventario",
        "tab.decks": "Mazos",
        "tab.optimize": "Optimizar",
        "tab.browse": "Explorar",
        "inventory.search": "Buscar carta en Scryfall",
        "inventory.add": "Añadir al inventario",
        "inventory.quantity": "Cantidad",
        "inventory.empty": "No hay copias libres en el inventario.",
        "inventory.summary.title": "Resumen de la colección",
        "inventory.summary.empty": (
            "Aún no hay copias físicas registradas. Importa un mazo para empezar a mapear tu colección."
        ),
        "inventory.summary.body": (
            "{unique} cartas únicas · {copies} copias físicas · "
            "{free} libres · {assigned} asignadas a mazos armados"
        ),
        "inventory.search.collection": (
            "Buscar en la colección (nombre o sintaxis Scryfall, p. ej. t:creature c:r)…"
        ),
        "inventory.search.name": "Filtrar la colección por nombre de carta…",
        "inventory.search.scryfall": "Sintaxis Scryfall (p. ej. id<=rb t:creature)…",
        "inventory.search.scryfall_mode": "Scryfall",
        "inventory.search.scryfall_mode_tip": (
            "Activa la sintaxis Scryfall en el cuadro. No se consulta nada hasta "
            "que pulses el logo de Scryfall — solo se conservan cartas de tu colección."
        ),
        "inventory.search.scryfall_run": "Buscar en Scryfall sobre tu colección",
        "inventory.search.scryfall_idle": (
            "Modo Scryfall activo — escribe la consulta y pulsa el logo. "
            "Solo se muestran cartas de tu inventario."
        ),
        "inventory.search.scryfall_busy": "Buscando en Scryfall…",
        "inventory.search.scryfall_applied": (
            "Scryfall «{query}» → {count} carta(s) en tu colección"
        ),
        "inventory.search.scryfall_failed": "Falló la búsqueda Scryfall: {error}",
        "inventory.search.hint": "Escribe el nombre de una carta para ver si tienes copias libres.",
        "inventory.search.offline_filters": (
            "Se ignoraron los filtros [{filters}]: requieren conexión a internet"
        ),
        "inventory.filters.toggle": "Filtrar",
        "inventory.filters.toggle_count": "Filtrar ({count})",
        "inventory.view.images": "Vista imágenes",
        "inventory.view.images_active": "Vista imágenes ✓",
        "inventory.view.sort_by": "Ordenar por",
        "inventory.view.loading_image": "¡Oops! Todavía está cargando la imagen",
        "inventory.view.missing_image": (
            "Recuerda actualizar las imágenes de tu colección"
        ),
        "inventory.view.details_empty": "Selecciona una carta para ver sus datos.",
        "inventory.filters.title": "Filtros de inventario",
        "inventory.filters.close": "Cerrar",
        "inventory.filters.availability": "Disponibilidad",
        "inventory.filters.availability_hint": (
            "Las copias libres son las que no están asignadas a un mazo armado."
        ),
        "inventory.filters.only_free": "Solo cartas con copias libres",
        "inventory.filters.type": "Tipo",
        "inventory.filters.type_hint": (
            "Marca uno o más tipos; se queda la carta que cumpla cualquiera (OR)."
        ),
        "inventory.filters.subtypes": "Subtipo",
        "inventory.filters.subtypes_hint": (
            "Lo que va después del guion largo de la línea de tipo: Elf, Equipment, "
            "Aura… Solo se ofrecen los subtipos presentes en tu colección. "
            "Cualquiera de ellos coincide (OR) y acotan a los tipos marcados."
        ),
        "inventory.filters.subtypes_search": "Buscar un subtipo (Elf, Aura…)",
        "inventory.filters.subtypes_selected": "Subtipos seleccionados",
        "inventory.filters.subtypes_add": "Añadir",
        "inventory.filters.decks": "Mazos armados",
        "inventory.filters.decks_hint": (
            "Oculta cartas con una copia física asignada a mazos armados. "
            "Usa el checkbox para todos los armados, o añade mazos concretos."
        ),
        "inventory.filters.decks_any_armed": "Ocultar cartas en cualquier mazo armado",
        "inventory.filters.decks_search": "Buscar un mazo armado…",
        "inventory.filters.decks_selected": "Mazos excluidos",
        "inventory.filters.decks_add": "Añadir",
        "inventory.filters.picker_no_match": "Nada coincide con «{text}».",
        "inventory.filters.picker_ambiguous": (
            "Varias opciones coinciden con «{text}»: seguí escribiendo."
        ),
        "inventory.filters.picker_already": "«{name}» ya está en la lista.",
        "inventory.filters.colors": "Identidad de color",
        "inventory.filters.colors_hint": (
            "Compara las letras marcadas como máximo (id≤), exacto o al menos. "
            "Sin letras no hay filtro, así que las cartas sin ningún color "
            "necesitan el interruptor de incoloras."
        ),
        "inventory.filters.colors_mode": "Coincidencia",
        "inventory.filters.colors_mode.at_most": "Como máximo estos colores (id≤)",
        "inventory.filters.colors_mode.exact": "Exactamente estos colores (id=)",
        "inventory.filters.colors_mode.at_least": "Al menos estos colores (id≥)",
        "inventory.filters.colors_colorless": "Solo cartas incoloras",
        "inventory.filters.color.W": "W: Blanco",
        "inventory.filters.color.U": "U: Azul",
        "inventory.filters.color.B": "B: Negro",
        "inventory.filters.color.R": "R: Rojo",
        "inventory.filters.color.G": "G: Verde",
        "inventory.filters.rarity": "Rareza",
        "inventory.filters.rarity_hint": (
            "Coincide con cualquiera de las rarezas (C/U/R/M). Vacío o las cuatro = sin filtro. "
            "Requiere datos de Scryfall; con ediciones ON usa el set de la copia si se conoce."
        ),
        "inventory.filters.rarity.C": "C: Común",
        "inventory.filters.rarity.U": "U: Poco común",
        "inventory.filters.rarity.R": "R: Rara",
        "inventory.filters.rarity.M": "M: Mítica",
        "inventory.filters.cmc": "Valor de maná",
        "inventory.filters.cmc_hint": (
            "Añade una o más comparaciones; todas deben cumplirse (AND)."
        ),
        "inventory.filters.cmc_add": "Añadir",
        "inventory.filters.cmc_remove": "Quitar",
        "inventory.filters.cmc_duplicate": (
            "«VM {op} {value}» ya está en la lista."
        ),
        "inventory.filters.cmc_conflict": (
            "«VM {op} {value}» no coincidiría con ninguna carta junto a las otras condiciones."
        ),
        "inventory.filters.cmc_duplicates": (
            "Hay condiciones de valor de maná duplicadas; quita una."
        ),
        "inventory.filters.cmc_impossible": (
            "Estas condiciones de valor de maná no coinciden con ninguna carta."
        ),
        "inventory.filters.clear": "Limpiar filtros",
        "inventory.filters.chip_remove_tip": "Quitar este filtro",
        "inventory.filters.chips_clear": "Limpiar todo",
        "inventory.filters.chip.only_free": "Con copias libres",
        "inventory.filters.chip.type": "Tipo: {name}",
        "inventory.filters.chip.subtype": "Subtipo: {name}",
        "inventory.filters.chip.any_armed": "Fuera de mazos armados",
        "inventory.filters.chip.deck": "Fuera de: {name}",
        "inventory.filters.chip.colors_at_most": "Colores ≤ {colors}",
        "inventory.filters.chip.colors_exact": "Colores = {colors}",
        "inventory.filters.chip.colors_at_least": "Colores ≥ {colors}",
        "inventory.filters.chip.colorless": "Incoloras",
        "inventory.filters.chip.rarity": "Rareza: {codes}",
        "inventory.filters.chip.cmc": "VM {op} {value}",
        "inventory.add_new": "Agregar carta nueva a la colección",
        "inventory.add_list": "Agregar listado a la colección",
        "inventory.add_list.title": "Agregar listado a la colección",
        "inventory.add_list.dialog_title": "Abrir listado",
        "inventory.add_list.identified": "Cartas identificadas",
        "inventory.add_list.unresolved": "Líneas no reconocidas",
        "inventory.add_list.unresolved.hint": (
            "Edita una línea y pulsa Rechequear, o Quitar para descartarla."
        ),
        "inventory.add_list.unresolved.line": "Línea",
        "inventory.add_list.recheck": "Rechequear",
        "inventory.add_list.recheck.failed": (
            "Sigue sin reconocerse. Corrige el nombre (p. ej. “1 Nombre Correcto”) e inténtalo de nuevo."
        ),
        "inventory.add_list.recheck.skipped": (
            "Esa línea resolvió a una básica o token, que no se llevan en el inventario."
        ),
        "inventory.add_list.add": "Agregar",
        "inventory.add_list.remove": "Quitar",
        "inventory.add_list.confirm": "Agregar copias",
        "inventory.add_list.empty": "No se encontraron cartas en ese listado.",
        "inventory.add_list.placeholder": (
            "Pega Moxfield / Archidekt / Arena / MTGO (.dek), o una URL de mazo Moxfield / Archidekt…"
        ),
        "inventory.add_list.url_failed": "No se pudo descargar ese mazo:\n{error}",
        "inventory.add_list.not_trackable": (
            "Las básicas y tokens no se llevan en el inventario. Elige otra carta."
        ),
        "inventory.edit_copies": "Editar el número de copias",
        "inventory.add_dialog.title": "Agregar carta a la colección",
        "inventory.add_dialog.search": "Buscar carta por nombre",
        "inventory.add_dialog.copies": "Copias a agregar",
        "inventory.add_dialog.confirm": "Agregar copias",
        "inventory.add_dialog.no_selection": "Selecciona una carta de los resultados.",
        "inventory.edit_dialog.title": "Editar el número de copias",
        "inventory.edit_dialog.card": "Carta",
        "inventory.edit_dialog.total": "Copias totales",
        "inventory.edit_dialog.assigned_note": (
            "{count} copia(s) están asignadas a mazos armados y no se pueden quitar aquí."
        ),
        "inventory.status.available": "Disponible — {count} libre(s)",
        "inventory.status.unavailable": "No disponible — las {count} copia(s) están asignadas",
        "inventory.not_owned": "Esa carta no está en tu colección.",
        "inventory.matches": "{count} cartas coinciden en tu colección.",
        "inventory.table.total": "Total",
        "inventory.table.free": "Libres",
        "inventory.table.assigned": "Asignadas",
        "inventory.table.decks": "En mazos",
        "inventory.table.cmc": "CMC",
        "inventory.table.cmc_tip": "Coste de maná convertido",
        "inventory.table.color": "Colores",
        "inventory.table.rarity": "Rareza",
        "inventory.table.rarity_tip": "C common · U uncommon · R rare · M mythic (orden C→U→R→M)",
        "inventory.table.edition": "Edición",
        "inventory.table.colorless": "—",
        "inventory.table.no_decks": "—",
        "inventory.editions.title": "Ediciones",
        "inventory.editions.hint": (
            "Asigna un código de set a cada copia física. Deja «-» en las copias "
            "que todavía no identificaste."
        ),
        "inventory.editions.copy": "Copia",
        "inventory.editions.edition": "Edición",
        "inventory.editions.copy_label": "Copia {number} — {where}",
        "inventory.editions.apply_all": "Aplicar a todas",
        "inventory.editions.prompt_title": "Ediciones de las cartas que moviste",
        "inventory.editions.prompt_hint": (
            "Estas copias quedaron en {deck} y no tienen edición registrada. "
            "Completa las que sepas; el resto queda en «-»."
        ),
        "inventory.editions.skip": "Omitir",
        "decks.import": "Importar listado nuevo",
        "decks.name": "Nombre del mazo",
        "decks.format": "Formato",
        "decks.format.commander": "EDH / Commander",
        "decks.format.other": "Otro (sin reglas aún)",
        "decks.commander": "Nombre del commander (opcional)",
        "decks.import.placeholder": (
            "Pega Moxfield / Archidekt / Arena / MTGO (.dek), o una URL de mazo Moxfield / Archidekt…"
        ),
        "decks.import.url_failed": "No se pudo descargar ese mazo:\n{error}",
        "decks.import.url_filled": "Mazo cargado desde URL. Revísalo y confirma de nuevo.",
        "import.moxfield.forbidden": (
            "Moxfield bloqueó la descarga (403).\n\n"
            "El mazo puede ser privado, o Moxfield rechazó la petición desde esta "
            "red.\n\n"
            "Abre el mazo en el navegador → More → Export → Copy for MTGO y pega "
            "ese texto aquí."
        ),
        "import.moxfield.not_found": (
            "Moxfield no encontró ese mazo.\n\n"
            "Puede ser privado o estar borrado. Pega More → Export → Copy for MTGO "
            "en su lugar."
        ),
        "import.moxfield.http": (
            "Moxfield devolvió un error (HTTP {status}).\n\n"
            "Pega More → Export → Copy for MTGO en su lugar."
        ),
        "import.moxfield.bad_response": (
            "Moxfield devolvió una respuesta inesperada.\n\n"
            "Pega More → Export → Copy for MTGO en su lugar."
        ),
        "import.url.network": (
            "No se pudo contactar con el sitio del mazo (error de red).\n\n"
            "Revisa la conexión, o pega el listado exportado en lugar de la URL."
        ),
        "decks.status.armed": "Armado",
        "decks.status.dismantled": "Desarmado",
        "decks.legality.warning": "⚠",
        "decks.legality.banned": "baneada",
        "decks.legality.not_legal": "no legal",
        "decks.legality.restricted": "restringida",
        "decks.legality.tooltip_header": "Avisos de formato Commander (informativos — no impiden armar):",
        "decks.legality.tooltip_line": "• {name} — {status}",
        "decks.legality.card_tooltip": "{name} está {status} en Commander (aviso).",
        "decks.rules.tooltip_header": "Avisos de reglas Commander (informativos — no impiden armar):",
        "decks.rules.color_identity": "• {name} ({colors}) está fuera de la identidad de color {allowed}",
        "decks.rules.pairing": "• {name} no es un segundo comandante legal para {commander}",
        "decks.rules.missing_data": "• {name} — sin datos de Scryfall en caché, identidad de color sin verificar",
        "decks.rules.singleton": "• {name} aparece {qty} veces (Commander permite hasta {limit})",
        "decks.rules.deck_size": "• El listado tiene {count} cartas (se esperan {expected}; Companion va fuera)",
        "decks.rules.colorless": "incolora",
        "decks.lock": "Bloquear mazo",
        "decks.unlock": "Desbloquear mazo",
        "decks.locked.icon": "ɸ",
        "decks.locked.tooltip": "Bloqueado — Optimize no desarmará este mazo",
        "decks.set_armed": "Marcar armado",
        "decks.set_dismantled": "Marcar desarmado",
        "decks.export_list": "Exportar listado",
        "decks.export.title": "Exportar “{name}”",
        "decks.export.hint": (
            "Elige un formato, copia el listado y pégalo en Moxfield, Arena, "
            "Archidekt, MTGGoldfish u otra herramienta."
        ),
        "decks.export.format": "Formato",
        "decks.export.format.mtgo": "MTGO",
        "decks.export.format.moxfield": "Moxfield",
        "decks.export.format.arena": "Arena",
        "decks.export.format.archidekt": "Archidekt",
        "decks.export.format.mtggoldfish": "MTGGoldfish",
        "decks.export.copy": "Copiar al portapapeles",
        "decks.export.copied": "Copiado al portapapeles.",
        "decks.empty": "Aún no hay mazos importados.",
        "decks.empty_filtered": "Ningún mazo coincide con este filtro.",
        "decks.details": "{name}: {count} entradas en el listado",
        "decks.details.armed": "{count} entradas en el listado — completado",
        "decks.details.dismantled": (
            "{count} entradas en el listado — {available}/{needed} cartas trackeables disponibles"
        ),
        "decks.details.commander": "Commander: {name}",
        "decks.details.commander_none": "Commander: sin definir",
        "decks.details.secondary": "{role}: {name}",
        "decks.details.format": "Formato: {name}",
        "decks.role.partner": "Partner",
        "decks.role.companion": "Companion",
        "decks.role.background": "Background",
        "decks.import.status.title": "Estado del mazo",
        "decks.import.status.question": "¿Este mazo está armado o desarmado?",
        "decks.import.available.title": "Cartas disponibles",
        "decks.import.available.question": (
            "¿Cuáles cartas de este listado sigues teniendo disponibles en tu colección?"
        ),
        "decks.import.available.in_list": "En listado",
        "decks.import.available.available": "Disponibles",
        "decks.import.available.all": "Marcar todas disponibles",
        "decks.list.title": "Tus mazos",
        "decks.filter.label": "Mostrar",
        "decks.filter.all": "Todos los mazos",
        "decks.filter.armed": "Solo armados",
        "decks.filter.dismantled": "Solo desarmados",
        "decks.filter.format.all": "Todos los formatos",
        "decks.search": "Buscar por mazo o commander…",
        "decks.sort.by": "Orden",
        "decks.sort.number": "Número",
        "decks.sort.name": "Nombre",
        "decks.sort.status": "Armado / Desarmado",
        "decks.sort.asc": "Ascendente",
        "decks.sort.desc": "Descendente",
        "decks.cards.title": "Listado del mazo",
        "decks.cards.empty": "Sin cartas en este mazo",
        "decks.cards.line": "{qty}× {name}",
        "decks.cards.line_role": "{qty}× {name} ({role})",
        "decks.cards.filter_by": "Filtrar por",
        "decks.cards.sort.mana_value": "Valor de maná",
        "decks.cards.sort.alphabetical": "Alfabético",
        "decks.cards.group_by_type": "Agrupar por tipo",
        "decks.cards.group_header": "{name}:",
        "decks.cards.group.command_zone": "Zona de mando",
        "decks.cards.group.other": "Otros",
        "decks.stats.lands": "Tierras: {count} ({basic} básicas)",
        "decks.stats.avg_no_lands": "x̄ valor de maná (sin tierras): {value}",
        "decks.stats.avg_with_lands": "x̄ valor de maná (con tierras): {value}",
        "decks.stats.avg_tooltip": "x̄ = promedio",
        "decks.stats.types_title": "Tipos:",
        "decks.stats.pips": "Símbolos de maná: {value}",
        "decks.stats.unknown": "{count} carta(s) sin datos cacheados",
        "decks.stats.type.creature": "Criaturas",
        "decks.stats.type.instant": "Instantáneos",
        "decks.stats.type.sorcery": "Conjuros",
        "decks.stats.type.artifact": "Artefactos",
        "decks.stats.type.enchantment": "Encantamientos",
        "decks.stats.type.planeswalker": "Planeswalkers",
        "decks.stats.type.battle": "Batallas",
        "decks.stats.type.land": "Tierras",
        "decks.stats.curve.title": "Curva de maná (sin tierras)",
        "decks.stats.curve.creatures": "Criaturas",
        "decks.stats.curve.spells": "No criatura",
        "decks.stats.curve.empty": "Sin datos para la curva de maná",
        "decks.move_up": "Subir",
        "decks.move_down": "Bajar",
        "decks.edit_details": "Editar nombre / commander",
        "decks.details_edit.title": "Editar detalles del mazo",
        "decks.details_edit.commander": "Commander",
        "decks.details_edit.add_secondary": "Añadir Partner, Companion o Background",
        "decks.details_edit.remove_secondary": "Quitar carta secundaria",
        "decks.details_edit.secondary_placeholder": "Nombre del {role}",
        "decks.details_edit.secondary_required": (
            "Escribe el nombre de la carta para {role}, o quítala."
        ),
        "decks.details_edit.hint": (
            "Deja el commander vacío para quitarlo. Usa + para añadir Partner, "
            "Companion o Background. Las cartas deben existir en la caché local "
            "de Scryfall; si aún no están en el listado, se añadirán."
        ),
        "decks.details_edit.name_required": "El nombre del mazo no puede estar vacío.",
        "decks.details_edit.commander_not_found": (
            "La carta “{name}” no está en la caché local de cartas."
        ),
        "decks.edit_list": "Editar listado",
        "decks.update_list": "Actualizar listado",
        "decks.update.title": "Actualizar listado — {name}",
        "decks.update.submit": "Revisar actualización",
        "decks.update.summary": "Cartas en el listado: {before} → {after}",
        "decks.update.added": "Cartas a agregar ({count})",
        "decks.update.removed": "Cartas a quitar ({count})",
        "decks.update.unresolved": (
            "Líneas no reconocidas ({count}) — quedarán fuera del listado"
        ),
        "decks.update.no_changes": "El listado ya coincide; no hay nada que actualizar.",
        "decks.update.armed_warning": (
            "Este mazo está armado: al aplicar la actualización se reasignan sus "
            "copias físicas y se crean copias para las cartas nuevas del listado."
        ),
        "decks.update.apply": "Aplicar actualización",
        "decks.update.copies_hint": (
            "Libres = copias que ya tienes en inventario. Súbelas solo si necesitas "
            "agregar copias físicas (por ejemplo las tierras que faltaban en el listado)."
        ),
        "decks.delete_list": "Eliminar listado",
        "decks.delete.confirm.title": "Eliminar listado",
        "decks.delete.confirm.question": (
            "¿Eliminar “{name}”? Elige abajo cuántas copias físicas quitar "
            "junto con el listado."
        ),
        "decks.delete.copies.hint": (
            "Puedes quitar todas las copias eliminables, algunas o ninguna. "
            "Si Quitar se queda en 0, esas copias están en otros mazos armados."
        ),
        "decks.delete.copies.inventory": "En inventario",
        "decks.delete.copies.inventory_elsewhere": "{total} ({elsewhere} en otros mazos)",
        "decks.delete.copies.elsewhere_tip": (
            "{count} copia(s) asignada(s) a otros mazos armados; no se pueden quitar aquí."
        ),
        "decks.delete.copies.remove": "Quitar",
        "decks.delete.copies.remaining": "Quedarían",
        "decks.delete.copies.keep_all": "Conservar todas las copias",
        "decks.delete.copies.remove_all": "Quitar todas las eliminables",
        "decks.show_import": "Importar listado nuevo",
        "decks.load_file": "Cargar archivo",
        "decks.submit_import": "Confirmar listado",
        "decks.cancel_import": "Cancelar",
        "decks.load_file.dialog_title": "Abrir listado",
        "decks.edit.title": "Editar listado del mazo",
        "decks.edit.save": "Guardar listado",
        "decks.edit.total": "Cartas en listado: {current} / {target}",
        "decks.edit.total_only": "Cartas en listado: {current}",
        "decks.edit.size_mismatch": (
            "El listado tiene {current} cartas; este formato espera {target}. Aún puedes guardar."
        ),
        "decks.edit.slots": "Huecos libres: {slots}",
        "decks.edit.free": "Libres",
        "decks.edit.replace": "Reemplazar",
        "decks.edit.add": "Añadir carta",
        "decks.edit.add.title": "Añadir carta al listado",
        "decks.edit.replace.title": "Reemplazar carta",
        "decks.edit.search": "Buscar carta por nombre",
        "decks.edit.quantity": "Cantidad en listado",
        "decks.edit.available": "Copias disponibles (0 = faltan)",
        "decks.edit.remove_outgoing": "También quitar copias de la carta que sale",
        "decks.edit.remove_outgoing_qty": "Copias a quitar",
        "decks.edit.pick": "Usar carta seleccionada",
        "decks.edit.no_selection": "Selecciona una carta de los resultados.",
        "decks.edit.over_target": "El total del listado no puede superar el tamaño original.",
        "optimize.target": "Mazo a armar",
        "optimize.target.search": "Escribe nombre de mazo o commander…",
        "optimize.target.armed_suffix": "(armado)",
        "optimize.add": "Agregar al plan",
        "optimize.queue": "Conjunto a armar",
        "optimize.queue.remove": "Quitar del conjunto",
        "optimize.queue.viable": "viable",
        "optimize.queue.missing": "faltan cartas",
        "optimize.queue.armed": "ya armado",
        "optimize.queue.kept": "se mantiene armado",
        "optimize.run": "Calcular plan óptimo",
        "optimize.no_solutions": "No hay plan viable de desmontaje.",
        "optimize.no_solutions_set": "No es viable tener este conjunto todo armado a la vez.",
        "optimize.already_armed": "Este mazo ya está armado — no hay nada que optimizar.",
        "optimize.multiple": "Hay varios planes óptimos — elige uno:",
        "optimize.solution.suggested": "sugerida",
        "optimize.from_inventory": "Cartas cubiertas por inventario libre",
        "optimize.decks_to_dismantle": "Mazos a desarmar",
        "optimize.section_for": "---------- Para {deck} ----------",
        "optimize.summary.dismantle": "Desarmar {count} mazo(s) para armar este listado",
        "optimize.summary.inventory_only": "Armar desde inventario libre — no hace falta desarmar mazos",
        "optimize.summary.dismantle_set": "Desarmar {count} mazo(s) para armar este conjunto",
        "optimize.summary.inventory_only_set": "Armar este conjunto desde inventario libre — no hace falta desarmar mazos",
        "optimize.missing": "Aún faltan",
        "optimize.missing.need_to_find": "Faltan por encontrar",
        "optimize.unit.cards": "cartas",
        "optimize.unit.decks": "mazos",
        "optimize.confirm": "Confirmar plan",
        "optimize.cancel": "Cancelar",
        "optimize.apply.confirm_title": "¿Aplicar el plan de armado?",
        "optimize.apply.confirm_body": "Se desarmarán:\n{decks}\n\ny se armará:\n{target}",
        "optimize.apply.confirm_body_set": "Se desarmarán:\n{decks}\n\ny se armarán:\n{targets}",
        "optimize.apply.success": "Plan aplicado: mazos donantes desarmados y objetivo armado.",
        "optimize.apply.success_set": "Plan aplicado: donantes desarmados y el conjunto armado.",
        "optimize.card_qty": "{name} × {qty}",
        "optimize.section.assembly": "Plan de armado",
        "optimize.section.viable_plans": "Planes viables",
        "optimize.viable.max": "Mayor número viable",
        "optimize.viable.n": "{n} mazos",
        "optimize.viable.respect_locked": "Respetar mazos bloqueados (ɸ)",
        "optimize.viable.respect_locked.tip": "Las copias asignadas a mazos bloqueados no cubren a otros mazos del conjunto.",
        "optimize.viable.count": "{k} combinación(es) viable(s)",
        "optimize.viable.count_truncated": "Mostrando las primeras {k} combinación(es)…",
        "optimize.viable.count_max": "Máximo {n} mazos · {k} combinación(es)",
        "optimize.viable.count_max_truncated": "Máximo {n} mazos · mostrando las primeras {k}…",
        "optimize.viable.empty": "No hay combinaciones viables de este tamaño.",
        "optimize.viable.empty_max": "Ninguna agrupación de 2+ mazos cabe en la colección.",
        "optimize.viable.hint": "Conjuntos de mazos que la colección puede tener armados a la vez (solo copias físicas).",
        "optimize.viable.computing": "Calculando…",
        "optimize.viable.calculate": "Calcular combinaciones",
        "optimize.viable.recalculate": "Recalcular",
        "optimize.viable.recalculate_required": "Recalcular (obligatorio)",
        "optimize.viable.not_calculated": "Aún no calculado para este tamaño — pulsa Calcular.",
        "optimize.viable.stale_optional": "la colección cambió; se recomienda recalcular",
        "optimize.viable.stale_mandatory": "Se quitaron copias — hay que recalcular este tamaño.",
        "optimize.viable.filter": "Ver combinaciones con el mazo",
        "optimize.viable.filter.search": "Escribe nombre de mazo o commander…",
        "optimize.viable.filter.all": "Todos los mazos",
        "optimize.viable.count_filtered": "{shown} de {total} combinación(es) incluyen este mazo",
        "optimize.viable.combination": "Combinación #{n}",
        "optimize.viable.send_to_assembly": "Llevar a plan de armado",
        "optimize.viable.expand_all": "Expandir todas",
        "menu.language": "Idioma",
        "config.language": "Idioma",
        "config.theme": "Tema",
        "language.en": "English",
        "language.es": "Español",
        "theme.system": "Sistema",
        "theme.light": "Claro",
        "theme.dark": "Oscuro",
        "common.refresh": "Actualizar",
        "common.error": "Error",
        "common.success": "Éxito",
        "browse.section.overview": "Resumen",
        "browse.section.customize": "Personalizar",
        "browse.section.cards": "Cartas",
        "browse.section.decks": "Mazos",
        "browse.section.availability": "Disponibilidad",
        "browse.section.history": "Historial",
        "browse.section.scryfall": "Scryfall",
        "browse.history.filter": "Filtro",
        "browse.history.filter.all": "Todos",
        "browse.history.filter.inventory": "Inventario",
        "browse.history.filter.decks": "Mazos",
        "browse.history.when": "Cuándo",
        "browse.history.event": "Evento",
        "browse.history.empty": "Todavía no hay actividad registrada.",
        "browse.history.load_more": "Cargar más",
        "browse.history.export": "Exportar CSV",
        "browse.history.undo": "Deshacer último",
        "browse.history.undo.confirm": (
            "¿Deshacer el cambio más reciente?"
        ),
        "browse.history.redo": "Rehacer último",
        "browse.history.redo.confirm": (
            "¿Rehacer el cambio que acabas de deshacer?"
        ),
        "history.event.copies_added": "Añadidas {name} × {qty_delta}",
        "history.event.copies_removed": "Quitadas {name} × {qty_delta}",
        "history.event.deck_armed": "Armado {deck_name}",
        "history.event.deck_dismantled": "Desarmado {deck_name}",
        "history.event.deck_imported": "Importado {deck_name}",
        "history.event.deck_deleted": "Eliminado {deck_name}",
        "history.event.deck_list_edited": "Listado editado: {deck_name}",
        "history.event.plan_applied": (
            "Plan aplicado: armado {deck_name}"
            "{donors_suffix}"
        ),
        "history.event.plan_applied.donors": " (desarmados {donors})",
        "history.event.undone": "Deshecho: {detail}",
        "browse.overview.greeting": (
            " __  __  _______   _____         _____  \n"
            "|  \\/  ||__   __| / ____|       |  __ \\ \n"
            "| \\  / |   | |   | |  __ ______ | |__) |\n"
            "| |\\/| |   | |   | | |_ |______| |  _  / \n"
            "| |  | |   | |   | |__| |        | | \\ \\ \n"
            "|_|  |_|   |_|    \\_____|        |_|  \\_\\"
        ),
        "browse.overview.tagline": "Gestor de Colección Commander",
        "browse.overview.body": (
            "Cartas en caché: {cards}\n"
            "Copias físicas: {copies} ({unassigned} libres)\n"
            "Mazos: {decks} ({armed} armados)\n"
            "Entradas en listas: {deck_cards}\n"
            "Asignaciones de copias: {assignments}"
        ),
        "browse.cards.search": "Filtrar cartas por nombre",
        "browse.cards.name": "Nombre",
        "browse.cards.type": "Tipo",
        "browse.cards.cmc": "CMC",
        "browse.cards.copies": "Copias",
        "browse.cards.flags": "Etiquetas",
        "browse.cards.flag.basic": "básica",
        "browse.cards.flag.token": "token",
        "browse.overview.show_images": "Mostrar imágenes de cartas",
        "browse.overview.welcome_separator": "-----",
        "browse.overview.welcome": (
            "¡Bienvenido!\n"
            "Si es tu primera vez en este programa te recomendamos seguir "
            "el siguiente listado de pasos:\n"
            "1. Descarga el bulk de Scryfall para buscarlas y leerlas offline\n"
            "2. Importa en Inventario el listado de cartas libres que tengas "
            "en tu bulk personal\n"
            "3. Importa en Mazos el listado de cartas que tienes entre tus mazos "
            "armados y desarmados, agregándolos así a tu inventario\n"
            "4. Descarga las imágenes de las cartas dentro de tu colección\n"
            "5. Disfruta de la herramienta de optimización de Inventario para "
            "descubrir si te faltan copias en tu bulk"
        ),
        "browse.overview.track_editions": "Registrar ediciones de las cartas",
        "browse.overview.track_editions_hint": (
            "Agrega la columna Edición en Inventario y pide los códigos de set "
            "al rearmar un mazo. Las copias sin edición se muestran como «-»."
        ),
        "browse.customize.display": "Visualización",
        "browse.customize.warnings": "Avisos de mazos",
        "browse.customize.show_images": "Mostrar imágenes de cartas",
        "browse.customize.track_editions": "Registrar ediciones de las cartas",
        "browse.customize.track_editions_hint": (
            "Agrega la columna Edición en Inventario y pide los códigos de set "
            "al rearmar un mazo. Las copias sin edición se muestran como «-»."
        ),
        "browse.customize.show_legality_warnings": (
            "Mostrar avisos de legalidad Commander de Scryfall (⚠)"
        ),
        "browse.customize.show_rule_warnings": (
            "Mostrar avisos de reglas de juego Commander (⚠)"
        ),
        "browse.customize.house_ban.title": "Banlist casera",
        "browse.customize.house_ban.hint": (
            "Las cartas de esta lista siempre muestran un ⚠ informativo "
            "en los mazos que las incluyen."
        ),
        "browse.customize.house_ban.add": "Agregar carta…",
        "browse.customize.house_ban.remove": "Quitar seleccionada",
        "decks.legality.house_banned": "baneada en casa",
        "preview.title": "Imagen de la carta",
        "preview.empty": "Selecciona una carta para verla.",
        "preview.loading": "Cargando imagen…",
        "preview.missing": "Sin imagen disponible.",
        "preview.flip": "Girar carta",
        "browse.decks.quantity": "Cant.",
        "browse.decks.role": "Rol",
        "browse.inventory.copy": "Copia #",
        "browse.inventory.copies": "Copias",
        "browse.inventory.mixed": "{free} libres · {decks}",
        "browse.inventory.assigned": "Asignada a",
        "browse.inventory.free": "Libre",
        "browse.scryfall.sync_download": "Descargar pack bulk oracle-cards",
        "browse.scryfall.sync_update": "Actualizar pack bulk oracle-cards",
        "browse.scryfall.sync_current": "oracle-cards al día",
        "browse.scryfall.sync_resync": "Re-sincronizar pack oracle-cards",
        "browse.scryfall.sync_unique": "Usar unique-artwork (mejor arte)",
        "browse.scryfall.images_collection": "Descargar imágenes (colección)",
        "browse.scryfall.images_cached": "Descargar imágenes (caché completo)",
        "browse.scryfall.card_data_refresh": "Actualizar datos de cartas (colección)",
        "browse.scryfall.card_data_starting": "Actualizando datos de cartas…",
        "browse.scryfall.card_data_done": (
            "Legalidades Commander e imágenes actualizadas para "
            "{count:,} cartas de la colección."
        ),
        "browse.scryfall.starting": "Iniciando sincronización con Scryfall…",
        "browse.scryfall.done": "Se importaron {count:,} cartas desde {pack}.",
        "browse.scryfall.sync_failed": (
            "No se pudo sincronizar el pack bulk de Scryfall.\n\n{detail}"
        ),
        "browse.scryfall.images_failed": (
            "No se pudieron descargar las imágenes.\n\n{detail}"
        ),
        "browse.scryfall.card_data_failed": (
            "No se pudieron actualizar los datos de cartas.\n\n{detail}"
        ),
        "browse.scryfall.network_failed": (
            "No se pudo contactar con Scryfall.\n\n"
            "Revisa la conexión a internet e inténtalo de nuevo."
        ),
        "browse.scryfall.images_starting": "Iniciando descarga de imágenes…",
        "browse.scryfall.images_done": (
            "Imágenes: {downloaded:,} descargadas, {skipped:,} ya locales."
        ),
        "browse.scryfall.never": "Nunca",
        "browse.scryfall.none": "Ninguno",
        "browse.scryfall.update_yes": "Sí — hay pack más nuevo en Scryfall",
        "browse.scryfall.update_no": "No",
        "browse.scryfall.update_unknown": "Desconocido (sin red)",
        "browse.scryfall.status": (
            "Cartas en caché local: {cached}\n"
            "Pack local: {pack}\n"
            "Bulk de Scryfall actualizado: {bulk_updated}\n"
            "Última sync local: {last_synced}\n"
            "Cartas procesadas en la última sync: {imported}\n"
            "Actualización disponible: {update_available}\n"
            "Imágenes de colección en disco: {images_collection}\n"
            "Imágenes de caché en disco: {images_cached}"
        ),
        "browse.scryfall.info": (
            "Las búsquedas individuales por API se guardan en la caché local. "
            "Descarga oracle-cards una vez para resolver nombres sin conexión, o "
            "unique-artwork para mejor arte por defecto. "
            "La descarga de imágenes guarda JPEGs normal de Scryfall en "
            "data/images/ (colección o caché completo). "
            "Actualizar legalidades Commander refresca el estado de formato de "
            "las cartas que tienes o están en listados (más rápido que un sync "
            "bulk completo). "
            "Los símbolos de maná son SVG de Scryfall incluidos en la app; "
            "Scryfall no está afiliado ni respalda este software."
        ),
        "browse.scryfall.confirm_unique_title": "¿Usar unique-artwork?",
        "browse.scryfall.confirm_unique_body": (
            "Esto descarga el pack unique-artwork (~250 MB) y actualiza las "
            "URLs de arte locales. ¿Continuar?"
        ),
        "browse.scryfall.confirm_images_title": "¿Descargar imágenes del caché completo?",
        "browse.scryfall.confirm_images_body": (
            "Puede descargar decenas de miles de imágenes y tardar mucho. "
            "¿Continuar?"
        ),
    },
}


class Translator:
    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        self._locale = locale if locale in TRANSLATIONS else DEFAULT_LOCALE

    @property
    def locale(self) -> str:
        return self._locale

    def set_locale(self, locale: str) -> None:
        if locale in TRANSLATIONS:
            self._locale = locale

    def t(self, key: str) -> str:
        return TRANSLATIONS[self._locale].get(
            key,
            TRANSLATIONS[DEFAULT_LOCALE].get(key, key),
        )
