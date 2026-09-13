"""Deck statistics list and mana curve chart for the Decks detail pane.

The commander column of the detail splitter becomes stats (top), the commander
preview (middle) and the curve chart (bottom). When the column is too short to
fit everything, stats and chart hide automatically so the commander preview
keeps the whole column, matching the pre-stats layout on small windows.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from mtg_rebuilder.algorithms.deck_stats import DeckStatistics
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.ui.mana_icons import pips_rich_html
from mtg_rebuilder.ui.widgets.card_preview import PREVIEW_ASPECT, PREVIEW_MIN_WIDTH

# Both read well on the light and the dark Fusion palettes.
CREATURE_COLOR = QColor(0x4C, 0xAF, 0x50)
SPELL_COLOR = QColor(0x42, 0x85, 0xF4)

CHART_MIN_HEIGHT = 130
# Image min size plus the title row and layout spacing around the preview.
_PREVIEW_MIN_HEIGHT = int((PREVIEW_MIN_WIDTH - 30) * PREVIEW_ASPECT) + 40

_TYPE_I18N = {
    "Creature": "decks.stats.type.creature",
    "Instant": "decks.stats.type.instant",
    "Sorcery": "decks.stats.type.sorcery",
    "Artifact": "decks.stats.type.artifact",
    "Enchantment": "decks.stats.type.enchantment",
    "Planeswalker": "decks.stats.type.planeswalker",
    "Battle": "decks.stats.type.battle",
}


def format_types_html(stats: DeckStatistics, translator: Translator) -> str:
    """Type breakdown as a full-width two-column grid (odd leftover centered)."""
    if not stats.type_counts:
        return ""
    items = [
        f"{translator.t(_TYPE_I18N[name])}:&nbsp;{qty}"
        for name, qty in stats.type_counts
    ]
    rows = []
    for index in range(0, len(items) - 1, 2):
        rows.append(
            f'<tr><td align="left">{items[index]}</td>'
            f'<td align="right">{items[index + 1]}</td></tr>'
        )
    if len(items) % 2:
        rows.append(
            f'<tr><td align="center" colspan="2">{items[-1]}</td></tr>'
        )
    return (
        translator.t("decks.stats.types_title")
        + '<table width="100%" cellspacing="0">'
        + "".join(rows)
        + "</table>"
    )


def format_average_lines(stats: DeckStatistics, translator: Translator) -> str:
    """The two x̄ mana-value lines (without and with lands)."""
    lines = []
    if stats.average_cmc is not None:
        lines.append(
            translator.t("decks.stats.avg_no_lands").format(
                value=f"{stats.average_cmc:.2f}"
            )
        )
    if stats.average_cmc_with_lands is not None:
        lines.append(
            translator.t("decks.stats.avg_with_lands").format(
                value=f"{stats.average_cmc_with_lands:.2f}"
            )
        )
    return "\n".join(lines)


class ManaCurveChart(QWidget):
    """Stacked bar chart: cards per mana value, creatures vs other spells."""

    def __init__(
        self, translator: Translator, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._stats: DeckStatistics | None = None
        # Preferred (not a hard minimum) so the chart never inflates the
        # column's minimum height — the column hides it instead when short.
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(PREVIEW_MIN_WIDTH, CHART_MIN_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(0, 0)

    def set_stats(self, stats: DeckStatistics | None) -> None:
        self._stats = stats
        self.update()

    def retranslate(self) -> None:
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        text_color = palette.color(palette.ColorRole.Text)

        area = self.rect().adjusted(4, 2, -4, -2)
        if self._stats is None:
            painter.end()
            return
        if not self._stats.has_curve_data:
            painter.setPen(text_color)
            painter.drawText(
                area,
                int(Qt.AlignmentFlag.AlignCenter),
                self._translator.t("decks.stats.curve.empty"),
            )
            painter.end()
            return

        metrics = painter.fontMetrics()
        legend_height = metrics.height() + 4
        label_height = metrics.height() + 2
        value_height = metrics.height()

        self._paint_legend(painter, area, legend_height, text_color)

        bars_area = QRect(
            area.left(),
            area.top() + legend_height + value_height,
            area.width(),
            area.height() - legend_height - value_height - label_height,
        )
        if bars_area.height() <= 0:
            painter.end()
            return

        columns = self._stats.curve
        max_total = max(column.total for column in columns)
        slot_width = bars_area.width() / len(columns)
        bar_width = max(6, int(slot_width * 0.62))

        for index, column in enumerate(columns):
            slot_left = bars_area.left() + int(index * slot_width)
            bar_left = slot_left + int((slot_width - bar_width) / 2)
            label = f"{column.cmc}+" if index == len(columns) - 1 else str(column.cmc)
            label_rect = QRect(
                slot_left, bars_area.bottom() + 2, int(slot_width), label_height
            )
            painter.setPen(text_color)
            painter.drawText(
                label_rect, int(Qt.AlignmentFlag.AlignHCenter), label
            )
            if column.total == 0:
                continue

            total_height = max(
                2, int(bars_area.height() * column.total / max_total)
            )
            creature_height = (
                int(total_height * column.creatures / column.total)
                if column.creatures
                else 0
            )
            top = bars_area.bottom() - total_height
            painter.setPen(Qt.PenStyle.NoPen)
            if total_height - creature_height > 0:
                painter.setBrush(SPELL_COLOR)
                painter.drawRect(
                    bar_left, top, bar_width, total_height - creature_height
                )
            if creature_height > 0:
                painter.setBrush(CREATURE_COLOR)
                painter.drawRect(
                    bar_left,
                    bars_area.bottom() - creature_height,
                    bar_width,
                    creature_height,
                )
            painter.setPen(text_color)
            value_rect = QRect(
                slot_left, top - value_height - 1, int(slot_width), value_height
            )
            painter.drawText(
                value_rect,
                int(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
                ),
                str(column.total),
            )
        painter.end()

    def _paint_legend(
        self,
        painter: QPainter,
        area: QRect,
        legend_height: int,
        text_color: QColor,
    ) -> None:
        metrics = painter.fontMetrics()
        swatch = max(8, metrics.ascent() - 2)
        creatures = self._translator.t("decks.stats.curve.creatures")
        spells = self._translator.t("decks.stats.curve.spells")
        gap = 12
        x = area.left()
        y = area.top() + (legend_height - swatch) // 2
        for color, label in ((CREATURE_COLOR, creatures), (SPELL_COLOR, spells)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRect(x, y, swatch, swatch)
            painter.setPen(text_color)
            text_rect = QRect(
                x + swatch + 4,
                area.top(),
                metrics.horizontalAdvance(label) + 2,
                legend_height,
            )
            painter.drawText(
                text_rect, int(Qt.AlignmentFlag.AlignVCenter), label
            )
            x = text_rect.right() + gap


class DeckStatsColumn(QWidget):
    """Stats list + commander preview + mana curve, hiding extras when short."""

    def __init__(
        self,
        translator: Translator,
        preview: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._stats: DeckStatistics | None = None
        self._extras_visible = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stats_box = QWidget()
        stats_layout = QVBoxLayout(self._stats_box)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(2)
        self._counts_label = QLabel("")
        self._counts_label.setWordWrap(True)
        self._avg_label = QLabel("")
        self._avg_label.setWordWrap(True)
        self._avg_label.setToolTip(self._translator.t("decks.stats.avg_tooltip"))
        self._types_label = QLabel("")
        self._types_label.setWordWrap(True)
        self._types_label.setTextFormat(Qt.TextFormat.RichText)
        self._pips_label = QLabel("")
        self._pips_label.setWordWrap(True)
        self._pips_label.setTextFormat(Qt.TextFormat.RichText)
        stats_layout.addWidget(self._counts_label)
        stats_layout.addWidget(self._avg_label)
        stats_layout.addWidget(self._types_label)
        stats_layout.addWidget(self._pips_label)
        layout.addWidget(self._stats_box)

        layout.addWidget(preview, 1)

        self._curve_title = QLabel(self._translator.t("decks.stats.curve.title"))
        layout.addWidget(self._curve_title)
        self._chart = ManaCurveChart(translator)
        layout.addWidget(self._chart)

        self.setMinimumWidth(PREVIEW_MIN_WIDTH)

    def set_stats(self, stats: DeckStatistics | None) -> None:
        self._stats = stats
        self._render_stats()
        self._chart.set_stats(stats)
        self._update_extras_visibility()

    def retranslate(self) -> None:
        self._curve_title.setText(self._translator.t("decks.stats.curve.title"))
        self._avg_label.setToolTip(self._translator.t("decks.stats.avg_tooltip"))
        self._render_stats()
        self._chart.retranslate()

    def _render_stats(self) -> None:
        if self._stats is None:
            for label in (
                self._counts_label,
                self._avg_label,
                self._types_label,
                self._pips_label,
            ):
                label.setText("")
            return
        stats = self._stats
        self._counts_label.setText(
            self._translator.t("decks.stats.lands").format(
                count=stats.lands, basic=stats.basic_lands
            )
        )
        self._avg_label.setText(format_average_lines(stats, self._translator))
        self._types_label.setText(format_types_html(stats, self._translator))
        pips_lines = []
        if stats.color_pips:
            pips = pips_rich_html(stats.color_pips)
            pips_lines.append(
                self._translator.t("decks.stats.pips").format(value=pips)
            )
        if stats.unknown_cards:
            pips_lines.append(
                self._translator.t("decks.stats.unknown").format(
                    count=stats.unknown_cards
                )
            )
        self._pips_label.setText("<br>".join(pips_lines))

    def _update_extras_visibility(self) -> None:
        needed = (
            _PREVIEW_MIN_HEIGHT
            + self._stats_box.sizeHint().height()
            + self._curve_title.sizeHint().height()
            + CHART_MIN_HEIGHT
        )
        show = self._stats is not None and self.height() >= needed
        if show == self._extras_visible:
            return
        self._extras_visible = show
        self._stats_box.setVisible(show)
        self._curve_title.setVisible(show)
        self._chart.setVisible(show)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._update_extras_visibility()
