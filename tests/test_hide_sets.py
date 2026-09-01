"""Hiding a set keeps its data but drops it from the Sets view and the totals.

For sets added by accident or while testing that should not count toward the
collection. Hidden is a mark, not a delete: cards, products and the goal stay,
and the set is un-hidden from Mantenimiento.
"""
import json

import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "h.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    for sid, name, rel in (("bs", "Base Set", "1999/01/09"),
                           ("ju", "Jungle", "1999/06/16")):
        r.upsert_official_set({"id": sid, "name": name, "series": "Base",
                               "printed_total": 1, "total": 1, "release_date": rel,
                               "ptcgo_code": sid.upper(), "logo_url": None,
                               "symbol_url": None})
        r.upsert_cards([{"id": f"{sid}-1", "official_set_id": sid, "name": "X",
                         "number": "1", "rarity": "Common"}])
        r.upsert_collection_set({"id": f"{sid}-goal", "name": name,
                                 "rules_json": json.dumps({"include_sets": [sid]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.extensions["setbuilder"].build_all() if hasattr(a.extensions["setbuilder"], "build_all") \
        else [a.extensions["setbuilder"].build(s["id"]) for s in r.list_collection_sets()]
    return a


def _listed_ids(app):
    return {s["id"] for s in app.test_client().get("/api/sets").get_json()["data"]}


def _hide(app, sid, hidden=True):
    return app.test_client().put(f"/api/sets/{sid}/hidden", json={"hidden": hidden})


# --------------------------------------------------------------- the mark
def test_hidden_set_leaves_the_sets_list(app):
    assert _listed_ids(app) == {"bs-goal", "ju-goal"}
    assert _hide(app, "bs-goal").status_code == 200
    assert _listed_ids(app) == {"ju-goal"}          # bs gone, ju stays


def test_hidden_set_leaves_the_completion_totals(app):
    """The dashboard sums set_progress(), which now skips hidden sets."""
    repo = app.extensions["repo"]
    assert len(repo.set_progress()) == 2
    _hide(app, "bs-goal")
    assert len(repo.set_progress()) == 1            # one fewer set counts


def test_the_data_is_untouched(app):
    repo = app.extensions["repo"]
    _hide(app, "bs-goal")
    assert repo.get_collection_set("bs-goal") is not None       # goal kept
    assert repo.get_card("bs-1") is not None                    # cards kept
    assert repo.get_set_slots("bs-goal")                        # slots kept


def test_a_hidden_set_is_still_viewable_by_id(app):
    _hide(app, "bs-goal")
    # its own detail endpoint still resolves it (to confirm before un-hiding)
    assert app.test_client().get("/api/sets/bs-goal").status_code == 200
    assert len(app.extensions["repo"].set_progress("bs-goal")) == 1


# ---------------------------------------------------------------- un-hide
def test_maintenance_lists_hidden_sets(app):
    _hide(app, "bs-goal")
    rows = app.test_client().get("/api/maintenance/hidden-sets").get_json()["data"]
    assert [s["id"] for s in rows] == ["bs-goal"]


def test_unhide_brings_it_back(app):
    _hide(app, "bs-goal")
    assert _hide(app, "bs-goal", hidden=False).status_code == 200
    assert _listed_ids(app) == {"bs-goal", "ju-goal"}
    assert app.test_client().get("/api/maintenance/hidden-sets").get_json()["data"] == []


def test_hiding_an_unknown_set_is_404(app):
    assert _hide(app, "nope-goal").status_code == 404
