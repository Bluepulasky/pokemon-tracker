from .base import CardSource
from .pokemontcgio import PokemonTcgIoSource
from .tcgdex import TcgdexSource
from .tcggo import TcggoSource


def get_source(name: str, config, budget=None) -> CardSource:
    if name == "pokemontcgio":
        return PokemonTcgIoSource(config)
    if name == "tcgdex":
        return TcgdexSource(config)
    if name == "tcggo":
        # Metered. Constructed without a budget it would be able to spend
        # money uncounted, so the caller must supply one; create_app does.
        if budget is None:
            raise ValueError("tcggo requires a RequestBudget: every call is billed")
        return TcggoSource(config, budget=budget)
    raise ValueError(f"unknown source: {name!r}")
