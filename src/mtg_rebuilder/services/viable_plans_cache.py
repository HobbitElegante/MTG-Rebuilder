"""Persist and validate cached Planes viables results.

Cache is keyed by combination size (or ``max``) and the ɸ checkbox. A
collection fingerprint detects when results are still safe to show, when a
recalculate is optional (more copies / deck edits), or mandatory (fewer
physical copies).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mtg_rebuilder.config import SETTING_VIABLE_PLANS_CACHE
from mtg_rebuilder.services.optimization_service import ViablePlan, ViablePlansResult
from mtg_rebuilder.services.settings_service import SettingsService


class CacheFreshness(str, Enum):
    MISSING = "missing"
    FRESH = "fresh"
    OPTIONAL = "optional"
    MANDATORY = "mandatory"


@dataclass(frozen=True)
class CollectionFingerprint:
    copy_count: int
    deck_sig: str

    def to_dict(self) -> dict[str, Any]:
        return {"copy_count": self.copy_count, "deck_sig": self.deck_sig}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CollectionFingerprint | None:
        if not isinstance(data, dict):
            return None
        try:
            return cls(
                copy_count=int(data["copy_count"]),
                deck_sig=str(data["deck_sig"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


def build_deck_signature(
    decks: list[tuple[int, str, int, bool]],
) -> str:
    """Hash of ``(deck_id, name, requirement_qty_sum, is_locked)`` rows."""
    parts = [
        f"{deck_id}:{name}:{qty}:{int(is_locked)}"
        for deck_id, name, qty, is_locked in sorted(
            decks, key=lambda row: (row[0], row[1].casefold())
        )
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:20]


def compare_fingerprints(
    cached: CollectionFingerprint | None,
    current: CollectionFingerprint,
) -> CacheFreshness:
    if cached is None:
        return CacheFreshness.MISSING
    if current.copy_count < cached.copy_count:
        return CacheFreshness.MANDATORY
    if (
        current.copy_count != cached.copy_count
        or current.deck_sig != cached.deck_sig
    ):
        return CacheFreshness.OPTIONAL
    return CacheFreshness.FRESH


def cache_entry_key(n: int | None, respect_locked: bool) -> str:
    size_key = "max" if n is None else str(n)
    return f"{size_key}:{int(respect_locked)}"


def _plans_to_json(plans: tuple[ViablePlan, ...]) -> list[dict[str, Any]]:
    return [
        {"ids": list(plan.deck_ids), "names": list(plan.deck_names)}
        for plan in plans
    ]


def _plans_from_json(rows: list[Any]) -> tuple[ViablePlan, ...]:
    plans: list[ViablePlan] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ids = row.get("ids")
        names = row.get("names")
        if not isinstance(ids, list) or not isinstance(names, list):
            continue
        if len(ids) != len(names):
            continue
        try:
            deck_ids = tuple(int(deck_id) for deck_id in ids)
        except (TypeError, ValueError):
            continue
        deck_names = tuple(str(name) for name in names)
        plans.append(ViablePlan(deck_ids=deck_ids, deck_names=deck_names))
    return tuple(plans)


class ViablePlansCacheStore:
    """JSON blob in ``AppSetting`` for viable-plan enumeration results."""

    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings

    def load_raw(self) -> dict[str, Any]:
        raw = self._settings.get(SETTING_VIABLE_PLANS_CACHE)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def save_raw(self, data: dict[str, Any]) -> None:
        self._settings.set(SETTING_VIABLE_PLANS_CACHE, json.dumps(data, ensure_ascii=False))

    def fingerprint_for(
        self, n: int | None, respect_locked: bool
    ) -> CollectionFingerprint | None:
        data = self.load_raw()
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return None
        entry = entries.get(cache_entry_key(n, respect_locked))
        if not isinstance(entry, dict):
            return None
        return CollectionFingerprint.from_dict(entry.get("fingerprint"))

    def get_entry(
        self, n: int | None, respect_locked: bool
    ) -> ViablePlansResult | None:
        data = self.load_raw()
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return None
        entry = entries.get(cache_entry_key(n, respect_locked))
        if not isinstance(entry, dict):
            return None
        try:
            size = int(entry["size"])
            truncated = bool(entry.get("truncated", False))
            plans = _plans_from_json(list(entry.get("plans") or []))
        except (KeyError, TypeError, ValueError):
            return None
        return ViablePlansResult(size=size, plans=plans, truncated=truncated)

    def put_entry(
        self,
        n: int | None,
        respect_locked: bool,
        result: ViablePlansResult,
        fingerprint: CollectionFingerprint,
    ) -> None:
        data = self.load_raw()
        entries = data.get("entries")
        if not isinstance(entries, dict):
            entries = {}
        entries[cache_entry_key(n, respect_locked)] = {
            "size": result.size,
            "truncated": result.truncated,
            "plans": _plans_to_json(result.plans),
            "fingerprint": fingerprint.to_dict(),
        }
        data["entries"] = entries
        self.save_raw(data)

    def clear_all(self) -> None:
        self.save_raw({})

    def clear_entries_with_mandatory(
        self, current: CollectionFingerprint
    ) -> list[str]:
        """Remove entries whose fingerprints require mandatory recalc."""
        data = self.load_raw()
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return []
        removed: list[str] = []
        kept: dict[str, Any] = {}
        for key, entry in entries.items():
            if not isinstance(entry, dict):
                removed.append(key)
                continue
            cached_fp = CollectionFingerprint.from_dict(entry.get("fingerprint"))
            if compare_fingerprints(cached_fp, current) == CacheFreshness.MANDATORY:
                removed.append(key)
            else:
                kept[key] = entry
        if removed:
            data["entries"] = kept
            self.save_raw(data)
        return removed

    def freshness_for(
        self,
        n: int | None,
        respect_locked: bool,
        current: CollectionFingerprint,
    ) -> CacheFreshness:
        entry = self.get_entry(n, respect_locked)
        if entry is None:
            return CacheFreshness.MISSING
        cached_fp = self.fingerprint_for(n, respect_locked)
        return compare_fingerprints(cached_fp, current)


def filter_plans_containing(
    plans: tuple[ViablePlan, ...],
    deck_ids: Collection[int],
) -> tuple[ViablePlan, ...]:
    """Combinations that include **every** deck in ``deck_ids`` (empty = all)."""
    if not deck_ids:
        return plans
    required = frozenset(deck_ids)
    return tuple(plan for plan in plans if required.issubset(plan.deck_ids))


def co_occurring_deck_ids(
    plans: tuple[ViablePlan, ...],
    deck_ids: Collection[int] = (),
) -> frozenset[int]:
    """Decks that can still be added to the filter without emptying it.

    These are the decks appearing in a combination that already includes all
    of ``deck_ids``, minus ``deck_ids`` themselves. With no selection this is
    every deck that appears in some combination.
    """
    ids: set[int] = set()
    for plan in filter_plans_containing(plans, deck_ids):
        ids.update(plan.deck_ids)
    return frozenset(ids.difference(deck_ids))
