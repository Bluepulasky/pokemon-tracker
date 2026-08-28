"""The Sets view groups by TCG series, ordered by release date (not by an
'added vs seeded' bucket).

series and release_date are catalogue facts carried by the set a rule is built
on, so every set — seeded or imported later — files itself into its era. The
old 'Añadidos' catch-all is gone.
"""
import json

import pytest

from tombot.config import Config, DEFAULT_MODIFIERS
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "s.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db(DEFAULT_MODIFIERS)
    # Deliberately out of chronological order, and one with a blank series.
    for sid, name, series, rel in (
            ("ng", "Neo Genesis", "Neo", "2000/12/16"),
            ("bs", "Base Set", "", "1999/01/09"),      # tcggo leaves this blank
            ("hs", "HeartGold & SoulSilver", "", "2010/02/10"),
            ("fo", "Fossil", "Base", "1999/10/10")):
        r.upsert_official_set({"id": sid, "name": name, "series": series,
                               "printed_total": 1, "total": 1, "release_date": rel,
                               "ptcgo_code": sid.upper(), "logo_url": None,
                               "symbol_url": None})
    for sid, name in (("ng", "Neo Genesis"), ("bs", "Base Set"),
                      ("hs", "HeartGold & SoulSilver"), ("fo", "Fossil")):
        r.upsert_collection_set({"id": f"{sid}-goal", "name": name,
                                 "rules_json": json.dumps({"include_sets": [sid]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    return a


def _sets(app):
    return app.test_client().get("/api/sets").get_json()["data"]


def test_sets_carry_series_and_release_date(app):
    by_name = {s["name"]: s for s in _sets(app)}
    assert by_name["Fossil"]["series"] == "Base"
    assert by_name["Neo Genesis"]["series"] == "Neo"
    assert by_name["Fossil"]["release_date"] == "1999/10/10"


def test_sets_come_back_oldest_first(app):
    names = [s["name"] for s in _sets(app)]
    assert names == ["Base Set", "Fossil", "Neo Genesis", "HeartGold & SoulSilver"]


def test_no_set_is_bucketed_as_added(app):
    # The old 'Añadidos' group_name is never assigned any more.
    groups = {(s.get("group_name") or "") for s in _sets(app)}
    assert "Añadidos" not in groups


def test_a_blank_series_still_orders_by_date(app):
    """HeartGold has no series but must still land last by its 2010 date."""
    sets = _sets(app)
    assert sets[-1]["name"] == "HeartGold & SoulSilver"
    assert not sets[-1]["series"]   # blank — the client shows it as its own block
