"""Issue #75: a set tcggo lists but holds no cards for, and a shouted rarity.

tcggo's catalogue contains "Celebrations: Classic Collection" (episode 36, code
CEL, "25 cards"), and asking it for those cards returns nothing — they are filed
under Celebrations itself (episode 35), which is why Blastoise and Reshiram are
both "CEL 2". Pressing Añadir on it spent a metered request to import zero.

The numbers here are what tcggo actually returns.
"""
import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo
from tombot.services.tcggo_catalog import (canonical_rarity,
                                           canonicalise_stored_rarities)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "e.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    return r


def _episode(eid, code, name, cards, products):
    """An episode the shape tcggo sends one."""
    return {"id": eid, "code": code, "name": name, "slug": name.lower(),
            "released_at": "2021-10-08", "logo": None, "cards_total": cards,
            "prices": {"cardmarket": {"total": products, "currency": "EUR"}}}


CELEBRATIONS = _episode(35, "CEL", "Celebrations", 25, 565)
CLASSIC = _episode(36, "CEL", "Celebrations: Classic Collection", 25, 0)


def test_the_product_total_is_remembered_and_is_not_the_card_total(repo):
    repo.remember_episodes([CELEBRATIONS, CLASSIC])
    got = {e["episode_id"]: e for e in repo.search_known_episodes("Celebrations")}
    assert got[35]["products_total"] == 565
    assert got[36]["products_total"] == 0
    # Both claim 25 cards. That is exactly why cards_total cannot be the signal.
    assert got[35]["cards_total"] == got[36]["cards_total"] == 25


def test_an_episode_we_were_told_nothing_about_is_not_treated_as_empty(repo):
    """Unknown is not zero. A set with no total stays addable rather than being
    hidden on a guess."""
    bare = {"id": 99, "code": "XY", "name": "Sin datos", "cards_total": 12}
    repo.remember_episodes([bare])
    got = repo.search_known_episodes("Sin datos")[0]
    assert got["products_total"] is None


# ------------------------------------------------------------------ the API

@pytest.fixture()
def client(repo):
    from tombot import create_app
    app = create_app(Config)
    app.config["TESTING"] = True
    repo.remember_episodes([CELEBRATIONS, CLASSIC])
    return app.test_client()


def test_the_search_marks_the_empty_set_and_not_the_real_one(client):
    eps = {e["id"]: e for e in
           client.get("/api/maintenance/episodes?q=Celebrations").get_json()["episodes"]}
    assert eps[36]["empty"] is True
    assert eps[35]["empty"] is False


def test_importing_an_empty_set_is_refused_before_spending_a_request(client):
    """The button is hidden, but the endpoint is reachable without it."""
    r = client.post("/api/maintenance/episodes/36/import")
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"]["code"] == "empty_episode"
    assert "Classic Collection" in body["error"]["message"]


def test_a_real_set_is_not_refused(client):
    """It fails for want of a configured source, not for being empty — the
    guard must not stand in front of a set that has products."""
    r = client.post("/api/maintenance/episodes/35/import")
    assert r.status_code != 409


# --------------------------------------------------------------- the rarity

def test_secret_rare_canonicalises_both_ways_round():
    assert canonical_rarity("SECRET RARE") == "Rare Secret"
    assert canonical_rarity("Secret Rare") == "Rare Secret"
    assert canonical_rarity("Rare Secret") == "Rare Secret"


def test_stored_rarities_are_repaired_without_a_reimport(repo):
    """The health check went red on "Rare Secret / SECRET RARE" after a full
    re-import. Adding a mapping only helps the next one, and nobody should have
    to re-import sixteen sets to clear it."""
    repo.upsert_official_set({"id": "bs", "name": "Base", "series": "",
                              "total": 102, "printed_total": 102,
                              "release_date": "1999/01/09", "ptcgo_code": "BS",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([
        {"id": "bs-1", "official_set_id": "bs", "name": "A", "number": "1",
         "rarity": "SECRET RARE"},
        {"id": "bs-2", "official_set_id": "bs", "name": "B", "number": "2",
         "rarity": "Rare Secret"},
        {"id": "bs-3", "official_set_id": "bs", "name": "C", "number": "3",
         "rarity": "Common"},
    ])

    out = canonicalise_stored_rarities(repo)

    assert out["spellings"] == 1 and out["cards"] == 1
    assert {r["rarity"] for r in repo._all("SELECT DISTINCT rarity FROM cards")} \
        == {"Rare Secret", "Common"}


def test_the_health_check_stops_complaining(repo):
    from tombot.services.health import check_rarities
    repo.upsert_official_set({"id": "bs", "name": "Base", "series": "",
                              "total": 102, "printed_total": 102,
                              "release_date": "1999/01/09", "ptcgo_code": "BS",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([
        {"id": "bs-1", "official_set_id": "bs", "name": "A", "number": "1",
         "rarity": "SECRET RARE"},
        {"id": "bs-2", "official_set_id": "bs", "name": "B", "number": "2",
         "rarity": "Rare Secret"},
    ])
    assert any(f["level"] == "error" for f in check_rarities(repo))

    canonicalise_stored_rarities(repo)

    assert not [f for f in check_rarities(repo) if f["level"] == "error"]


def test_repairing_twice_changes_nothing_the_second_time(repo):
    repo.upsert_official_set({"id": "bs", "name": "Base", "series": "",
                              "total": 102, "printed_total": 102,
                              "release_date": "1999/01/09", "ptcgo_code": "BS",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "bs-1", "official_set_id": "bs", "name": "A",
                        "number": "1", "rarity": "SECRET RARE"}])
    canonicalise_stored_rarities(repo)
    assert canonicalise_stored_rarities(repo) == {"spellings": 0, "cards": 0}
