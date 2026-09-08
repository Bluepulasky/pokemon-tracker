"""Issue #68: a printing is a row, even when Cardmarket's id says otherwise.

market_products was keyed on `cardmarket_id`, and the importer skipped any row
that had none. tcggo breaks both assumptions, so printings were being dropped:

  * it stamps genuinely different print runs with one id — Base Set Charizard
    comes back as "1st Edition Shadowless" at 50,000 EUR and "Shadowless" at
    2,000 EUR, both on product 660224
  * it sends no id at all on others — 31 Base Set printings, and the 11 Base
    Set 2 cards that were therefore missing from the catalogue outright

Base Set: tcggo sends 307 rows (102 "1st Edition Shadowless", 100 "Shadowless",
101 "Unlimited" — one per real print run of all 102 cards) and 193 were stored.

The numbers and product ids below are what tcggo actually returned.
"""
import pytest

from tombot.config import Config
from tombot.services.market_import import MarketImporter
from tombot.services.repository import PokemonRepo
from tombot.services.tcggo_catalog import TcggoCatalog, resolve_collisions


def _raw(pid, code, name, version, nm=10.0, artist="Ken Sugimori"):
    """A row shaped the way tcggo sends one."""
    return {"cardmarket_id": pid, "card_code_number": code, "name": name,
            "version": version, "rarity": "Rare Holo", "artist": artist,
            "supertype": "Pokémon", "image": None, "links": {},
            "prices": {"cardmarket": {"lowest_near_mint": nm, "currency": "EUR",
                                      "30d_average": nm, "available_items": 5}}}


# ------------------------------------------------------- the importer's dedupe

def test_two_print_runs_sharing_one_product_id_both_survive():
    """The Charizard case. Keyed on the product id, one of these was lost."""
    rows = [_raw(660224, "BS 4", "Charizard", "1st Edition Shadowless", 50000.0),
            _raw(660224, "BS 4", "Charizard", "Shadowless", 2000.0)]
    kept = MarketImporter._dedupe(None, rows)
    assert len(kept) == 2
    assert {r["version"] for r in kept} == {"1st Edition Shadowless", "Shadowless"}


def test_a_printing_with_no_product_id_is_kept():
    """Pidgey's Unlimited arrives with no cardmarket_id and a 1.50 price. It is
    a printing you can own; it just has no buy link."""
    rows = [_raw(660171, "BS 57", "Pidgey", "1st Edition Shadowless", 40.0),
            _raw(660171, "BS 57", "Pidgey", "Shadowless", 10.0),
            _raw(None, "BS 57", "Pidgey", "Unlimited", 1.5)]
    kept = MarketImporter._dedupe(None, rows)
    assert len(kept) == 3
    unlimited = next(r for r in kept if r["version"] == "Unlimited")
    assert unlimited["prices"]["cardmarket"]["lowest_near_mint"] == 1.5


def test_a_real_repeat_of_one_printing_still_collapses():
    """Same card, same print run, twice — that IS one printing. The row with an
    offer behind it wins."""
    rows = [_raw(1, "BS 4", "Charizard", "Unlimited", None),
            _raw(1, "BS 4", "Charizard", "Unlimited", 599.9)]
    kept = MarketImporter._dedupe(None, rows)
    assert len(kept) == 1
    assert kept[0]["prices"]["cardmarket"]["lowest_near_mint"] == 599.9


def test_a_row_with_an_id_beats_an_identical_one_without():
    rows = [_raw(None, "BS 4", "Charizard", "Unlimited", 599.9),
            _raw(273699, "BS 4", "Charizard", "Unlimited", 599.9)]
    kept = MarketImporter._dedupe(None, rows)
    assert len(kept) == 1 and kept[0]["cardmarket_id"] == 273699


# ------------------------------------------------------------------ the table

@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DB_PATH", tmp_path / "p.db")
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    r.upsert_official_set({"id": "bs", "name": "Base", "series": "", "total": 102,
                           "printed_total": 102, "release_date": "1999/01/09",
                           "ptcgo_code": "BS", "logo_url": None, "symbol_url": None})
    return r


def _stored(pid, card_id, version, name="Charizard", code="BS 4", episode=171):
    return {"cardmarket_id": pid, "episode_id": episode, "card_id": card_id,
            "code": code, "number": code.split(" ")[-1], "name": name,
            "version": version, "rarity": "Rare Holo", "currency": "EUR",
            "price": 1.0, "price_low": 1.0, "price_avg30": None, "price_avg7": None,
            "available": 5, "image": None, "market_url": None,
            "artist": "Mitsuhiro Arita", "supertype": "Pokémon"}


def test_the_table_holds_both_print_runs_of_one_product_id(repo):
    repo.upsert_market_products([
        _stored(660224, "bs-4", "1st Edition Shadowless"),
        _stored(660224, "bs-4", "Shadowless"),
    ])
    got = repo.market_products_for_card("bs-4")
    assert len(got) == 2
    assert {r["version"] for r in got} == {"1st Edition Shadowless", "Shadowless"}
    assert {r["cardmarket_id"] for r in got} == {660224}
    assert len({r["id"] for r in got}) == 2, "each printing gets its own id"


def test_reimporting_updates_a_printing_in_place(repo):
    repo.upsert_market_products([_stored(660224, "bs-4", "Shadowless")])
    first = repo.market_products_for_card("bs-4")[0]["id"]
    row = _stored(660224, "bs-4", "Shadowless")
    row["price"] = 2000.0
    repo.upsert_market_products([row])
    got = repo.market_products_for_card("bs-4")
    assert len(got) == 1, "the same printing must not be inserted twice"
    assert got[0]["id"] == first, "and must keep its id, which items point at"
    assert got[0]["price"] == 2000.0


def test_a_printing_with_no_product_id_is_stored(repo):
    repo.upsert_market_products([_stored(None, "bs-57", "Unlimited",
                                         name="Pidgey", code="BS 57")])
    got = repo.market_products_for_card("bs-57")
    assert len(got) == 1 and got[0]["cardmarket_id"] is None


def test_two_cards_under_one_code_do_not_collide(repo):
    """Celebrations files Reshiram and Blastoise both at "CEL 2", both with no
    version. The key is the card, not the code, precisely for this."""
    repo.upsert_market_products([
        _stored(576747, "cel-2", "", name="Reshiram", code="CEL 2", episode=35),
        _stored(576771, "cel-2-blastoise", "", name="Blastoise", code="CEL 2",
                episode=35),
    ])
    assert [r["name"] for r in repo.market_products_for_card("cel-2")] == ["Reshiram"]
    assert [r["name"] for r in
            repo.market_products_for_card("cel-2-blastoise")] == ["Blastoise"]


# ------------------------------------------------------- cards need a product

def test_a_card_whose_only_row_has_no_product_id_still_appears(repo):
    """Base Set 2's 11 missing cards. Cards are built from products, so dropping
    the row dropped the card — the set came out 119 of 130."""
    rows = [_raw(None, "B2 40", "Ninetales", "Unlimited", 3.0)]
    kept = MarketImporter._dedupe(None, rows)
    product_rows = [MarketImporter._row(r, 167, "B2") for r in kept]
    resolve_collisions(product_rows)
    repo.upsert_market_products(product_rows)
    built = TcggoCatalog(repo).build_set({
        "id": 167, "code": "B2", "name": "Base Set 2", "released_at": "2000-02-24",
        "cards_total": 130})
    assert built["cards"] == 1
    assert repo.get_card("b2-40")["name"] == "Ninetales"


# ---------------------------------------------------------------- the relink

def test_owned_rows_are_relinked_to_their_printing(repo):
    """An item saved before the change points at a Cardmarket id. It is matched
    back to the printing whose print run is the variant the row was saved as.

    Jungle Flareon is the real case: tcggo returns its 1st Edition and its
    Unlimited both on product 273816, and those derive different variants, so
    the saved variant picks the right one of the two.
    """
    repo.upsert_official_set({"id": "ju", "name": "Jungle", "series": "",
                              "total": 64, "printed_total": 64,
                              "release_date": "1999/06/16", "ptcgo_code": "JU",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "ju-19", "official_set_id": "ju", "name": "Flareon",
                        "number": "19", "rarity": "rare"}])
    for version in ("1st Edition", "Unlimited"):
        row = _stored(273816, "ju-19", version, name="Flareon", code="JU 19",
                      episode=170)
        row["rarity"] = "rare"
        repo.upsert_market_products([row])
    repo.upsert_collection_item({"card_id": "ju-19", "variant": "first_edition",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": 273816})

    out = repo.relink_collection_products()

    assert out["relinked"] == 1
    item = repo.items_by_card("ju-19")[0]
    linked = repo.get_market_product(item["market_product_id"])
    assert linked["version"] == "1st Edition", \
        "the 1st-edition row must not be relinked to the Unlimited one"


def test_an_ambiguous_relink_is_left_alone_rather_than_guessed(repo):
    """Two printings share the id and neither matches the saved variant. A wrong
    printing is a wrong price, so the row is left for the user to re-pick."""
    repo.upsert_cards([{"id": "bs-4", "official_set_id": "bs", "name": "Charizard",
                        "number": "4", "rarity": "Rare Holo"}])
    repo.upsert_market_products([
        _stored(660224, "bs-4", "1st Edition Shadowless"),
        _stored(660224, "bs-4", "Shadowless"),
    ])
    # Both of Charizard's runs derive "shadowless" (a 1st Edition Shadowless IS
    # a shadowless run), so the saved variant cannot tell them apart.
    repo.upsert_collection_item({"card_id": "bs-4", "variant": "shadowless",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": 660224})

    out = repo.relink_collection_products()

    assert out["relinked"] == 0 and out["ambiguous"] == 1
    assert repo.items_by_card("bs-4")[0]["market_product_id"] == 660224


def test_an_already_linked_row_is_left_alone(repo):
    repo.upsert_cards([{"id": "bs-4", "official_set_id": "bs", "name": "Charizard",
                        "number": "4", "rarity": "Rare Holo"}])
    repo.upsert_market_products([_stored(660224, "bs-4", "Shadowless")])
    pid = repo.market_products_for_card("bs-4")[0]["id"]
    repo.upsert_collection_item({"card_id": "bs-4", "variant": "shadowless",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": pid})

    assert repo.relink_collection_products() == {"relinked": 0, "ambiguous": 0,
                                                 "unmatched": 0}
    assert repo.items_by_card("bs-4")[0]["market_product_id"] == pid


# ------------------------------------------------------- the old table is gone

def test_a_database_keyed_on_the_product_id_is_rebuilt(tmp_path, monkeypatch):
    """schema.sql is CREATE ... IF NOT EXISTS, so the changed table is the one
    thing init_db cannot deliver on its own. The old one has to be dropped."""
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE market_products (
                       product_id INTEGER PRIMARY KEY, episode_id INTEGER NOT NULL,
                       card_id TEXT, code TEXT, number TEXT, name TEXT,
                       version TEXT, rarity TEXT,
                       currency TEXT NOT NULL DEFAULT 'EUR', price REAL,
                       price_low REAL, price_avg30 REAL, price_avg7 REAL,
                       available INTEGER, image TEXT, market_url TEXT,
                       updated_at TEXT NOT NULL DEFAULT (datetime('now')))""")
    con.execute("INSERT INTO market_products(product_id, episode_id, card_id) "
                "VALUES (660224, 171, 'bs-4')")
    con.commit()
    con.close()

    monkeypatch.setattr(Config, "DB_PATH", db)
    r = PokemonRepo(db)
    r.init_db()

    cols = {row["name"] for row in
            r._all("SELECT name FROM pragma_table_info('market_products')")}
    assert "id" in cols and "cardmarket_id" in cols and "product_id" not in cols
    # Both print runs now fit where only one did before.
    r.upsert_market_products([_stored(660224, "bs-4", "1st Edition Shadowless"),
                              _stored(660224, "bs-4", "Shadowless")])
    assert len(r.market_products_for_card("bs-4")) == 2


def test_an_already_migrated_database_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DB_PATH", tmp_path / "new.db")
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    r.upsert_official_set({"id": "bs", "name": "Base", "series": "", "total": 102,
                           "printed_total": 102, "release_date": "1999/01/09",
                           "ptcgo_code": "BS", "logo_url": None,
                           "symbol_url": None})
    r.upsert_market_products([_stored(660224, "bs-4", "Shadowless")])
    r.init_db()                                   # a restart must not wipe it
    assert len(r.market_products_for_card("bs-4")) == 1
