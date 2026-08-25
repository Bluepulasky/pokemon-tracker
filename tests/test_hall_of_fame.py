"""Hall of Fame ranking (0-8) on collection items."""
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


def test_rating_defaults_to_unranked(repo):
    item = repo.upsert_collection_item({"card_id": "base1-4"})
    assert item["rating"] == 0


def test_rating_is_per_row_not_per_physical_copy(repo):
    """The spec asks for a rank per copy, but UNIQUE(card,variant,condition,
    language) collapses identical copies into one row with a quantity. Copies
    that differ in any of those attributes are separate rows and rank
    separately; truly identical copies share a rank."""
    repo.upsert_collection_item({"card_id": "base1-4", "condition": "NM", "rating": 8})
    repo.upsert_collection_item({"card_id": "base1-4", "condition": "LP", "rating": 3})
    ratings = {i["condition"]: i["rating"] for i in repo.items_by_card("base1-4")}
    assert ratings == {"NM": 8, "LP": 3}

    # same combination again -> still one row, quantity accumulates
    repo.upsert_collection_item({"card_id": "base1-4", "condition": "NM", "quantity": 2})
    rows = [i for i in repo.items_by_card("base1-4") if i["condition"] == "NM"]
    assert len(rows) == 1 and rows[0]["quantity"] == 3


def test_adding_more_copies_keeps_the_existing_rank(repo):
    """Adding a duplicate sends rating=0 by default; that must not wipe a rank."""
    item = repo.upsert_collection_item({"card_id": "base1-4", "rating": 7})
    repo.upsert_collection_item({"card_id": "base1-4", "quantity": 1})
    assert repo.get_collection_item(item["id"])["rating"] == 7


def test_average_excludes_unranked(repo):
    """0 means "not ranked yet", not "ranked zero" — averaging it in would make
    the number describe how much ranking is left rather than the collection."""
    repo.upsert_collection_item({"card_id": "base1-4", "rating": 8})
    repo.upsert_collection_item({"card_id": "base1-2", "rating": 6})
    repo.upsert_collection_item({"card_id": "base1-4", "condition": "LP"})   # unranked
    stats = repo.rating_stats()
    assert stats["average"] == 7.0
    assert stats["rated"] == 2 and stats["unrated"] == 1
    assert stats["best"] == 8


def test_rating_filters(repo):
    for cond, rating in [("NM", 8), ("LP", 7), ("MP", 5), ("HP", 2)]:
        repo.upsert_collection_item({"card_id": "base1-4", "condition": cond,
                                     "rating": rating})
    exact, _ = repo.list_collection(rating=8)
    assert len(exact) == 1
    top, _ = repo.list_collection(rating_min=7)
    assert len(top) == 2, "Top Tier quick filter"
    fav, _ = repo.list_collection(rating_min=5)
    assert len(fav) == 3, "Favourites quick filter"
    band, _ = repo.list_collection(rating_min=2, rating_max=5)
    assert len(band) == 2


def test_database_rejects_out_of_range(repo):
    """Defence in depth: the API validates, but the column carries a CHECK so a
    bad value cannot get in through the CLI or a direct write."""
    with pytest.raises(sqlite3.IntegrityError):
        with repo.tx() as c:
            c.execute("INSERT INTO collection_items(card_id, rating) VALUES ('base1-4', 9)")


def test_migration_adds_rating_to_an_existing_database():
    """schema.sql is CREATE TABLE IF NOT EXISTS, so it does nothing to a database
    that already exists. Without an explicit migration every existing install
    breaks on the first query touching the new column."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        repo = PokemonRepo(path)
        repo.init_db(DEFAULT_MODIFIERS)
        with repo.tx() as c:                     # simulate the pre-feature schema
            c.execute("DROP INDEX IF EXISTS idx_items_rating")   # index pins the column
            c.execute("ALTER TABLE collection_items DROP COLUMN rating")
            cols = {r["name"] for r in c.execute("PRAGMA table_info(collection_items)")}
            assert "rating" not in cols
        repo.close()

        PokemonRepo(path).init_db(DEFAULT_MODIFIERS)   # upgrade
        con = sqlite3.connect(path)
        assert "rating" in {r[1] for r in con.execute("PRAGMA table_info(collection_items)")}
        con.close()
    finally:
        os.unlink(path)
