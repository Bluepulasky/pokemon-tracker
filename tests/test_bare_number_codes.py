"""A set whose card codes carry no set prefix — Southern Islands says "1", not
"SI 1" — must still import every card (#97)."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from tombot.services.market_import import MarketImporter
from tombot.services.repository import PokemonRepo
from tombot.services.tcggo_catalog import TcggoCatalog, card_id_for, split_code

FIXTURE = Path(__file__).parent / "fixtures" / "tcggo_southern_islands.json"
EPISODE_ID = 161


class _Source:
    """Answers one search page from the fixture and never touches the network."""
    game = "pokemon"

    def __init__(self, rows):
        self.rows = rows

    def _get(self, path, params):
        assert params["episode_id"] == EPISODE_ID
        return {"data": self.rows if params["page"] == 1 else []}


@pytest.fixture()
def repo():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    r = PokemonRepo(path)
    r.init_db()
    yield r
    os.unlink(path)


def test_a_code_with_no_space_is_a_number_not_a_set_prefix():
    assert split_code("1") == ("", "1")
    assert split_code("14") == ("", "14")
    assert split_code("BS 4") == ("BS", "4")
    assert split_code("SK H7") == ("SK", "H7")
    assert split_code("") == ("", "")


def test_every_southern_islands_card_gets_its_own_id(repo):
    rows = json.loads(FIXTURE.read_text())
    importer = MarketImporter(repo, _Source(rows))
    result = importer.import_episode(EPISODE_ID)
    assert result["stored"] == len(rows)

    episode = {"id": EPISODE_ID, "name": "Southern Islands", "code": "",
               "cards_total": 18, "released_at": "2001-07-31"}
    built = TcggoCatalog(repo).build_set(episode)
    cards = repo._all("SELECT * FROM cards WHERE official_set_id = ?", (built["set_id"],))
    assert built["cards"] == len(rows)
    # Without a prefix the set is keyed on its tcggo id, as build_set already
    # did for the set itself — so the card ids agree with it.
    assert built["set_id"] == "161"
    assert {c["id"] for c in cards} == {card_id_for("161", r["card_code_number"]) for r in rows}
    assert {(c["name"], c["number"]) for c in cards} == {(r["name"], r["card_code_number"])
                                                         for r in rows}


def test_a_prefixed_set_is_unchanged(repo):
    """The Base Set shape: "BS 4" keeps producing bs-4."""
    row = MarketImporter._row({"card_code_number": "BS 4", "name": "Charizard",
                               "cardmarket_id": 1}, 171, "BS")
    assert (row["card_id"], row["number"], row["code"]) == ("bs-4", "4", "BS 4")


def test_a_reimport_removes_the_rows_the_old_ids_left_behind(repo):
    """Tom's database after the bug: two products filed under the mangled ids
    "1-" and "1--tentacruel". A re-import must end with 18 cards, not 20 — but
    never drop a product an owned copy still points at."""
    rows = json.loads(FIXTURE.read_text())
    repo.upsert_market_products([
        {"cardmarket_id": 1, "episode_id": EPISODE_ID, "card_id": "1-", "code": "1",
         "number": "", "name": "Butterfree", "version": "", "rarity": None, "currency": "EUR",
         "price": 1, "price_low": None, "price_avg30": None, "price_avg7": None,
         "available": None, "image": None, "market_url": None, "artist": None, "supertype": None},
        {"cardmarket_id": 2, "episode_id": EPISODE_ID, "card_id": "1--tentacruel", "code": "10",
         "number": "", "name": "Primeape", "version": "", "rarity": None, "currency": "EUR",
         "price": 1, "price_low": None, "price_avg30": None, "price_avg7": None,
         "available": None, "image": None, "market_url": None, "artist": None, "supertype": None},
    ])
    episode = {"id": EPISODE_ID, "name": "Southern Islands", "code": ""}
    TcggoCatalog(repo).build_set(episode)
    # One of the stale printings is owned: that row must survive the prune.
    owned = repo._one("SELECT id FROM market_products WHERE card_id = '1-'")["id"]
    repo.upsert_collection_item({"card_id": "1-", "market_product_id": owned})

    result = MarketImporter(repo, _Source(rows)).import_episode(EPISODE_ID)
    assert result["pruned"] == 1
    TcggoCatalog(repo).build_set(episode)

    ids = {c["id"] for c in repo._all("SELECT id FROM cards WHERE official_set_id = '161'")}
    assert "1--tentacruel" not in ids
    assert "1-" in ids, "the owned printing keeps its card"
    assert len(ids) == len(rows) + 1
