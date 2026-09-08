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
from tombot.services.tcggo_catalog import (TcggoCatalog, normalized_name,
                                           resolve_collisions)


def _p(pid, card_id, name, artist=None):
    return {"product_id": pid, "card_id": card_id, "name": name,
            "artist": artist}


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


def test_celebrations_collisions_split_on_the_artist():
    """The real CEL 15 pile-up: one code, five cards, five illustrators."""
    rows = [_p(1, "cel-15", "Lunala", "kirisAki"),
            _p(2, "cel-15", "Venusaur", "Mitsuhiro Arita"),
            _p(3, "cel-15", "Claydol", "Midori Harada"),
            _p(4, "cel-15", "Rocket's Zapdos", "Shin-ichi Yoshida"),
            _p(5, "cel-15", "Here Comes Team Rocket!", "Ken Sugimori")]
    resolve_collisions(rows)
    ids = [r["card_id"] for r in rows]
    assert len(set(ids)) == 5 and ids[0] == "cel-15"


# Issue #69: Base Set came out at 106 cards instead of 102, because tcggo spells
# four of them differently on the shadowless products than on the unlimited
# ones. The product ids, names and artists below are the ones actually stored on
# the live instance. Every pair is one card by two names — same illustrator.
BASE_SET_SPELLING_PAIRS = [
    ("bs-55", 273750, "Nidoran \u2642", 660173, "Nidoran M", "Ken Sugimori"),
    ("bs-73", 273768, "Imposter Professor Oak", 660146,
     "Impostor Professor Oak", "Ken Sugimori"),
    ("bs-85", 273780, "Pokemon Center", 660121, "Pok\u00e9mon Center",
     "Keiji Kinebuchi"),
    ("bs-86", 273781, "Pok\u00e9mon Flute", 660120, "Pokemon Flute",
     "Keiji Kinebuchi"),
]


@pytest.mark.parametrize("card_id,pid_a,name_a,pid_b,name_b,artist",
                         BASE_SET_SPELLING_PAIRS)
def test_one_card_spelled_two_ways_stays_one_card(card_id, pid_a, name_a,
                                                  pid_b, name_b, artist):
    rows = [_p(pid_a, card_id, name_a, artist), _p(pid_b, card_id, name_b, artist)]
    resolve_collisions(rows)
    assert {r["card_id"] for r in rows} == {card_id}


def test_imposter_vs_impostor_needs_the_artist_not_the_name():
    """A real letter apart. Normalising the name cannot merge these; the
    illustrator can, which is why the artist is the primary signal."""
    assert normalized_name("Imposter Professor Oak") != \
        normalized_name("Impostor Professor Oak")


def test_normalized_name_folds_accents_and_gender_signs():
    assert normalized_name("Pok\u00e9mon Center") == normalized_name("Pokemon Center")
    assert normalized_name("Nidoran \u2642") == normalized_name("Nidoran M")
    assert normalized_name("Nidoran \u2640") == normalized_name("Nidoran F")
    assert normalized_name("Rocket's Zapdos") != normalized_name("Lunala")


def test_without_artists_it_falls_back_to_the_normalized_name():
    """A set where tcggo sends no illustrator still must not split on an accent,
    and still must split two genuinely different cards."""
    rows = [_p(1, "bs-85", "Pokemon Center"), _p(2, "bs-85", "Pok\u00e9mon Center")]
    resolve_collisions(rows)
    assert {r["card_id"] for r in rows} == {"bs-85"}

    rows = [_p(1, "cel-2", "Reshiram"), _p(2, "cel-2", "Blastoise")]
    resolve_collisions(rows)
    assert len({r["card_id"] for r in rows}) == 2


def test_a_blank_artist_on_one_product_does_not_split_the_card():
    """All-or-nothing: a group is judged by artist only when every product has
    one, so a missing illustrator cannot invent a card on its own."""
    rows = [_p(10, "bs-2", "Blastoise", "Ken Sugimori"),
            _p(20, "bs-2", "Blastoise", None)]
    resolve_collisions(rows)
    assert {r["card_id"] for r in rows} == {"bs-2"}


def test_two_artists_sharing_a_name_get_distinct_ids():
    """The suffix is the name, so a name collision inside one code must still
    come out unique or the split would undo itself."""
    rows = [_p(1, "x-1", "Base", "Artist A"), _p(2, "x-1", "Same", "Artist B"),
            _p(3, "x-1", "Same", "Artist C")]
    resolve_collisions(rows)
    assert len({r["card_id"] for r in rows}) == 3


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
