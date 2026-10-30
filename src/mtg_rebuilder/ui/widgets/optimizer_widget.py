from PySide6.QtCore import Qt, QThread, QSize, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QIcon, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.models.enums import DeckStatus
from mtg_rebuilder.repositories import CopyRepository
from mtg_rebuilder.services import DeckService, InventoryService, OptimizationService
from mtg_rebuilder.services.optimization_service import (
    AssemblyPlan,
    MovedCopy,
    ViablePlan,
    ViablePlansResult,
    sequence_is_viable,
    unique_donors_for_sequence,
)
from mtg_rebuilder.services.settings_service import SettingsService
from mtg_rebuilder.services.viable_plans_cache import (
    CacheFreshness,
    CollectionFingerprint,
    ViablePlansCacheStore,
    build_deck_signature,
    cache_entry_key,
    co_occurring_deck_ids,
    compare_fingerprints,
    filter_plans_containing,
)
from mtg_rebuilder.ui.combo import (
    SEARCHABLE_COMBO_CONTENTS_LENGTH,
    configure_data_combo,
)
from mtg_rebuilder.ui.widgets.card_preview import card_images_enabled
from mtg_rebuilder.ui.widgets.chip_bar import Chip, ChipBar
from mtg_rebuilder.algorithms.copy_traits import CopyTraits
from mtg_rebuilder.ui.widgets.edition_picker import CopyEditionTable
from mtg_rebuilder.ui.widgets.viable_commanders_column import (
    ViableCommandersColumn,
    ViableCommandersStrip,
)

ASSEMBLY_SECTION_INDEX = 0
VIABLE_SECTION_INDEX = 1
VIABLE_FIXED_N_MAX = 6
VIABLE_PLAN_ROLE = Qt.ItemDataRole.UserRole


class ViablePlansWorker(QThread):
    """Compute viable simultaneous sets off the GUI thread."""

    finished_ok = Signal(
        object, object, object, object
    )  # request_id, n, respect_locked, ViablePlansResult
    failed = Signal(
        object, object, object, object
    )  # request_id, n, respect_locked, error

    def __init__(
        self,
        request_id: int,
        n: int | None,
        respect_locked: bool,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._n = n
        self._respect_locked = respect_locked

    def run(self) -> None:
        try:
            with get_session() as session:
                result = OptimizationService(session).list_viable_plans(
                    n=self._n,
                    respect_locked=self._respect_locked,
                    should_stop=self.isInterruptionRequested,
                )
            if self.isInterruptionRequested():
                return
            self.finished_ok.emit(
                self._request_id, self._n, self._respect_locked, result
            )
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(
                    self._request_id, self._n, self._respect_locked, str(exc)
                )


class SpecifyEditionsDialog(QDialog):
    """Optional prompt after a rebuild: which edition is each moved copy?"""

    def __init__(
        self,
        translator: Translator,
        deck_name: str,
        copies: list[MovedCopy],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._traits: dict[int, CopyTraits] = {}
        self.setWindowTitle(self._translator.t("inventory.editions.prompt_title"))
        self.resize(980, 520)

        layout = QVBoxLayout(self)
        hint = QLabel(
            self._translator.t("inventory.editions.prompt_hint").format(deck=deck_name)
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._table = CopyEditionTable(self._translator)
        self._table.set_copies(
            [
                (
                    copy.copy_id,
                    copy.oracle_id,
                    copy.card_name,
                    CopyTraits(
                        finish=copy.finish,
                        language=copy.language,
                        condition=copy.condition,
                        collector_number=copy.collector_number,
                        printing_id=copy.printing_id,
                    ),
                )
                for copy in copies
            ]
        )
        layout.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        skip = buttons.addButton(
            self._translator.t("inventory.editions.skip"),
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        skip.clicked.connect(self.reject)
        buttons.accepted.connect(self._accept)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        self._traits = self._table.traits()
        self.accept()

    def traits(self) -> dict[int, CopyTraits]:
        return self._traits


class OptimizerWidget(QWidget):
    changed = Signal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._queue: list[int] = []
        self._plans: list[AssemblyPlan] = []
        self._chosen_solutions: dict[int, frozenset[str]] = {}
        self._current_plan: AssemblyPlan | None = None
        self._selection_committed = False
        self._recomputing_queue = False
        self._needs_reload = False
        self._deck_count = 0
        self._viable_mode_n: int | None = None  # None = largest viable set
        self._viable_workers: dict[str, tuple[int, ViablePlansWorker]] = {}
        self._viable_request_id = 0
        self._viable_plans: tuple[ViablePlan, ...] = ()
        self._viable_result_size = 0
        self._viable_truncated = False
        self._viable_freshness = CacheFreshness.MISSING
        self._viable_filter_deck_ids: list[int] = []
        self._viable_deck_labels: dict[int, str] = {}
        self._viable_fingerprint: CollectionFingerprint | None = None
        self._viable_shown_plans: tuple[ViablePlan, ...] = ()
        self._viable_image_view = False
        with get_session() as session:
            self._track_editions = SettingsService(session).get_track_editions()
        self._build_ui()
        self.refresh_decks()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        if self._needs_reload:
            self._reload_decks()

    def set_track_editions(self, enabled: bool) -> None:
        self._track_editions = enabled

    def set_show_card_images(self, enabled: bool) -> None:
        self._viable_image_view_button.setVisible(enabled)
        if not enabled and self._viable_image_view:
            self._set_viable_image_view(False)
            return
        self._update_viable_side_images_visibility()
        if not enabled:
            self._viable_commanders.clear()
        elif (
            self._section_list.currentRow() == VIABLE_SECTION_INDEX
            and not self._viable_image_view
        ):
            current = self._viable_results.currentItem()
            self._on_viable_combination_selected(current, None)

    def retranslate(self) -> None:
        self._section_list.item(ASSEMBLY_SECTION_INDEX).setText(
            self._translator.t("optimize.section.assembly")
        )
        self._section_list.item(VIABLE_SECTION_INDEX).setText(
            self._translator.t("optimize.section.viable_plans")
        )
        self._target_label.setText(self._translator.t("optimize.target"))
        self._add_button.setText(self._translator.t("optimize.add"))
        self._queue_group.setTitle(self._translator.t("optimize.queue"))
        self._remove_button.setText(self._translator.t("optimize.queue.remove"))
        self._confirm_button.setText(self._translator.t("optimize.confirm"))
        self._cancel_button.setText(self._translator.t("optimize.cancel"))
        line_edit = self._deck_combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(
                self._translator.t("optimize.target.search")
            )
        self._viable_respect.setText(
            self._translator.t("optimize.viable.respect_locked")
        )
        self._viable_respect.setToolTip(
            self._translator.t("optimize.viable.respect_locked.tip")
        )
        self._viable_hint.setText(self._translator.t("optimize.viable.hint"))
        self._viable_filter_label.setText(
            self._translator.t("optimize.viable.filter")
        )
        filter_edit = self._viable_filter_combo.lineEdit()
        if filter_edit is not None:
            filter_edit.setPlaceholderText(
                self._translator.t("optimize.viable.filter.search")
            )
        self._set_viable_filter_chip_texts()
        self._viable_send_button.setText(
            self._translator.t("optimize.viable.send_to_assembly")
        )
        self._viable_expand_all.setText(
            self._translator.t("optimize.viable.expand_all")
        )
        self._update_viable_image_view_button()
        self._rebuild_viable_mode_list()
        self._rebuild_viable_filter_combo()
        self._apply_section_titles_from_plan()
        self._refresh_queue_list()
        if self._plans:
            self._refresh_plan_display()
        else:
            self.refresh_decks()
        if self._section_list.currentRow() == VIABLE_SECTION_INDEX:
            self._load_viable_view()
        self._update_viable_action_button()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        splitter = QSplitter()
        root.addWidget(splitter)

        self._section_list = QListWidget()
        self._section_list.addItem(self._translator.t("optimize.section.assembly"))
        self._section_list.addItem(self._translator.t("optimize.section.viable_plans"))
        self._section_list.setMaximumWidth(200)
        splitter.addWidget(self._section_list)

        self._panels = QStackedWidget()
        splitter.addWidget(self._panels)
        splitter.setStretchFactor(1, 1)

        assembly = QWidget()
        self._build_assembly_ui(assembly)
        self._panels.addWidget(assembly)
        self._panels.addWidget(self._build_viable_ui())

        self._section_list.currentRowChanged.connect(self._on_section_changed)
        self._section_list.setCurrentRow(ASSEMBLY_SECTION_INDEX)

    def _on_section_changed(self, index: int) -> None:
        self._panels.setCurrentIndex(index)
        if index == VIABLE_SECTION_INDEX:
            self._load_viable_view()

    def _build_viable_ui(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self._viable_hint = QLabel(self._translator.t("optimize.viable.hint"))
        self._viable_hint.setWordWrap(True)
        layout.addWidget(self._viable_hint)

        self._viable_respect = QCheckBox(
            self._translator.t("optimize.viable.respect_locked")
        )
        self._viable_respect.setToolTip(
            self._translator.t("optimize.viable.respect_locked.tip")
        )
        self._viable_respect.stateChanged.connect(self._on_viable_options_changed)
        layout.addWidget(self._viable_respect)

        body = QHBoxLayout()
        self._viable_mode_list = QListWidget()
        self._viable_mode_list.setMaximumWidth(220)
        self._viable_mode_list.currentRowChanged.connect(self._on_viable_mode_changed)
        body.addWidget(self._viable_mode_list)

        right = QVBoxLayout()
        filter_row = QHBoxLayout()
        self._viable_filter_label = QLabel(
            self._translator.t("optimize.viable.filter")
        )
        self._viable_filter_combo = QComboBox()
        self._viable_filter_combo.setEditable(True)
        self._viable_filter_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        configure_data_combo(self._viable_filter_combo, min_contents=28)
        filter_edit = self._viable_filter_combo.lineEdit()
        filter_edit.setPlaceholderText(
            self._translator.t("optimize.viable.filter.search")
        )
        filter_edit.setClearButtonEnabled(True)
        filter_completer = QCompleter(
            self._viable_filter_combo.model(), self._viable_filter_combo
        )
        filter_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        filter_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        filter_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._viable_filter_combo.setCompleter(filter_completer)
        self._viable_filter_combo.activated.connect(self._on_viable_filter_activated)
        filter_completer.activated[str].connect(self._on_viable_filter_completed)
        filter_edit.returnPressed.connect(self._on_viable_filter_return)
        filter_row.addWidget(self._viable_filter_label)
        filter_row.addWidget(self._viable_filter_combo, 1)
        right.addLayout(filter_row)

        self._viable_filter_chips = ChipBar()
        self._viable_filter_chips.chip_removed.connect(self._on_viable_filter_chip_removed)
        self._viable_filter_chips.cleared.connect(self._clear_viable_filter)
        self._set_viable_filter_chip_texts()
        right.addWidget(self._viable_filter_chips)

        self._viable_status = QLabel("")
        self._viable_status.setWordWrap(True)
        status_row = QHBoxLayout()
        status_row.addWidget(self._viable_status, stretch=1)
        self._viable_image_view_button = QPushButton()
        self._viable_image_view_button.setCheckable(True)
        self._viable_image_view_button.clicked.connect(self._toggle_viable_image_view)
        self._viable_image_view_button.setVisible(card_images_enabled())
        self._update_viable_image_view_button()
        status_row.addWidget(self._viable_image_view_button, stretch=0)
        right.addLayout(status_row)

        results_row = QHBoxLayout()

        list_col = QVBoxLayout()
        self._viable_action = QPushButton()
        self._viable_action.clicked.connect(self._compute_viable_plans)
        list_col.addWidget(self._viable_action)
        self._viable_expand_all = QCheckBox(
            self._translator.t("optimize.viable.expand_all")
        )
        self._viable_expand_all.setChecked(True)
        self._viable_expand_all.toggled.connect(self._on_viable_expand_all_toggled)
        list_col.addWidget(self._viable_expand_all)
        self._viable_results = QTreeWidget()
        self._viable_results.setHeaderHidden(True)
        self._viable_results.setRootIsDecorated(True)
        self._viable_results.setAnimated(True)
        self._viable_results.setUniformRowHeights(True)
        self._viable_results.setIndentation(18)
        self._viable_results.currentItemChanged.connect(
            self._on_viable_combination_selected
        )
        list_col.addWidget(self._viable_results, stretch=1)
        results_row.addLayout(list_col, stretch=1)

        images_col = QVBoxLayout()
        self._viable_send_button = QPushButton(
            self._translator.t("optimize.viable.send_to_assembly")
        )
        self._viable_send_button.setEnabled(False)
        self._viable_send_button.clicked.connect(self._send_viable_to_assembly)
        images_col.addWidget(self._viable_send_button)
        self._viable_commanders = ViableCommandersColumn(self._translator)
        self._update_viable_side_images_visibility()
        images_col.addWidget(self._viable_commanders, stretch=1)
        results_row.addLayout(images_col, stretch=0)

        right.addLayout(results_row, stretch=1)
        body.addLayout(right, stretch=1)
        layout.addLayout(body, stretch=1)

        self._rebuild_viable_mode_list()
        self._rebuild_viable_filter_combo()
        self._update_viable_action_button()
        return panel

    def _rebuild_viable_mode_list(self) -> None:
        previous = self._viable_mode_n
        self._viable_mode_list.blockSignals(True)
        self._viable_mode_list.clear()
        max_item = QListWidgetItem(self._viable_mode_label(None))
        max_item.setData(Qt.ItemDataRole.UserRole, None)
        self._viable_mode_list.addItem(max_item)
        upper = min(VIABLE_FIXED_N_MAX, self._deck_count) if self._deck_count else VIABLE_FIXED_N_MAX
        for n in range(2, upper + 1):
            item = QListWidgetItem(self._viable_mode_label(n))
            item.setData(Qt.ItemDataRole.UserRole, n)
            self._viable_mode_list.addItem(item)
        select_row = 0
        for row in range(self._viable_mode_list.count()):
            if self._viable_mode_list.item(row).data(Qt.ItemDataRole.UserRole) == previous:
                select_row = row
                break
        self._viable_mode_list.setCurrentRow(select_row)
        self._viable_mode_n = self._viable_mode_list.item(select_row).data(
            Qt.ItemDataRole.UserRole
        )
        self._viable_mode_list.blockSignals(False)
        self._update_viable_mode_counts()

    def _viable_mode_label(self, n: int | None) -> str:
        if n is None:
            return self._translator.t("optimize.viable.max")
        return self._translator.t("optimize.viable.n").format(n=n)

    def _cached_viable_plans_by_mode(self) -> dict[int | None, tuple[ViablePlan, ...]]:
        """Calculated combinations of every size in the list, for the current ɸ.

        Sizes never calculated (or needing a mandatory recalculation) are left
        out: counting or suggesting from them would be a guess.
        """
        respect = self._viable_respect.isChecked()
        entries: dict[int | None, tuple[ViablePlan, ...]] = {}
        with get_session() as session:
            store = self._viable_cache_store(session)
            for row in range(self._viable_mode_list.count()):
                n = self._viable_mode_list.item(row).data(Qt.ItemDataRole.UserRole)
                entry = store.get_entry(n, respect)
                if entry is None:
                    continue
                if (
                    self._viable_fingerprint is not None
                    and compare_fingerprints(
                        store.fingerprint_for(n, respect), self._viable_fingerprint
                    )
                    == CacheFreshness.MANDATORY
                ):
                    continue
                entries[n] = entry.plans
        return entries

    def _update_viable_mode_counts(self) -> None:
        """With decks in the filter, suffix each calculated size with its matches."""
        selected = self._viable_filter_deck_ids
        entries = self._cached_viable_plans_by_mode() if selected else {}
        for row in range(self._viable_mode_list.count()):
            item = self._viable_mode_list.item(row)
            n = item.data(Qt.ItemDataRole.UserRole)
            label = self._viable_mode_label(n)
            plans = entries.get(n)
            if plans is not None:
                label = self._translator.t("optimize.viable.mode_count").format(
                    label=label, k=len(filter_plans_containing(plans, selected))
                )
            item.setText(label)

    def _rebuild_viable_filter_combo(self) -> None:
        """Offer only decks that still co-occur with the decks already picked.

        Suggestions come from every calculated size, not just the one on screen,
        so a deck can be added from a size where the current pick has no
        matches. The picked decks survive size / ɸ changes, so only decks that
        no longer exist are dropped. With nothing left to add the combo is
        disabled so the completer cannot suggest decks that would empty every
        size.
        """
        with get_session() as session:
            service = DeckService(session)
            commander_names = service.commander_names_by_deck()
            self._viable_deck_labels = {
                deck.id: self._picker_label(
                    deck.name,
                    commander_names.get(deck.id),
                    deck.status == DeckStatus.ARMED,
                )
                for deck in service.list_decks()
            }
        self._viable_filter_deck_ids = [
            deck_id
            for deck_id in self._viable_filter_deck_ids
            if deck_id in self._viable_deck_labels
        ]
        allowed: set[int] = set(
            co_occurring_deck_ids(self._viable_plans, self._viable_filter_deck_ids)
        )
        for plans in self._cached_viable_plans_by_mode().values():
            allowed.update(
                co_occurring_deck_ids(plans, self._viable_filter_deck_ids)
            )
        typed = self._viable_filter_combo.currentText()
        self._viable_filter_combo.blockSignals(True)
        self._viable_filter_combo.clear()
        for deck_id, label in self._viable_deck_labels.items():
            if deck_id in allowed:
                self._viable_filter_combo.addItem(label, deck_id)
        completer = self._viable_filter_combo.completer()
        if completer is not None:
            completer.setModel(self._viable_filter_combo.model())
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._viable_filter_combo.setCurrentIndex(-1)
        self._viable_filter_combo.setEditText(typed if allowed else "")
        self._viable_filter_combo.setEnabled(bool(allowed))
        self._viable_filter_combo.blockSignals(False)
        self._refresh_viable_filter_chips()

    def _set_viable_filter_chip_texts(self) -> None:
        self._viable_filter_chips.set_texts(
            remove_tooltip=self._translator.t("optimize.viable.filter.chip_remove_tip"),
            clear_text=self._translator.t("optimize.viable.filter.clear"),
        )

    def _refresh_viable_filter_chips(self) -> None:
        self._viable_filter_chips.set_chips(
            [
                Chip(deck_id, self._viable_deck_labels.get(deck_id, str(deck_id)))
                for deck_id in self._viable_filter_deck_ids
            ]
        )

    def _on_viable_mode_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self._viable_mode_list.item(row)
        if item is None:
            return
        self._viable_mode_n = item.data(Qt.ItemDataRole.UserRole)
        if self._section_list.currentRow() == VIABLE_SECTION_INDEX:
            self._load_viable_view()

    def _on_viable_options_changed(self) -> None:
        if self._section_list.currentRow() == VIABLE_SECTION_INDEX:
            self._load_viable_view()

    def _on_viable_filter_activated(self, index: int) -> None:
        self._add_viable_filter_deck(self._viable_filter_combo.itemData(index))

    def _on_viable_filter_completed(self, text: str) -> None:
        index = self._viable_filter_combo.findText(
            text, Qt.MatchFlag.MatchFixedString
        )
        if index >= 0:
            self._add_viable_filter_deck(self._viable_filter_combo.itemData(index))

    def _on_viable_filter_return(self) -> None:
        self._add_viable_filter_deck(self._typed_viable_filter_deck_id())

    def _typed_viable_filter_deck_id(self) -> int | None:
        needle = self._viable_filter_combo.currentText().strip().casefold()
        if not needle:
            return None
        labels = [
            (self._viable_filter_combo.itemText(i).casefold(),
             self._viable_filter_combo.itemData(i))
            for i in range(self._viable_filter_combo.count())
        ]
        for label, data in labels:
            if isinstance(data, int) and label == needle:
                return data
        for label, data in labels:
            if isinstance(data, int) and needle in label:
                return data
        return None

    def _add_viable_filter_deck(self, deck_id: object) -> None:
        if not isinstance(deck_id, int) or deck_id in self._viable_filter_deck_ids:
            return
        self._viable_filter_deck_ids.append(deck_id)
        self._on_viable_filter_selection_changed()
        # The completer writes the picked label back after its signal fires.
        QTimer.singleShot(0, lambda: self._viable_filter_combo.setEditText(""))

    def _on_viable_filter_chip_removed(self, deck_id: object) -> None:
        if deck_id in self._viable_filter_deck_ids:
            self._viable_filter_deck_ids.remove(deck_id)
            self._on_viable_filter_selection_changed()

    def _clear_viable_filter(self) -> None:
        if self._viable_filter_deck_ids:
            self._viable_filter_deck_ids.clear()
            self._on_viable_filter_selection_changed()

    def _on_viable_filter_selection_changed(self) -> None:
        self._rebuild_viable_filter_combo()
        self._update_viable_mode_counts()
        self._render_viable_results()

    def _current_fingerprint(self) -> CollectionFingerprint:
        with get_session() as session:
            decks = DeckService(session)
            rows: list[tuple[int, str, int, bool]] = []
            for deck in decks.list_decks():
                req = decks.deck_requirements(deck.id)
                rows.append(
                    (deck.id, deck.name, sum(req.values()), bool(deck.is_locked))
                )
            copy_count = CopyRepository(session).count_all()
        return CollectionFingerprint(
            copy_count=copy_count,
            deck_sig=build_deck_signature(rows),
        )

    def _viable_cache_store(self, session) -> ViablePlansCacheStore:
        return ViablePlansCacheStore(SettingsService(session))

    def _viable_current_key(self) -> str:
        return cache_entry_key(
            self._viable_mode_n, self._viable_respect.isChecked()
        )

    def _is_viable_computing(self, key: str | None = None) -> bool:
        return (key or self._viable_current_key()) in self._viable_workers

    def _load_viable_view(self) -> None:
        """Show cached combos for the current N/ɸ, or prompt to calculate.

        Does not cancel in-flight jobs — switching N/tabs keeps them running.
        """
        respect = self._viable_respect.isChecked()
        fingerprint = self._current_fingerprint()
        self._viable_fingerprint = fingerprint
        with get_session() as session:
            store = self._viable_cache_store(session)
            freshness = store.freshness_for(
                self._viable_mode_n, respect, fingerprint
            )
            if freshness == CacheFreshness.MANDATORY:
                store.clear_entries_with_mandatory(fingerprint)
                cached = None
            else:
                cached = store.get_entry(self._viable_mode_n, respect)
        self._viable_freshness = freshness
        if freshness == CacheFreshness.MANDATORY or cached is None:
            self._viable_plans = ()
            self._viable_result_size = 0
            self._viable_truncated = False
            if freshness != CacheFreshness.MANDATORY:
                self._viable_freshness = CacheFreshness.MISSING
        else:
            self._viable_plans = cached.plans
            self._viable_result_size = cached.size
            self._viable_truncated = cached.truncated
            self._viable_freshness = freshness
        self._rebuild_viable_filter_combo()
        self._update_viable_mode_counts()
        self._update_viable_action_button()
        self._render_viable_results()

    def _update_viable_action_button(self) -> None:
        if self._is_viable_computing():
            self._viable_action.setText(
                self._translator.t("optimize.viable.computing")
            )
            self._viable_action.setEnabled(False)
            self._viable_action.setVisible(True)
            return
        if self._viable_freshness == CacheFreshness.MANDATORY:
            self._viable_action.setText(
                self._translator.t("optimize.viable.recalculate_required")
            )
            self._viable_action.setEnabled(True)
            self._viable_action.setVisible(True)
        elif self._viable_freshness == CacheFreshness.MISSING:
            self._viable_action.setText(
                self._translator.t("optimize.viable.calculate")
            )
            self._viable_action.setEnabled(True)
            self._viable_action.setVisible(True)
        elif self._viable_freshness == CacheFreshness.OPTIONAL:
            self._viable_action.setText(
                self._translator.t("optimize.viable.recalculate")
            )
            self._viable_action.setEnabled(True)
            self._viable_action.setVisible(True)
        else:
            self._viable_action.setText(
                self._translator.t("optimize.viable.recalculate")
            )
            self._viable_action.setEnabled(True)
            self._viable_action.setVisible(True)

    def _compute_viable_plans(self) -> None:
        """Explicit calculate/recalculate for the currently selected N only."""
        respect = self._viable_respect.isChecked()
        key = cache_entry_key(self._viable_mode_n, respect)
        if key in self._viable_workers:
            return
        self._viable_request_id += 1
        request_id = self._viable_request_id
        self._viable_status.setText(self._translator.t("optimize.viable.computing"))
        worker = ViablePlansWorker(request_id, self._viable_mode_n, respect)
        worker.finished_ok.connect(self._on_viable_plans_ready)
        worker.failed.connect(self._on_viable_plans_failed)
        self._viable_workers[key] = (request_id, worker)
        self._update_viable_action_button()
        worker.start()

    def _drop_viable_worker(self, key: str, request_id: int) -> ViablePlansWorker | None:
        entry = self._viable_workers.get(key)
        if entry is None or entry[0] != request_id:
            return None
        worker = entry[1]
        del self._viable_workers[key]
        try:
            worker.finished_ok.disconnect(self._on_viable_plans_ready)
            worker.failed.disconnect(self._on_viable_plans_failed)
        except (RuntimeError, TypeError):
            pass
        return worker

    def _on_viable_plans_ready(
        self,
        request_id: int,
        n: object,
        respect_locked: object,
        result: object,
    ) -> None:
        respect = bool(respect_locked)
        size_n: int | None = n if isinstance(n, int) or n is None else None
        if not isinstance(n, int) and n is not None:
            return
        key = cache_entry_key(size_n, respect)
        self._drop_viable_worker(key, request_id)
        if not isinstance(result, ViablePlansResult):
            if key == self._viable_current_key():
                self._update_viable_action_button()
            return
        fingerprint = self._current_fingerprint()
        self._viable_fingerprint = fingerprint
        with get_session() as session:
            store = self._viable_cache_store(session)
            store.put_entry(size_n, respect, result, fingerprint)
        if respect == self._viable_respect.isChecked():
            self._update_viable_mode_counts()
            if key != self._viable_current_key():
                self._rebuild_viable_filter_combo()
        if key != self._viable_current_key():
            return
        self._viable_plans = result.plans
        self._viable_result_size = result.size
        self._viable_truncated = result.truncated
        self._viable_freshness = CacheFreshness.FRESH
        self._rebuild_viable_filter_combo()
        self._update_viable_action_button()
        self._render_viable_results()

    def _on_viable_plans_failed(
        self,
        request_id: int,
        n: object,
        respect_locked: object,
        message: object,
    ) -> None:
        respect = bool(respect_locked)
        if not isinstance(n, int) and n is not None:
            return
        size_n: int | None = n if isinstance(n, int) else None
        key = cache_entry_key(size_n, respect)
        self._drop_viable_worker(key, request_id)
        if key != self._viable_current_key():
            return
        self._viable_status.setText(
            self._translator.t("common.error") + f": {message}"
        )
        self._update_viable_action_button()

    def _render_viable_results(self) -> None:
        filtered = filter_plans_containing(
            self._viable_plans, self._viable_filter_deck_ids
        )
        self._viable_shown_plans = filtered
        self._rebuild_viable_tree(filtered)
        self._update_viable_side_images_visibility()
        self._viable_expand_all.setEnabled(bool(filtered))

        if self._is_viable_computing():
            self._viable_status.setText(
                self._translator.t("optimize.viable.computing")
            )
            return

        is_max = self._viable_mode_n is None
        total = len(self._viable_plans)
        shown = len(filtered)
        filtering = bool(self._viable_filter_deck_ids)

        if self._viable_freshness == CacheFreshness.MANDATORY:
            self._viable_status.setText(
                self._translator.t("optimize.viable.stale_mandatory")
            )
            self._viable_commanders.clear()
            return
        if self._viable_freshness == CacheFreshness.MISSING and total == 0:
            self._viable_status.setText(
                self._translator.t("optimize.viable.not_calculated")
            )
            self._viable_commanders.clear()
            return
        if total == 0:
            self._viable_status.setText(
                self._translator.t(
                    "optimize.viable.empty_max" if is_max else "optimize.viable.empty"
                )
            )
            self._viable_commanders.clear()
            return

        if filtering:
            base = self._translator.t("optimize.viable.count_filtered").format(
                shown=shown, total=total
            )
        elif is_max:
            key = (
                "optimize.viable.count_max_truncated"
                if self._viable_truncated
                else "optimize.viable.count_max"
            )
            base = self._translator.t(key).format(
                n=self._viable_result_size, k=total
            )
        else:
            key = (
                "optimize.viable.count_truncated"
                if self._viable_truncated
                else "optimize.viable.count"
            )
            base = self._translator.t(key).format(k=total)

        if self._viable_freshness == CacheFreshness.OPTIONAL:
            base = (
                f"{base} — {self._translator.t('optimize.viable.stale_optional')}"
            )
        self._viable_status.setText(base)

    def _rebuild_viable_tree(self, plans: tuple[ViablePlan, ...]) -> None:
        """Grouped collapsible combinations: title + names or commander images."""
        self._viable_results.blockSignals(True)
        self._viable_results.clear()
        image_mode = self._viable_image_view and card_images_enabled()
        self._viable_results.setUniformRowHeights(not image_mode)
        expand = self._viable_expand_all.isChecked()
        for index, plan in enumerate(plans, start=1):
            header = QTreeWidgetItem(
                [
                    self._translator.t("optimize.viable.combination").format(n=index)
                ]
            )
            header.setData(0, VIABLE_PLAN_ROLE, index - 1)
            font = header.font(0)
            font.setBold(True)
            header.setFont(0, font)
            header.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            self._viable_results.addTopLevelItem(header)
            if image_mode:
                child = QTreeWidgetItem([""])
                child.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                header.addChild(child)
                strip = ViableCommandersStrip(self._translator)
                strip.set_commanders(self._commanders_for_viable_plan(plan))
                self._viable_results.setItemWidget(child, 0, strip)
                viewport_w = max(self._viable_results.viewport().width() - 40, 200)
                child.setSizeHint(
                    0, QSize(viewport_w, strip.heightForWidth(viewport_w))
                )
            else:
                for name in plan.deck_names:
                    child = QTreeWidgetItem([name])
                    child.setFlags(
                        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    )
                    header.addChild(child)
            header.setExpanded(expand)
        self._viable_results.blockSignals(False)
        if plans:
            first = self._viable_results.topLevelItem(0)
            if first is not None:
                self._viable_results.setCurrentItem(first)
                self._on_viable_combination_selected(first, None)
        else:
            self._viable_commanders.clear()
            self._viable_send_button.setEnabled(False)

    def _on_viable_expand_all_toggled(self, checked: bool) -> None:
        self._viable_results.blockSignals(True)
        for row in range(self._viable_results.topLevelItemCount()):
            item = self._viable_results.topLevelItem(row)
            if item is not None:
                item.setExpanded(checked)
        self._viable_results.blockSignals(False)

    def _update_viable_image_view_button(self) -> None:
        key = (
            "inventory.view.images_active"
            if self._viable_image_view
            else "inventory.view.images"
        )
        self._viable_image_view_button.setText(self._translator.t(key))
        self._viable_image_view_button.setChecked(self._viable_image_view)

    def _toggle_viable_image_view(self) -> None:
        self._set_viable_image_view(self._viable_image_view_button.isChecked())

    def _set_viable_image_view(self, active: bool) -> None:
        if not card_images_enabled():
            active = False
        if active == self._viable_image_view:
            self._update_viable_image_view_button()
            return
        previous = self._viable_plan_from_item(self._viable_results.currentItem())
        previous_ids = previous.deck_ids if previous is not None else None
        self._viable_image_view = active
        self._update_viable_image_view_button()
        self._update_viable_side_images_visibility()
        if self._section_list.currentRow() != VIABLE_SECTION_INDEX:
            return
        self._rebuild_viable_tree(self._viable_shown_plans)
        if previous_ids is None:
            return
        for row in range(self._viable_results.topLevelItemCount()):
            item = self._viable_results.topLevelItem(row)
            plan = self._viable_plan_from_item(item)
            if plan is not None and plan.deck_ids == previous_ids:
                self._viable_results.setCurrentItem(item)
                self._on_viable_combination_selected(item, None)
                break

    def _update_viable_side_images_visibility(self) -> None:
        show = (
            card_images_enabled()
            and not self._viable_image_view
        )
        self._viable_commanders.setVisible(show)
        if not show:
            self._viable_commanders.clear()

    def _viable_plan_from_item(
        self, item: QTreeWidgetItem | None
    ) -> ViablePlan | None:
        if item is None:
            return None
        while item.parent() is not None:
            item = item.parent()
        index = item.data(0, VIABLE_PLAN_ROLE)
        if not isinstance(index, int):
            return None
        if index < 0 or index >= len(self._viable_shown_plans):
            return None
        return self._viable_shown_plans[index]

    def _on_viable_combination_selected(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        plan = self._viable_plan_from_item(current)
        self._viable_send_button.setEnabled(plan is not None)
        if plan is None or self._viable_image_view or not card_images_enabled():
            self._viable_commanders.clear()
            return
        self._viable_commanders.set_commanders(
            self._commanders_for_viable_plan(plan)
        )

    def _send_viable_to_assembly(self) -> None:
        """Open Plan de Armado with this combination queued in alphabetical order."""
        plan = self._viable_plan_from_item(self._viable_results.currentItem())
        if plan is None:
            return
        ordered = [
            deck_id
            for _name, deck_id in sorted(
                zip(plan.deck_names, plan.deck_ids, strict=True),
                key=lambda pair: pair[0].casefold(),
            )
        ]
        self._chosen_solutions.clear()
        self._queue = ordered
        self._section_list.setCurrentRow(ASSEMBLY_SECTION_INDEX)
        select = ordered[0] if ordered else None
        self._recompute_queue_plans(select_deck_id=select)

    def _commanders_for_viable_plan(
        self, plan: ViablePlan
    ) -> list[tuple[str, str]]:
        """Primary commander image per deck in the combination (grid wraps by 3)."""
        cards: list[tuple[str, str]] = []
        with get_session() as session:
            service = DeckService(session)
            for deck_id in plan.deck_ids:
                zone = service.command_zone_cards(deck_id)
                if not zone:
                    continue
                oracle_id, name = zone[0]
                cards.append((oracle_id, name))
        return cards

    def _build_assembly_ui(self, panel: QWidget) -> None:
        layout = QVBoxLayout(panel)

        form = QFormLayout()
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        picker_row = QHBoxLayout()
        self._deck_combo = QComboBox()
        self._deck_combo.setEditable(True)
        self._deck_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        configure_data_combo(self._deck_combo, min_contents=32)
        line_edit = self._deck_combo.lineEdit()
        line_edit.setPlaceholderText(self._translator.t("optimize.target.search"))
        line_edit.setClearButtonEnabled(True)
        search_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogContentsView
        )
        search_action = QAction(
            search_icon if not search_icon.isNull() else QIcon(),
            "",
            self,
        )
        search_action.setEnabled(False)
        line_edit.addAction(search_action, line_edit.ActionPosition.LeadingPosition)
        completer = QCompleter(self._deck_combo.model(), self._deck_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._deck_combo.setCompleter(completer)
        self._deck_combo.activated.connect(self._commit_combo_selection)
        line_edit.textChanged.connect(self._on_combo_text_changed)
        line_edit.returnPressed.connect(self._commit_combo_selection)
        self._add_button = QPushButton(self._translator.t("optimize.add"))
        self._add_button.clicked.connect(self._add_selected_to_queue)
        picker_row.addWidget(self._deck_combo, 1)
        picker_row.addWidget(self._add_button)
        self._target_label = QLabel(self._translator.t("optimize.target"))
        form.addRow(self._target_label, picker_row)
        layout.addLayout(form)

        self._queue_group = QGroupBox(self._translator.t("optimize.queue"))
        queue_layout = QVBoxLayout(self._queue_group)
        self._queue_list = QListWidget()
        self._queue_list.setMaximumHeight(140)
        self._queue_list.currentRowChanged.connect(self._on_queue_selection_changed)
        queue_layout.addWidget(self._queue_list)
        self._remove_button = QPushButton(self._translator.t("optimize.queue.remove"))
        self._remove_button.clicked.connect(self._remove_selected_from_queue)
        queue_layout.addWidget(self._remove_button)
        layout.addWidget(self._queue_group)
        self._queue_group.setVisible(False)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_font = QFont(self._summary.font())
        summary_font.setPointSize(summary_font.pointSize() + 5)
        summary_font.setBold(True)
        self._summary.setFont(summary_font)
        self._summary.setMinimumHeight(48)
        layout.addWidget(self._summary)

        self._inventory_group = QGroupBox()
        inventory_layout = QVBoxLayout(self._inventory_group)
        self._inventory_list = QListWidget()
        self._inventory_list.setMaximumHeight(160)
        inventory_layout.addWidget(self._inventory_list)
        layout.addWidget(self._inventory_group)

        self._solution_group = QGroupBox()
        solution_layout = QVBoxLayout(self._solution_group)
        self._solution_combo = QComboBox()
        configure_data_combo(
            self._solution_combo, min_contents=SEARCHABLE_COMBO_CONTENTS_LENGTH
        )
        self._solution_combo.currentIndexChanged.connect(self._on_solution_changed)
        solution_layout.addWidget(self._solution_combo)
        self._step_combos_host = QWidget()
        self._step_combos_layout = QVBoxLayout(self._step_combos_host)
        self._step_combos_layout.setContentsMargins(0, 0, 0, 0)
        solution_layout.addWidget(self._step_combos_host)
        self._step_combos_host.setVisible(False)
        self._solution_tree = QTreeWidget()
        self._solution_tree.setHeaderHidden(True)
        self._solution_tree.setRootIsDecorated(True)
        self._solution_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        solution_layout.addWidget(self._solution_tree, stretch=1)
        buttons = QHBoxLayout()
        self._confirm_button = QPushButton(self._translator.t("optimize.confirm"))
        self._cancel_button = QPushButton(self._translator.t("optimize.cancel"))
        self._confirm_button.clicked.connect(self._confirm_plan)
        self._cancel_button.clicked.connect(self._cancel_plan)
        buttons.addWidget(self._confirm_button)
        buttons.addWidget(self._cancel_button)
        solution_layout.addLayout(buttons)
        layout.addWidget(self._solution_group, stretch=1)
        self._set_plan_actions_visible(False)
        self._step_solution_combos: dict[int, QComboBox] = {}

        self._missing_group = QGroupBox()
        missing_layout = QVBoxLayout(self._missing_group)
        self._missing_tree = QTreeWidget()
        self._missing_tree.setHeaderHidden(True)
        self._missing_tree.setRootIsDecorated(True)
        self._missing_tree.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        missing_layout.addWidget(self._missing_tree, stretch=1)
        layout.addWidget(self._missing_group, stretch=1)
        self._missing_group.setVisible(False)

        self._set_section_titles(0, 0, 0)

    def _set_plan_actions_visible(self, visible: bool) -> None:
        self._confirm_button.setVisible(visible)
        self._cancel_button.setVisible(visible)

    def _counted_title(self, label_key: str, count: int, unit_key: str) -> str:
        return (
            f"{self._translator.t(label_key)} - {count} "
            f"{self._translator.t(unit_key)}"
        )

    def _set_section_titles(
        self,
        inventory_cards: int,
        decks: int,
        missing_cards: int,
    ) -> None:
        self._inventory_group.setTitle(
            self._counted_title(
                "optimize.from_inventory",
                inventory_cards,
                "optimize.unit.cards",
            )
        )
        self._solution_group.setTitle(
            self._counted_title(
                "optimize.decks_to_dismantle",
                decks,
                "optimize.unit.decks",
            )
        )
        self._missing_group.setTitle(
            self._counted_title(
                "optimize.missing",
                missing_cards,
                "optimize.unit.cards",
            )
        )

    def _apply_section_titles_from_plan(self) -> None:
        if not self._plans:
            self._set_section_titles(0, 0, 0)
            return
        if len(self._plans) == 1:
            plan = self._plans[0]
            inventory_cards = sum(plan.free_inventory_used.values())
            missing_cards = sum(plan.still_missing.values())
            decks = 0
            if not plan.still_missing and plan.result.solutions:
                decks = plan.result.minimum_decks_to_dismantle
            self._set_section_titles(inventory_cards, decks, missing_cards)
            return
        inventory_cards = sum(
            sum(plan.free_inventory_used.values()) for plan in self._plans
        )
        missing_cards = sum(sum(plan.still_missing.values()) for plan in self._plans)
        decks = 0
        if sequence_is_viable(self._plans):
            decks = len(unique_donors_for_sequence(self._plans, self._chosen_solutions))
        self._set_section_titles(inventory_cards, decks, missing_cards)

    def _card_qty_label(self, plan: AssemblyPlan, card_id: str, qty: int) -> str:
        name = plan.card_names.get(card_id, card_id)
        return self._translator.t("optimize.card_qty").format(name=name, qty=qty)

    def _section_header(self, deck_name: str) -> str:
        return self._translator.t("optimize.section_for").format(deck=deck_name)

    @staticmethod
    def _deck_label(name: str, commander: str | None) -> str:
        if commander:
            return f"{name} — {commander}"
        return name

    def _picker_label(
        self, name: str, commander: str | None, armed: bool
    ) -> str:
        label = self._deck_label(name, commander)
        if armed:
            suffix = self._translator.t("optimize.target.armed_suffix")
            return f"{label} {suffix}"
        return label
    def _set_combo_committed(self, committed: bool) -> None:
        self._selection_committed = committed
        line_edit = self._deck_combo.lineEdit()
        if line_edit is None:
            return
        line_edit.setReadOnly(committed)
        if committed:
            line_edit.home(False)

    def _on_combo_text_changed(self, text: str) -> None:
        if not text.strip():
            self._set_combo_committed(False)
            self._deck_combo.setCurrentIndex(-1)

    def _commit_combo_selection(self, *_args) -> None:
        deck_id = self._selected_deck_id()
        if deck_id is None:
            self._set_combo_committed(False)
            return
        index = self._deck_combo.findData(deck_id)
        if index < 0:
            self._set_combo_committed(False)
            return
        self._deck_combo.blockSignals(True)
        self._deck_combo.setCurrentIndex(index)
        self._deck_combo.blockSignals(False)
        self._set_combo_committed(True)

    def refresh_decks(self) -> None:
        """Reload the target picker. Defers while this tab is hidden."""
        if not self.isVisible():
            self._needs_reload = True
            return
        self._reload_decks()

    def _reload_decks(self) -> None:
        self._needs_reload = False
        current = self._deck_combo.currentData()
        self._deck_combo.blockSignals(True)
        self._deck_combo.clear()
        with get_session() as session:
            service = DeckService(session)
            commander_names = service.commander_names_by_deck()
            decks = list(service.list_decks())
            self._deck_count = len(decks)
            for deck in decks:
                commander = commander_names.get(deck.id)
                label = self._picker_label(
                    deck.name, commander, deck.status == DeckStatus.ARMED
                )
                self._deck_combo.addItem(label, deck.id)
        completer = self._deck_combo.completer()
        if completer is not None:
            completer.setModel(self._deck_combo.model())
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        if current is not None:
            index = self._deck_combo.findData(current)
            if index >= 0:
                self._deck_combo.setCurrentIndex(index)
                self._set_combo_committed(True)
            else:
                self._deck_combo.setCurrentIndex(-1)
                line_edit = self._deck_combo.lineEdit()
                if line_edit is not None:
                    line_edit.clear()
                self._set_combo_committed(False)
        else:
            self._deck_combo.setCurrentIndex(-1)
            self._set_combo_committed(False)
        self._deck_combo.blockSignals(False)
        self._rebuild_viable_mode_list()
        self._rebuild_viable_filter_combo()
        if self._section_list.currentRow() == VIABLE_SECTION_INDEX:
            self._load_viable_view()
        if self._queue:
            self._recompute_queue_plans(select_deck_id=self._selected_queue_deck_id())

    def _selected_deck_id(self) -> int | None:
        typed = self._deck_combo.currentText().strip()
        if not typed:
            return None
        index = self._deck_combo.currentIndex()
        if index >= 0 and self._deck_combo.itemText(index) == typed:
            data = self._deck_combo.itemData(index)
            if isinstance(data, int):
                return data
        needle = typed.casefold()
        exact: list[int] = []
        partial: list[int] = []
        for i in range(self._deck_combo.count()):
            label = self._deck_combo.itemText(i)
            data = self._deck_combo.itemData(i)
            if not isinstance(data, int):
                continue
            folded = label.casefold()
            if folded == needle:
                exact.append(data)
            elif needle in folded:
                partial.append(data)
        if len(exact) == 1:
            return exact[0]
        if len(partial) == 1:
            return partial[0]
        return None

    def _selected_queue_deck_id(self) -> int | None:
        item = self._queue_list.currentItem()
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, int) else None

    def _clear_plan_panels(self) -> None:
        self._inventory_list.clear()
        self._solution_tree.clear()
        self._solution_combo.blockSignals(True)
        self._solution_combo.clear()
        self._solution_combo.blockSignals(False)
        self._clear_step_combos()
        self._missing_tree.clear()
        self._summary.setText("")
        self._current_plan = None
        self._set_section_titles(0, 0, 0)
        self._missing_group.setVisible(False)
        self._set_plan_actions_visible(False)
        self._inventory_group.setVisible(True)
        self._solution_group.setVisible(True)
        self._solution_combo.setVisible(True)
        self._step_combos_host.setVisible(False)

    def _clear_step_combos(self) -> None:
        while self._step_combos_layout.count():
            item = self._step_combos_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._step_solution_combos.clear()

    def _clear_queue(self) -> None:
        self._queue.clear()
        self._plans.clear()
        self._chosen_solutions.clear()
        self._queue_list.clear()
        self._queue_group.setVisible(False)
        self._clear_plan_panels()

    def _add_selected_to_queue(self) -> None:
        self._commit_combo_selection()
        deck_id = self._selected_deck_id()
        if deck_id is None or deck_id in self._queue:
            return
        self._queue.append(deck_id)
        self._recompute_queue_plans(select_deck_id=deck_id)
        line_edit = self._deck_combo.lineEdit()
        if line_edit is not None:
            line_edit.clear()
        self._deck_combo.setCurrentIndex(-1)
        self._set_combo_committed(False)

    def _remove_selected_from_queue(self) -> None:
        deck_id = self._selected_queue_deck_id()
        if deck_id is None:
            return
        self._queue = [item for item in self._queue if item != deck_id]
        self._chosen_solutions.pop(deck_id, None)
        if not self._queue:
            self._clear_queue()
            return
        self._recompute_queue_plans()

    def _recompute_queue_plans(self, select_deck_id: int | None = None) -> None:
        if not self._queue:
            self._clear_queue()
            return
        self._recomputing_queue = True
        try:
            try:
                with get_session() as session:
                    self._plans = OptimizationService(session).plan_assembly_sequence(
                        self._queue, self._chosen_solutions
                    )
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    self._translator.t("common.error"),
                    str(exc),
                )
                return
            self._queue_group.setVisible(True)
            keep = select_deck_id if select_deck_id in self._queue else None
            if keep is None:
                keep = self._selected_queue_deck_id()
            self._refresh_queue_list(select_deck_id=keep)
        finally:
            self._recomputing_queue = False

    def _queue_status_label(self, plan: AssemblyPlan) -> str:
        if plan.already_armed:
            return self._translator.t("optimize.queue.kept")
        if plan.still_missing or not plan.result.solutions:
            return self._translator.t("optimize.queue.missing")
        return self._translator.t("optimize.queue.viable")

    def _refresh_queue_list(self, select_deck_id: int | None = None) -> None:
        self._queue_list.blockSignals(True)
        self._queue_list.clear()
        plans_by_id = {plan.target_deck_id: plan for plan in self._plans}
        for index, deck_id in enumerate(self._queue, start=1):
            plan = plans_by_id.get(deck_id)
            name = plan.target_deck_name if plan else str(deck_id)
            status = self._queue_status_label(plan) if plan else "?"
            mark = (
                "✓"
                if plan
                and not plan.already_armed
                and not plan.still_missing
                and plan.result.solutions
                else "✗"
            )
            if plan and plan.already_armed:
                mark = "—"
            item = QListWidgetItem(f"{index}. {name}  {mark} {status}")
            item.setData(Qt.ItemDataRole.UserRole, deck_id)
            self._queue_list.addItem(item)
            if deck_id == select_deck_id:
                self._queue_list.setCurrentItem(item)
        if self._queue_list.currentItem() is None and self._queue_list.count() > 0:
            self._queue_list.setCurrentRow(0)
        self._queue_list.blockSignals(False)
        self._refresh_plan_display()

    def _on_queue_selection_changed(self, row: int) -> None:
        if len(self._plans) <= 1 and 0 <= row < len(self._plans):
            self._current_plan = self._plans[row]
        # Aggregate (2+) view ignores selection for the main panels.
        if not self._recomputing_queue:
            self._refresh_plan_display()

    def _on_solution_changed(self, _index: int = 0) -> None:
        if self._recomputing_queue:
            return
        if len(self._plans) > 1:
            return
        plan = self._current_plan
        if plan is None:
            return
        solution = self._solution_combo.currentData()
        if isinstance(solution, frozenset):
            previous = self._chosen_solutions.get(plan.target_deck_id)
            self._chosen_solutions[plan.target_deck_id] = solution
            if previous != solution and any(
                deck_id != plan.target_deck_id for deck_id in self._queue
            ):
                self._recompute_queue_plans(select_deck_id=plan.target_deck_id)
                return
        self._show_selected_solution()

    def _on_step_solution_changed(self, deck_id: int) -> None:
        if self._recomputing_queue:
            return
        combo = self._step_solution_combos.get(deck_id)
        if combo is None:
            return
        solution = combo.currentData()
        if not isinstance(solution, frozenset):
            return
        previous = self._chosen_solutions.get(deck_id)
        self._chosen_solutions[deck_id] = solution
        if previous != solution:
            self._recompute_queue_plans(select_deck_id=deck_id)

    def _refresh_plan_display(self) -> None:
        if not self._plans:
            self._clear_plan_panels()
            return
        if len(self._plans) == 1:
            self._current_plan = self._plans[0]
            self._refresh_single_plan_display(self._plans[0])
            return
        self._current_plan = None
        self._refresh_aggregate_plan_display()

    def _refresh_single_plan_display(self, plan: AssemblyPlan) -> None:
        self._inventory_list.clear()
        self._solution_tree.clear()
        self._solution_combo.blockSignals(True)
        self._solution_combo.clear()
        self._solution_combo.blockSignals(False)
        self._clear_step_combos()
        self._step_combos_host.setVisible(False)
        self._solution_combo.setVisible(True)
        self._missing_tree.clear()
        self._apply_section_titles_from_plan()

        if plan.already_armed:
            self._summary.setText(self._translator.t("optimize.already_armed"))
            self._inventory_group.setVisible(False)
            self._solution_group.setVisible(False)
            self._missing_group.setVisible(False)
            self._set_plan_actions_visible(False)
            return

        self._inventory_group.setVisible(True)
        if plan.free_inventory_used:
            for card_id, qty in sorted(
                plan.free_inventory_used.items(),
                key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
            ):
                self._inventory_list.addItem(self._card_qty_label(plan, card_id, qty))
        else:
            self._inventory_list.addItem("—")

        if plan.still_missing:
            self._summary.setText(self._translator.t("optimize.no_solutions"))
            self._solution_group.setVisible(False)
            self._set_plan_actions_visible(False)
            self._missing_group.setVisible(True)
            self._populate_missing_tree(plan)
            self._cancel_button.setVisible(True)
            return

        self._missing_group.setVisible(False)
        result = plan.result
        if not result.solutions:
            self._summary.setText(self._translator.t("optimize.no_solutions"))
            self._solution_group.setVisible(False)
            self._set_plan_actions_visible(False)
            self._cancel_button.setVisible(True)
            return

        self._solution_group.setVisible(True)
        count = result.minimum_decks_to_dismantle
        if count == 0:
            summary = self._translator.t("optimize.summary.inventory_only")
        else:
            summary = self._translator.t("optimize.summary.dismantle").format(
                count=count
            )
        if len(result.solutions) > 1:
            summary = f"{summary}\n{self._translator.t('optimize.multiple')}"
        self._summary.setText(summary)

        preferred = self._chosen_solutions.get(plan.target_deck_id)
        select_index = 0
        self._solution_combo.blockSignals(True)
        for index, solution in enumerate(result.solutions):
            label = plan.solution_labels.get(solution, ", ".join(sorted(solution)))
            if index == 0 and len(result.solutions) > 1:
                label = f"{label} — {self._translator.t('optimize.solution.suggested')}"
            self._solution_combo.addItem(label, solution)
            if preferred == solution:
                select_index = index
        self._solution_combo.setCurrentIndex(select_index)
        self._solution_combo.setVisible(len(result.solutions) > 1)
        self._solution_combo.blockSignals(False)
        self._show_selected_solution()

    def _refresh_aggregate_plan_display(self) -> None:
        self._inventory_list.clear()
        self._solution_tree.clear()
        self._missing_tree.clear()
        self._solution_combo.blockSignals(True)
        self._solution_combo.clear()
        self._solution_combo.blockSignals(False)
        self._solution_combo.setVisible(False)
        self._clear_step_combos()
        self._apply_section_titles_from_plan()

        viable = sequence_is_viable(self._plans)
        if viable:
            donors = unique_donors_for_sequence(self._plans, self._chosen_solutions)
            count = len(donors)
            if count == 0:
                summary = self._translator.t("optimize.summary.inventory_only_set")
            else:
                summary = self._translator.t("optimize.summary.dismantle_set").format(
                    count=count
                )
            self._summary.setText(summary)
        else:
            self._summary.setText(self._translator.t("optimize.no_solutions_set"))

        self._inventory_group.setVisible(True)
        for plan in self._plans:
            self._inventory_list.addItem(self._section_header(plan.target_deck_name))
            if plan.already_armed:
                self._inventory_list.addItem(
                    self._translator.t("optimize.queue.kept")
                )
                continue
            if plan.free_inventory_used:
                for card_id, qty in sorted(
                    plan.free_inventory_used.items(),
                    key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
                ):
                    self._inventory_list.addItem(
                        self._card_qty_label(plan, card_id, qty)
                    )
            else:
                self._inventory_list.addItem("—")

        show_solutions = viable
        if show_solutions:
            self._solution_group.setVisible(True)
            self._missing_group.setVisible(False)
            self._populate_aggregate_solutions()
            self._set_plan_actions_visible(True)
        else:
            self._solution_group.setVisible(False)
            self._set_plan_actions_visible(False)
            self._cancel_button.setVisible(True)
            self._missing_group.setVisible(True)
            self._populate_aggregate_missing()

    def _populate_aggregate_solutions(self) -> None:
        self._step_combos_host.setVisible(False)
        multi_steps = [
            plan
            for plan in self._plans
            if not plan.already_armed
            and plan.result.solutions
            and len(plan.result.solutions) > 1
        ]
        if multi_steps:
            self._step_combos_host.setVisible(True)
            for plan in multi_steps:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                label = QLabel(plan.target_deck_name)
                combo = QComboBox()
                configure_data_combo(
                    combo, min_contents=SEARCHABLE_COMBO_CONTENTS_LENGTH
                )
                preferred = self._chosen_solutions.get(plan.target_deck_id)
                select_index = 0
                for index, solution in enumerate(plan.result.solutions):
                    text = plan.solution_labels.get(
                        solution, ", ".join(sorted(solution))
                    )
                    if index == 0:
                        text = (
                            f"{text} — "
                            f"{self._translator.t('optimize.solution.suggested')}"
                        )
                    combo.addItem(text, solution)
                    if preferred == solution:
                        select_index = index
                combo.setCurrentIndex(select_index)
                deck_id = plan.target_deck_id
                combo.currentIndexChanged.connect(
                    lambda _i, d=deck_id: self._on_step_solution_changed(d)
                )
                row_layout.addWidget(label)
                row_layout.addWidget(combo, 1)
                self._step_combos_layout.addWidget(row)
                self._step_solution_combos[deck_id] = combo

        for plan in self._plans:
            header = QTreeWidgetItem([self._section_header(plan.target_deck_name)])
            self._solution_tree.addTopLevelItem(header)
            if plan.already_armed:
                header.addChild(
                    QTreeWidgetItem([self._translator.t("optimize.queue.kept")])
                )
                header.setExpanded(True)
                continue
            solution = self._chosen_solutions.get(
                plan.target_deck_id, plan.result.solutions[0]
            )
            taken = plan.cards_taken_from_solution(solution)
            if not solution:
                header.addChild(QTreeWidgetItem(["—"]))
                header.setExpanded(True)
                continue
            for deck_id in sorted(
                solution,
                key=lambda item: plan.deck_names.get(item, item).lower(),
            ):
                deck_name = plan.deck_names.get(deck_id, deck_id)
                parent = QTreeWidgetItem([deck_name])
                header.addChild(parent)
                cards = taken.get(deck_id, {})
                for card_id, qty in sorted(
                    cards.items(),
                    key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
                ):
                    parent.addChild(
                        QTreeWidgetItem([self._card_qty_label(plan, card_id, qty)])
                    )
                parent.setExpanded(True)
            header.setExpanded(True)

    def _populate_aggregate_missing(self) -> None:
        for plan in self._plans:
            if plan.already_armed:
                continue
            if not plan.still_missing and plan.result.solutions:
                continue
            header = QTreeWidgetItem([self._section_header(plan.target_deck_name)])
            self._missing_tree.addTopLevelItem(header)
            if plan.still_missing:
                by_deck, need_to_find = plan.missing_by_source()
                for deck_id in sorted(
                    by_deck.keys(),
                    key=lambda item: plan.deck_names.get(item, item).lower(),
                ):
                    deck_name = plan.deck_names.get(deck_id, deck_id)
                    parent = QTreeWidgetItem([deck_name])
                    header.addChild(parent)
                    cards = by_deck[deck_id]
                    for card_id, qty in sorted(
                        cards.items(),
                        key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
                    ):
                        parent.addChild(
                            QTreeWidgetItem(
                                [self._card_qty_label(plan, card_id, qty)]
                            )
                        )
                    parent.setExpanded(True)
                if need_to_find:
                    find_parent = QTreeWidgetItem(
                        [self._translator.t("optimize.missing.need_to_find")]
                    )
                    header.addChild(find_parent)
                    for card_id, qty in sorted(
                        need_to_find.items(),
                        key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
                    ):
                        find_parent.addChild(
                            QTreeWidgetItem(
                                [self._card_qty_label(plan, card_id, qty)]
                            )
                        )
                    find_parent.setExpanded(True)
                if not by_deck and not need_to_find:
                    for card_id, qty in sorted(
                        plan.still_missing.items(),
                        key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
                    ):
                        header.addChild(
                            QTreeWidgetItem(
                                [self._card_qty_label(plan, card_id, qty)]
                            )
                        )
            else:
                header.addChild(
                    QTreeWidgetItem([self._translator.t("optimize.no_solutions")])
                )
            header.setExpanded(True)

    def _populate_missing_tree(self, plan: AssemblyPlan) -> None:
        """Group unmet cards by armed deck; leftover under Need to find."""
        self._missing_tree.clear()
        by_deck, need_to_find = plan.missing_by_source()

        for deck_id in sorted(
            by_deck.keys(),
            key=lambda item: plan.deck_names.get(item, item).lower(),
        ):
            deck_name = plan.deck_names.get(deck_id, deck_id)
            parent = QTreeWidgetItem([deck_name])
            self._missing_tree.addTopLevelItem(parent)
            cards = by_deck[deck_id]
            for card_id, qty in sorted(
                cards.items(),
                key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
            ):
                parent.addChild(
                    QTreeWidgetItem([self._card_qty_label(plan, card_id, qty)])
                )
            parent.setExpanded(True)

        if need_to_find:
            find_parent = QTreeWidgetItem(
                [self._translator.t("optimize.missing.need_to_find")]
            )
            self._missing_tree.addTopLevelItem(find_parent)
            for card_id, qty in sorted(
                need_to_find.items(),
                key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
            ):
                find_parent.addChild(
                    QTreeWidgetItem([self._card_qty_label(plan, card_id, qty)])
                )
            find_parent.setExpanded(True)

        if not by_deck and not need_to_find:
            for card_id, qty in sorted(
                plan.still_missing.items(),
                key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
            ):
                self._missing_tree.addTopLevelItem(
                    QTreeWidgetItem([self._card_qty_label(plan, card_id, qty)])
                )

    def _show_selected_solution(self) -> None:
        plan = self._current_plan
        self._solution_tree.clear()
        if plan is None:
            self._set_plan_actions_visible(False)
            return

        solution = self._solution_combo.currentData()
        if solution is None:
            self._set_plan_actions_visible(False)
            return

        taken = plan.cards_taken_from_solution(solution)
        for deck_id in sorted(
            solution,
            key=lambda item: plan.deck_names.get(item, item).lower(),
        ):
            deck_name = plan.deck_names.get(deck_id, deck_id)
            parent = QTreeWidgetItem([deck_name])
            self._solution_tree.addTopLevelItem(parent)
            cards = taken.get(deck_id, {})
            for card_id, qty in sorted(
                cards.items(),
                key=lambda item: plan.card_names.get(item[0], item[0]).lower(),
            ):
                parent.addChild(
                    QTreeWidgetItem([self._card_qty_label(plan, card_id, qty)])
                )
            parent.setExpanded(True)

        if not solution:
            self._solution_tree.addTopLevelItem(QTreeWidgetItem(["—"]))

        self._set_plan_actions_visible(True)

    def _confirm_plan(self) -> None:
        if len(self._plans) > 1:
            self._confirm_aggregate_plan()
            return
        plan = self._current_plan
        if plan is None or plan.already_armed or plan.still_missing:
            return
        solution = self._solution_combo.currentData()
        if solution is None:
            return

        deck_names = [
            plan.deck_names.get(deck_id, deck_id)
            for deck_id in sorted(
                solution,
                key=lambda item: plan.deck_names.get(item, item).lower(),
            )
        ]
        if not deck_names:
            decks_text = "—"
        else:
            decks_text = "\n".join(f"• {name}" for name in deck_names)
        body = self._translator.t("optimize.apply.confirm_body").format(
            decks=decks_text,
            target=plan.target_deck_name,
        )
        reply = QMessageBox.question(
            self,
            self._translator.t("optimize.apply.confirm_title"),
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        target_id = plan.target_deck_id
        target_name = plan.target_deck_name
        try:
            with get_session() as session:
                moved = OptimizationService(session).apply_assembly_plan(
                    target_id, solution
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        self._queue = [deck_id for deck_id in self._queue if deck_id != target_id]
        self._chosen_solutions.pop(target_id, None)
        self._summary.setText(self._translator.t("optimize.apply.success"))
        if self._track_editions and moved:
            self._prompt_for_editions(target_name, moved)
        self.refresh_decks()
        if self._queue:
            self._recompute_queue_plans()
        else:
            self._clear_queue()
            self._summary.setText(self._translator.t("optimize.apply.success"))
        self.changed.emit()

    def _confirm_aggregate_plan(self) -> None:
        if not sequence_is_viable(self._plans):
            return
        donor_ids = unique_donors_for_sequence(self._plans, self._chosen_solutions)
        name_lookup: dict[str, str] = {}
        for plan in self._plans:
            name_lookup.update(plan.deck_names)
        donor_names = [
            name_lookup.get(deck_id, deck_id)
            for deck_id in sorted(
                donor_ids, key=lambda item: name_lookup.get(item, item).lower()
            )
        ]
        targets = [
            plan.target_deck_name
            for plan in self._plans
            if not plan.already_armed
        ]
        decks_text = (
            "\n".join(f"• {name}" for name in donor_names) if donor_names else "—"
        )
        targets_text = (
            "\n".join(f"• {name}" for name in targets) if targets else "—"
        )
        body = self._translator.t("optimize.apply.confirm_body_set").format(
            decks=decks_text,
            targets=targets_text,
        )
        reply = QMessageBox.question(
            self,
            self._translator.t("optimize.apply.confirm_title"),
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        steps = [
            (
                plan.target_deck_id,
                plan.target_deck_name,
                self._chosen_solutions.get(
                    plan.target_deck_id, plan.result.solutions[0]
                ),
            )
            for plan in self._plans
            if not plan.already_armed
        ]
        try:
            with get_session() as session:
                service = OptimizationService(session)
                all_moved: list[tuple[str, list[MovedCopy]]] = []
                for target_id, target_name, solution in steps:
                    moved = service.apply_assembly_plan(target_id, solution)
                    if moved:
                        all_moved.append((target_name, moved))
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            self.refresh_decks()
            self.changed.emit()
            return

        self._clear_queue()
        self.refresh_decks()
        self._summary.setText(self._translator.t("optimize.apply.success_set"))
        if self._track_editions:
            for target_name, moved in all_moved:
                self._prompt_for_editions(target_name, moved)
        self.changed.emit()

    def _prompt_for_editions(self, deck_name: str, moved: list[MovedCopy]) -> None:
        """Offer to record set codes; skipping leaves the copies unspecified."""
        dialog = SpecifyEditionsDialog(self._translator, deck_name, moved, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        traits = dialog.traits()
        if not traits:
            return
        try:
            with get_session() as session:
                InventoryService(session).set_copy_traits(traits)
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )

    def _cancel_plan(self) -> None:
        self._clear_queue()
