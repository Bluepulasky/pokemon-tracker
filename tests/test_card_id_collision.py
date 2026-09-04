"""Different cards that share a code+number must get distinct card_ids.

card_id is `{setcode}-{number}`, which assumes code+number identifies a card in
an episode. The tcggo "Celebrations" episode breaks that — it bundles the
Classic Collection under the same CEL code, so its Blastoise ("CEL 2") collided
with the base Reshiram ("CEL 2") and five cards shared "CEL 15", cross-polluting
the version picker and pricing. resolve_collisions splits them apart.
"""
import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo
from tombot.services.tcggo_catalog import TcggoCatalog, resolve_collisions


def _p(pid, card_id, name):
    return {"product_id": pid, "card_id": card_id, "name": name}


def test_different_cards_are_split_lowest_product_id_keeps_the_id():
    rows = [_p(576771, "cel-2", "Blastoise"), _p(576747, "cel-2", "Reshiram")]
    resolve_collisions(rows)
    got = {r["name"]: r["card_id"] for r in rows}
    assert got == {"Reshiram": "cel-2", "Blastoise": "cel-2-blastoise"}


def test_five_way_collision_all_distinct():
    rows = [_p(1, "cel-15", "Lunala"), _p(2, "cel-15", "Venusaur"),
            _p(3, "cel-15", "Claydol"), _p(4, "cel-15", "Rocket's Zapdos")]
    resolve_collisions(rows)
    ids = [r["card_id"] for r in rows]
    assert len(set(ids)) == 4 and ids[0] == "cel-15"


def test_printings_of_one_card_are_not_split():
    """Base Set Blastoise's four printings all share the name — one card."""
    rows = [_p(10, "bs-2", "Blastoise"), _p(20, "bs-2", "Blastoise"),
            _p(30, "bs-2", "Blastoise")]
    resolve_collisions(rows)
    assert {r["card_id"] for r in rows} == {"bs-2"}


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "c.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    return r


def _prod_row(pid, card_id, code, name, rarity):
    return {"product_id": pid, "episode_id": 35, "card_id": card_id, "code": code,
            "number": code.split(" ")[-1], "name": name, "version": None,
            "rarity": rarity, "currency": "EUR", "price": 1.0, "price_low": 1.0,
            "price_avg30": None, "price_avg7": None, "available": 5, "image": None,
            "market_url": f"https://x/{pid}", "artist": None, "supertype": "Pokémon"}


def test_build_set_makes_distinct_cards_and_clean_products(repo):
    """A collided episode builds one card per logical card, products unmixed."""
    rows = [
        _prod_row(576747, "cel-2", "CEL 2", "Reshiram", "rare"),
        _prod_row(576771, "cel-2", "CEL 2", "Blastoise", "Classic Collection"),
    ]
    resolve_collisions(rows)                       # what the importer does
    repo.upsert_market_products(rows)
    TcggoCatalog(repo).build_set({"id": 35, "code": "CEL", "name": "Celebrations",
                                  "released_at": "2021-10-08", "cards_total": 25})

    assert repo.get_card("cel-2")["name"] == "Reshiram"
    assert repo.get_card("cel-2-blastoise")["name"] == "Blastoise"
    # Each card's products are its own — the picker/pricing no longer cross over.
    assert [p["name"] for p in repo.market_products_for_card("cel-2")] == ["Reshiram"]
    assert [p["name"] for p in repo.market_products_for_card("cel-2-blastoise")] == ["Blastoise"]


def test_reimport_rebuilds_an_existing_goals_slots(repo, monkeypatch):
    """#63: reimport that de-collides a card adds it to the catalogue, but the
    goal already covered the set, so its rule slots must be rebuilt to pick the
    new card up. Before the fix _ensure_collection_set returned early without
    rebuilding, leaving the goal one slot short of the catalogue."""
    from tombot import create_app
    from tombot.api.catalog import _ensure_collection_set

    # First import: the collided episode gives one card (Reshiram) at CEL 2.
    collided = [_prod_row(576747, "cel-2", "CEL 2", "Reshiram", "rare")]
    repo.upsert_market_products(collided)
    TcggoCatalog(repo).build_set({"id": 35, "code": "CEL", "name": "Celebrations",
                                  "released_at": "2021-10-08", "cards_total": 25})

    app = create_app(Config)
    app.extensions["repo"] = repo
    with app.app_context():
        first = _ensure_collection_set("cel", "Celebrations")
        assert first["created"] is True
        assert len(repo.get_set_slots("cel-completo")) == 1

        # Reimport de-collides: Blastoise now lands on its own id in the catalogue.
        deco = [_prod_row(576747, "cel-2", "CEL 2", "Reshiram", "rare"),
                _prod_row(576771, "cel-2-blastoise", "CEL 2", "Blastoise", "Classic Collection")]
        repo.upsert_market_products(deco)
        TcggoCatalog(repo).build_set({"id": 35, "code": "CEL", "name": "Celebrations",
                                      "released_at": "2021-10-08", "cards_total": 25})

        again = _ensure_collection_set("cel", "Celebrations")
        assert again["created"] is False
        assert len(repo.get_set_slots("cel-completo")) == 2, \
            "reimport must rebuild the goal so the de-collided card gets a slot"
