from .base import CardSource
from .pokemontcgio import PokemonTcgIoSource


def get_source(name: str, config) -> CardSource:
    if name == "pokemontcgio":
        return PokemonTcgIoSource(config)
    raise ValueError(f"unknown source: {name!r}")
