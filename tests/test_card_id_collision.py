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
from tombot.services.tcggo_catalog import (TcggoCatalog, artist_key, normalized_name,
                                           resolve_collisions)


def _p(pid, card_id, name, artist=None):
    return {"cardmarket_id": pid, "card_id": card_id, "name": name,
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
    return {"cardmarket_id": pid, "episode_id": 35, "card_id": card_id, "code": code,
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


# Issue #108: Dark Crobat (NDE 2) and 24 other Neo cards came out twice, one
# card per print run. tcggo credits the CGI studio on the 1st Edition product
# and not on the Unlimited one, so the whole credit strings differed. The
# credits below are the ones stored on the live instance.
NEO_CO_CREDIT_PAIRS = [
    ("nde-2", "Dark Crobat", "Shin-ichi Yoshikawa, CR CG gangs", "Shin-ichi Yoshikawa"),
    ("nde-41", "Heracross", "K. Hoshiba, CR CG gangs", "K. Hoshiba"),
    ("ng-93", "Gold Berry", "Ryuta Kusumi, CR CG gangs", "Ryuta Kusumi"),
    # The nickname arrives with a different number of quote marks each time.
    ("nr-10", "Magneton", '"Big Mama"""" Tagawa"', '"Big Mama"""""""" Tagawa""""'),
]


@pytest.mark.parametrize("card_id,name,first,unlimited", NEO_CO_CREDIT_PAIRS)
def test_a_studio_co_credit_does_not_make_a_second_card(card_id, name, first, unlimited):
    rows = [_p(1, card_id, name, first), _p(2, card_id, name, unlimited)]
    resolve_collisions(rows)
    assert {r["card_id"] for r in rows} == {card_id}


def test_artist_key_is_the_lead_illustrator():
    assert artist_key("Shin-ichi Yoshikawa, CR CG gangs") == "shin-ichi yoshikawa"
    assert artist_key('"Big Mama" Tagawa & Benimaru Itoh') == "big mama tagawa"
    assert artist_key("  Ken   Sugimori ") == "ken sugimori"
    assert artist_key(None) == ""


def test_dedupe_keeps_both_print_runs_of_a_co_credited_card():
    """The dedupe key must agree with the splitter: two print runs are two
    printings of one card, not one printing to throw away and not two cards."""
    from tombot.services.market_import import _card_identity
    a = {"name": "Dark Crobat", "artist": {"name": "Shin-ichi Yoshikawa, CR CG gangs"}}
    b = {"name": "Dark Crobat", "artist": {"name": "Shin-ichi Yoshikawa"}}
    assert _card_identity(a) == _card_identity(b)


def _neo_product(pid, card_id, version, artist):
    row = _prod_row(pid, card_id, "NDE 2", "Dark Crobat", "Rare Holo")
    row.update(episode_id=60, version=version, artist=artist)
    return row


def _build_neo_destiny(repo):
    TcggoCatalog(repo).build_set({"id": 60, "code": "NDE", "name": "Neo Destiny",
                                  "released_at": "2002-02-28", "cards_total": 113})


def test_startup_rejoins_a_card_an_old_import_split(repo):
    """The installed database already holds the split; fixing the rule must
    not need a (metered) re-import to repair it. init_db does it from the
    stored products, and the set's goal loses the phantom slot."""
    from tombot.services.setbuilder import SetBuilder

    repo.upsert_market_products([
        _neo_product(18354, "nde-2", "1st Edition", "Shin-ichi Yoshikawa, CR CG gangs"),
        _neo_product(49957, "nde-2-dark-crobat", "Unlimited", "Shin-ichi Yoshikawa"),
    ])
    _build_neo_destiny(repo)
    repo.upsert_collection_set({"id": "nde-completo", "name": "Neo Destiny",
                                "description": "", "group_name": None, "position": 0,
                                "rules_json": '{"include_sets": ["nde"]}'})
    SetBuilder(repo).build("nde-completo")
    assert len(repo.get_set_slots("nde-completo")) == 2          # the bug

    repo.init_db()

    assert repo.get_card("nde-2-dark-crobat") is None
    assert [p["version"] for p in repo.market_products_for_card("nde-2")] == \
        ["1st Edition", "Unlimited"]
    assert len(repo.get_set_slots("nde-completo")) == 1
    assert repo.rejoin_split_cards()["moved"] == 0               # idempotent


def test_startup_leaves_real_collisions_split(repo):
    """Celebrations' Reshiram and Classic Collection Blastoise share CEL 2 with
    different illustrators; the repair must not glue them together."""
    rows = [_prod_row(576747, "cel-2", "CEL 2", "Reshiram", "rare"),
            _prod_row(576771, "cel-2", "CEL 2", "Blastoise", "Classic Collection")]
    rows[0]["artist"], rows[1]["artist"] = "Aya Kusube", "Ken Sugimori"
    resolve_collisions(rows)
    repo.upsert_market_products(rows)
    TcggoCatalog(repo).build_set({"id": 35, "code": "CEL", "name": "Celebrations",
                                  "released_at": "2021-10-08", "cards_total": 25})

    repo.init_db()

    assert repo.get_card("cel-2-blastoise")["name"] == "Blastoise"
    assert repo.rejoin_split_cards()["moved"] == 0


def test_startup_keeps_a_split_half_the_user_owns(repo):
    """A copy filed under the phantom half keeps that card rather than being
    deleted under the user; only pure catalogue rows are dropped."""
    repo.upsert_market_products([
        _neo_product(18354, "nde-2", "1st Edition", "Shin-ichi Yoshikawa, CR CG gangs"),
        _neo_product(49957, "nde-2-dark-crobat", "Unlimited", "Shin-ichi Yoshikawa"),
    ])
    _build_neo_destiny(repo)
    unlimited = repo.market_products_for_card("nde-2-dark-crobat")[0]
    repo.upsert_collection_item({"card_id": "nde-2-dark-crobat", "variant": "holo",
                                 "condition": "M/NM", "language": "en", "quantity": 1,
                                 "market_product_id": unlimited["id"]})

    repo.init_db()

    assert repo.get_card("nde-2-dark-crobat") is not None
    assert [p["version"] for p in repo.market_products_for_card("nde-2")] == \
        ["1st Edition", "Unlimited"]
