"""Hall of Fame ranking (0-8).

The rank belongs to the CARD, not to a collection row. It shipped on
collection_items, which meant a card owned as holo and non-holo had to be ranked
twice — two answers to a question that has one.
"""
import os
import sqlite3
import tempfile

import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = PokemonRepo(path)
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                           "printed_total": 102, "total": 102,
                           "release_date": "1999/01/09", "ptcgo_code": "BS",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard",
         "number": "4", "rarity": "Rare Holo"},
        {"id": "base1-2", "official_set_id": "base1", "name": "Blastoise",
         "number": "2", "rarity": "Rare Holo"},
    ])
    yield r
    os.unlink(path)


def test_rank_is_shared_by_every_variant_of_the_card(repo):
    """The reported bug: ranking the holo did not rank the non-holo."""
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo"})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "normal"})
    repo.set_card_rating("base1-4", 8)

    ratings = {i["variant"]: i["rating"] for i in repo.items_by_card("base1-4")}
    assert ratings == {"holo": 8, "normal": 8}


def test_rank_survives_owning_nothing(repo):
    """A rank is an opinion about the card, so it does not require a copy in
    hand — you can rank a card you are still hunting for."""
    repo.set_card_rating("base1-4", 7)
    assert repo.get_card_rating("base1-4") == 7


def test_zero_clears_the_rank(repo):
    repo.set_card_rating("base1-4", 5)
    repo.set_card_rating("base1-4", 0)
    assert repo.get_card_rating("base1-4") == 0
    assert repo._scalar("SELECT COUNT(*) FROM card_ratings") == 0, \
        "0 means unranked, so it is stored as absence"


def test_average_counts_cards_not_rows(repo):
    """Two variants of one card are one opinion. Counting the row twice would
    skew the average toward whatever the user happens to own duplicates of."""
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo"})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "normal"})
    repo.upsert_collection_item({"card_id": "base1-2"})
    repo.set_card_rating("base1-4", 8)
    repo.set_card_rating("base1-2", 6)

    stats = repo.rating_stats()
    assert stats["rated"] == 2, "two cards, not three rows"
    assert stats["average"] == 7.0
    assert stats["best"] == 8


def test_unranked_count_is_over_owned_cards(repo):
    repo.upsert_collection_item({"card_id": "base1-4"})
    repo.upsert_collection_item({"card_id": "base1-2"})
    repo.set_card_rating("base1-4", 8)
    assert repo.rating_stats() == {**repo.rating_stats(), "rated": 1, "unrated": 1}


def test_rating_filters_match_every_variant(repo):
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo"})
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "normal"})
    repo.upsert_collection_item({"card_id": "base1-2"})
    repo.set_card_rating("base1-4", 8)
    repo.set_card_rating("base1-2", 3)

    top, _ = repo.list_collection(rating_min=7)
    assert len(top) == 2, "both variants of the ranked card"
    exact, _ = repo.list_collection(rating=3)
    assert [i["card_id"] for i in exact] == ["base1-2"]
    unranked, _ = repo.list_collection(rating=0)
    assert unranked == []


def test_database_rejects_out_of_range(repo):
    with pytest.raises(sqlite3.IntegrityError):
        with repo.tx() as c:
            c.execute("INSERT INTO card_ratings(card_id, rating) VALUES ('base1-4', 9)")
