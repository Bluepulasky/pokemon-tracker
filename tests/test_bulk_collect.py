"""Quick-select bulk-applies the collecting star to a whole set.

'Only holo / only non-holo / all / none / invert' is the fast way to say how you
want to collect a set. It lands on exactly the cards the grid shows as holo
(rarity contains 'holo'), and it survives a rebuild because it writes the same
exclude_cards the per-card toggle does.
"""
import json

import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "b.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    r.upsert_official_set({"id": "ju", "name": "Jungle", "series": "Base",
                           "printed_total": 4, "total": 4,
                           "release_date": "1999/06/16", "ptcgo_code": "JU",
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "ju-1", "official_set_id": "ju", "name": "Clefable", "number": "1",
         "rarity": "Rare Holo"},
        # deliberately the OTHER spelling tcggo uses, to prove the /holo/ test
        {"id": "ju-2", "official_set_id": "ju", "name": "Electrode", "number": "2",
         "rarity": "Holo Rare"},
        {"id": "ju-20", "official_set_id": "ju", "name": "Cleffa", "number": "20",
         "rarity": "Common"},
        {"id": "ju-21", "official_set_id": "ju", "name": "Pidgey", "number": "21",
         "rarity": "Common"},
    ])
    r.upsert_collection_set({"id": "mi", "name": "Jungle",
                             "rules_json": json.dumps({"include_sets": ["ju"]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.extensions["setbuilder"].build("mi")
    return a


def _collecting(app):
    cards = app.extensions["repo"].set_cards_with_state("mi")
    return {c["id"] for c in cards if c["collecting"]}


def _bulk(app, selector):
    return app.test_client().put("/api/sets/mi/collect", json={"selector": selector})


def test_all_collects_everything(app):
    _bulk(app, "none")
    assert _bulk(app, "all").get_json()["collecting"] == 4
    assert _collecting(app) == {"ju-1", "ju-2", "ju-20", "ju-21"}


def test_holo_uses_the_same_holo_test_as_the_grid(app):
    """Both rarity spellings ('Rare Holo' and 'Holo Rare') count as holo."""
    _bulk(app, "holo")
    assert _collecting(app) == {"ju-1", "ju-2"}


def test_non_holo_is_the_complement(app):
    _bulk(app, "non-holo")
    assert _collecting(app) == {"ju-20", "ju-21"}


def test_none_clears_everything(app):
    _bulk(app, "none")
    assert _collecting(app) == set()


def test_invert_flips_the_selection(app):
    _bulk(app, "holo")                       # {ju-1, ju-2}
    _bulk(app, "invert")
    assert _collecting(app) == {"ju-20", "ju-21"}


def test_a_bulk_pick_survives_a_rebuild(app):
    _bulk(app, "holo")
    app.extensions["setbuilder"].build("mi")   # a rebuild must not lose it
    assert _collecting(app) == {"ju-1", "ju-2"}


def test_an_unknown_selector_is_400(app):
    assert _bulk(app, "sometimes").status_code == 400
