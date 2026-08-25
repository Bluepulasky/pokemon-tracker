"""Adapter interface for catalog/price sources.

Deliberately narrow so a second source (TCGdex, which carries Spanish card names)
can be dropped in without touching the importer or the pricing service.
"""
from __future__ import annotations

from typing import Iterator, Protocol


class CardSource(Protocol):
    name: str

    def fetch_set(self, set_id: str) -> dict:
        """Official set metadata, normalised to the official_sets column names."""

    def fetch_cards(self, set_id: str) -> Iterator[dict]:
        """Catalog cards for a set, normalised to the cards column names."""

    def fetch_prices(self, card_ids: list[str]) -> dict[str, dict]:
        """card_id -> {source, currency, prices: {...}}. Batched, never one call per card."""
