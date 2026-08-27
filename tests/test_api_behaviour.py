"""API-layer behaviour.

Every other test drives PokemonRepo directly, so the API layer went uncovered and
a syntax error in it once passed the whole suite. These exercise what the
handlers actually compute — the shaping, filtering and validation that lives
between the repository and the response — rather than asserting a status code.
"""
import os
import tempfile

import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(Config, "CATALOG_IMG_DIR", tmp_path / "media" / "catalog")
    monkeypatch.setattr(Config, "COLLECTION_IMG_DIR", tmp_path / "media" / "collection")
    monkeypatch.setattr(Config, "THUMB_DIR", tmp_path / "media" / "thumbs")

    repo = PokemonRepo(Config.DB_PATH)
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                              "printed_total": 3, "total": 3,
                              "release_date": "1999/01/09", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard",
         "number": "4", "rarity": "Rare Holo"},
        {"id": "base1-2", "official_set_id": "base1", "name": "Blastoise",
         "number": "2", "rarity": "Rare Holo"},
        {"id": "base1-58", "official_set_id": "base1", "name": "Pikachu",
         "number": "58", "rarity": "Common"},
    ])
    repo.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    repo.replace_rule_slots("mine", [
        {"position": 0, "label": "Blastoise", "cards": ["base1-2"],
         "display_card_id": "base1-2"},
        {"position": 1, "label": "Charizard", "cards": ["base1-4"],
         "display_card_id": "base1-4"},
        {"position": 2, "label": "Pikachu", "cards": ["base1-58"],
         "display_card_id": "base1-58"},
    ])

    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.repo = repo
    return a


@pytest.fixture()
def client(app):
    return app.test_client()


# ------------------------------------------------------------- serialisation
def test_card_detail_assembles_catalog_collection_and_printings(client, app):
    """get_card stitches together four sources; a broken join drops one silently."""
    app.repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo"})
    app.repo.set_card_rating("base1-4", 7)

    card = client.get("/api/cards/base1-4").get_json()
    assert card["name"] == "Charizard"
    assert card["rating"] == 7
    assert [i["variant"] for i in card["items"]] == ["holo"]
    assert card["available_printings"][0]["variants"], "variant list must be parsed"
    assert card["market_url"].endswith("base1-4") or "cardmarket.com" in card["market_url"]


def test_collection_rows_carry_a_computed_value(client, app):
    """The value block is assembled in the API layer, not stored."""
    app.repo.upsert_collection_item({"card_id": "base1-4", "condition": "EX",
                                     "language": "en", "quantity": 3})
    app.repo.upsert_price("base1-4", "normal", "cardmarket", "EUR", 100.0,
                          None, None, None, None)

    row = client.get("/api/collection").get_json()["data"][0]
    # 100 * 0.85 (EX) * 1.00 (en) = 85, times 3 copies
    assert row["value"]["unit"] == 85.0
    assert row["value"]["total"] == 255.0


def test_unowned_rows_are_not_valued(client, app):
    """show_all returns placeholders; pricing one would inflate the total."""
    data = client.get("/api/collection?show_all=1").get_json()["data"]
    placeholder = next(r for r in data if not r["owned"])
    assert placeholder["value"]["total"] is None
    assert placeholder["value"]["basis"] == "not_owned"


# ------------------------------------------------------------------ filters
def test_show_all_switches_the_data_source(client, app):
    app.repo.upsert_collection_item({"card_id": "base1-4"})
    owned = client.get("/api/collection").get_json()
    every = client.get("/api/collection?show_all=1").get_json()
    assert owned["mode"] == "owned" and owned["total"] == 1
    assert every["mode"] == "all" and every["total"] == 3, "one row per slot"


def test_rating_filter_includes_cards_you_have_not_acquired(client, app):
    """A rank is a judgement about the card, not about a copy in hand. Ranking a
    card you are still hunting for and then not finding it under the filter was
    the reported bug."""
    app.repo.upsert_collection_item({"card_id": "base1-4"})
    app.repo.set_card_rating("base1-4", 8)
    app.repo.set_card_rating("base1-2", 8)      # ranked but NOT owned

    data = client.get("/api/collection?show_all=1&rating_min=7").get_json()["data"]
    assert {r["card_id"] for r in data} == {"base1-4", "base1-2"}
    assert {r["owned"] for r in data} == {True, False}


def test_hall_of_fame_toggle_selects_anything_ranked(client, app):
    """The toggle sends rating_min=1, since 0 means unranked."""
    app.repo.set_card_rating("base1-2", 3)
    data = client.get("/api/collection?show_all=1&rating_min=1").get_json()["data"]
    assert [r["card_id"] for r in data] == ["base1-2"]


def test_search_narrows_only_the_collection_half(client, app):
    """A rating filter must not silently empty the catalog results."""
    app.repo.upsert_collection_item({"card_id": "base1-4"})
    res = client.get("/api/search?q=Charizard&rating_min=7").get_json()
    assert [c["id"] for c in res["cards"]] == ["base1-4"], "catalog ignores the rank"
    assert res["collection"] == [], "collection half respects it"


# --------------------------------------------------------------- validation
@pytest.mark.parametrize("payload,code", [
    ({"card_id": "base1-4", "rating": 9}, "invalid_rating"),
    ({"card_id": "base1-4", "rating": -1}, "invalid_rating"),
    ({"card_id": "base1-4", "condition": "PERFECT"}, "bad_request"),
    ({"card_id": "base1-4", "variant": "sparkly"}, "bad_request"),
    ({"card_id": "base1-4", "language": "klingon"}, "bad_request"),
    ({"card_id": "base1-4", "quantity": 0}, "bad_request"),
])
def test_invalid_writes_are_rejected_with_a_code(client, payload, code):
    r = client.post("/api/collection", json=payload)
    assert r.status_code >= 400
    assert r.get_json()["error"]["code"] == code


def test_rating_sent_to_the_collection_lands_on_the_card(client, app):
    """Backwards compatibility: the rank moved to the card, but a rating sent
    with a collection write still has to work."""
    client.post("/api/collection", json={"card_id": "base1-4", "rating": 6})
    assert app.repo.get_card_rating("base1-4") == 6


def test_printing_must_match_the_card(client, app):
    """A mismatch would have the collection claim a printing of another card."""
    app.repo.rebuild_printings()
    with app.repo.tx() as c:
        c.execute("""INSERT INTO card_printings
                       (print_group, card_id, official_set_id, is_reprint,
                        display_name, source)
                     VALUES ('base1-4','base1-4','base1',0,'Base','manual')""")
        pid = c.execute("SELECT id FROM card_printings "
                        "WHERE card_id='base1-4'").fetchone()["id"]

    bad = client.post("/api/collection",
                      json={"card_id": "base1-2", "printing_id": pid})
    assert bad.get_json()["error"]["code"] == "invalid_printing"


# ------------------------------------------------------------------ derived
def test_dashboard_totals_are_derived_not_stored(client, app):
    app.repo.upsert_collection_item({"card_id": "base1-4", "quantity": 2})
    app.repo.upsert_collection_item({"card_id": "base1-2", "quantity": 1})
    app.repo.set_card_rating("base1-4", 8)

    d = client.get("/api/dashboard").get_json()
    assert d["unique_cards"] == 2 and d["physical_cards"] == 3
    assert d["owned_cards"] == 2 and d["target_cards"] == 3
    assert d["completion_pct"] == pytest.approx(66.7, abs=0.1)
    # Hall of Fame is a ban-list style ranking; averaging it says nothing, so the
    # dashboard no longer carries a summary of it.
    assert "hall_of_fame" not in d


def test_missing_list_is_the_complement_of_owned(client, app):
    app.repo.upsert_collection_item({"card_id": "base1-4"})
    missing = client.get("/api/sets/mine/missing").get_json()["data"]
    assert {m["card_id"] for m in missing} == {"base1-2", "base1-58"}


def test_rating_labels_are_the_number_only(client):
    """Descriptive labels read as sentiment. Hall of Fame is a power ranking, so
    the scale is the number and nothing else."""
    ratings = client.get("/api/meta").get_json()["ratings"]
    assert ratings[0]["label"] == "—"
    assert [r["label"] for r in ratings[1:]] == [f"★ {n}" for n in range(1, 9)]
    assert not any(c.isalpha() for r in ratings for c in r["label"])


def test_meta_vocabularies_match_the_validator(client):
    """The UI builds its dropdowns from /api/meta; a drift here means the UI can
    offer a value the API rejects."""
    from tombot.config import CONDITIONS, LANGUAGES, VARIANTS
    meta = client.get("/api/meta").get_json()
    assert [c["key"] for c in meta["conditions"]] == CONDITIONS
    assert [l["key"] for l in meta["languages"]] == LANGUAGES
    assert [v["key"] for v in meta["variants"]] == VARIANTS
    assert [r["value"] for r in meta["ratings"]] == list(range(9))
