from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mtg_rebuilder.models import CardPrinting


class CardPrintingRepository:
    """Per-printing catalog. Not collapsed to one row per set."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_card(self, oracle_id: str) -> list[CardPrinting]:
        return list(
            self._session.scalars(
                select(CardPrinting)
                .where(CardPrinting.oracle_id == oracle_id)
                .order_by(CardPrinting.set_code, CardPrinting.collector_number)
            ).all()
        )

    def has_any(self, oracle_id: str) -> bool:
        return (
            self._session.scalar(
                select(CardPrinting.id)
                .where(CardPrinting.oracle_id == oracle_id)
                .limit(1)
            )
            is not None
        )

    def replace_for_card(
        self,
        oracle_id: str,
        printings: list[tuple[str, str, str | None, str | None, str | None, str]],
    ) -> list[CardPrinting]:
        """Replace this card's rows.

        Each tuple is ``(scryfall_id, set_code, collector_number, illustration_id, label, image_uri)``.
        """
        self._session.execute(
            delete(CardPrinting).where(CardPrinting.oracle_id == oracle_id)
        )
        rows = [
            CardPrinting(
                id=scryfall_id,
                oracle_id=oracle_id,
                set_code=set_code,
                collector_number=collector_number,
                illustration_id=illustration_id,
                label=label,
                image_uri=image_uri,
            )
            for (
                scryfall_id,
                set_code,
                collector_number,
                illustration_id,
                label,
                image_uri,
            ) in printings
        ]
        self._session.add_all(rows)
        self._session.flush()
        return rows
