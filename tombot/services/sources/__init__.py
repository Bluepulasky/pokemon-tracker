"""Card data sources.

Only tcggo remains. The pokemontcg.io and TCGdex adapters are gone: each mapped
a card to a single price for all its printings, so a reprint was priced as its
Base Set original and a non-holo as the holo. tcggo maps one Cardmarket product
per printing, which is what the collection actually needs.
"""
from .base import CardSource
from .tcggo import TcggoSource

__all__ = ["CardSource", "TcggoSource"]
