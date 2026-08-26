from .base import CardSource
from .pokemontcgio import PokemonTcgIoSource
from .tcgdex import TcgdexSource


def get_source(name: str, config) -> CardSource:
    if name == "pokemontcgio":
        return PokemonTcgIoSource(config)
    if name == "tcgdex":
        return TcgdexSource(config)
    raise ValueError(f"unknown source: {name!r}")
