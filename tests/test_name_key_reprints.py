"""Reprints match on a normalised name, not the literal spelling (issue #102).

tcggo spells one card two ways across sets: Base Set says "Pokemon Center"
where Base Set 2 says "Pokémon Center". Same artwork, same illustrator, same
card — but compared literally the two never met, so the version picker, loose
completion and the Hall of Fame rank all treated them as strangers. Every
reprint join now runs over `cards.name_key`, which is `normalized_name` of the
name: accents stripped, gender signs spelled out, case and punctuation gone.
"""
import sqlite3

import pytest

from tombot.services.repository import PokemonRepo
from tombot.services.setbuilder import SetBuilder
from tombot.services.tcggo_catalog import normalized_name


def _prod(pid, card_id, code, number, name):
    return {"cardmarket_id": pid, "episode_id": 1, "card_id": card_id, "code": code,
            "number": number, "name": name, "version": "Unlimited",
            "rarity": "Uncommon", "currency": "EUR", "price": 1.0, "price_low": None,
            "price_avg30": None, "price_avg7": None, "available": 1, "image": None,
            "market_url": f"https://x/{pid}", "artist": "Keiji Kinebuchi"}


def _sets(r):
    for sid, name, rd in [("bs", "Base Set", "1999/01/09"),
                          ("b2", "Base Set 2", "2000/02/24")]:
        r.upsert_official_set({"id": sid, "name": name, "series": "",
                               "printed_total": 1, "total": 1, "release_date": rd,
                               "ptcgo_code": sid.upper(), "logo_url": None,
                               "symbol_url": None})


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "r.db")
    r.init_db()
    _sets(r)
    r.upsert_cards([
        {"id": "bs-85", "official_set_id": "bs", "name": "Pokemon Center",
         "number": "85", "rarity": "Uncommon", "artist": "Keiji Kinebuchi"},
        {"id": "b2-114", "official_set_id": "b2", "name": "Pokémon Center",
         "number": "114", "rarity": "Uncommon", "artist": "Keiji Kinebuchi"},
    ])
    r.upsert_market_products([
        _prod(101, "bs-85", "BS 85", "85", "Pokemon Center"),
        _prod(102, "b2-114", "B2 114", "114", "Pokémon Center"),
    ])
    return r


def test_upsert_stores_the_normalised_key(repo):
    keys = {r["id"]: r["name_key"]
            for r in repo._all("SELECT id, name_key FROM cards")}
    assert keys == {"bs-85": "pokemoncenter", "b2-114": "pokemoncenter"}
    assert normalized_name("Pokémon Center") == "pokemoncenter"


def test_version_picker_lists_the_accented_reprint(repo):
    ids = {p["card_id"] for p in repo.market_products_for_reprint("bs-85")}
    assert ids == {"bs-85", "b2-114"}
    ids = {p["card_id"] for p in repo.market_products_for_name("pokemon center")}
    assert ids == {"bs-85", "b2-114"}


def test_loose_completion_counts_the_accented_reprint(repo):
    repo.upsert_collection_set({"id": "b2goal", "name": "Base Set 2",
                               "rules_json": '{"include_sets": ["b2"]}'})
    SetBuilder(repo).build("b2goal")
    repo.set_loose_completion("b2goal", True)
    repo.upsert_collection_item({"card_id": "bs-85"})
    assert repo.set_progress("b2goal")[0]["owned"] == 1
    grid = {c["id"]: c["owned_qty"] for c in repo.set_cards_with_state("b2goal")}
    assert grid["b2-114"] == 1
    reprints = repo.items_by_card("b2-114", include_reprints=True)
    assert [r["card_id"] for r in reprints] == ["bs-85"]


def test_rating_spans_both_spellings(repo):
    repo.set_card_rating("bs-85", 4)
    rated = {r["card_id"]: r["rating"]
             for r in repo._all("SELECT card_id, rating FROM card_ratings")}
    assert rated == {"bs-85": 4, "b2-114": 4}


def test_init_db_backfills_a_database_from_before_the_column(tmp_path):
    """An existing database gets the column *and* its values on next start."""
    db = tmp_path / "old.db"
    r = PokemonRepo(db)
    r.init_db()
    _sets(r)
    r.upsert_cards([
        {"id": "bs-85", "official_set_id": "bs", "name": "Pokemon Center",
         "number": "85", "artist": "Keiji Kinebuchi"},
        {"id": "b2-114", "official_set_id": "b2", "name": "Pokémon Center",
         "number": "114", "artist": "Keiji Kinebuchi"},
    ])
    r.close()
    # Age the database: drop the column and its index the way a pre-#102
    # schema never had them.
    c = sqlite3.connect(db)
    c.execute("DROP INDEX IF EXISTS idx_cards_name_key")
    c.execute("ALTER TABLE cards DROP COLUMN name_key")
    c.commit(); c.close()
    r2 = PokemonRepo(db)
    r2.init_db()
    keys = {row["id"]: row["name_key"]
            for row in r2._all("SELECT id, name_key FROM cards")}
    assert keys == {"bs-85": "pokemoncenter", "b2-114": "pokemoncenter"}
