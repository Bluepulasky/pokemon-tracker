"""The Faltantes view must read the same "any version counts" flag as the rest (#82).

Tom's case, exactly: Fossil has loose completion on, he owns the holo Muk FO-13,
and the goal collects the non-holo Muk FO-28 with a target of two copies. The
Cartas grid and the Sets progress bar both counted the holo. The Faltantes list
did not, so one screen said the card was in hand and the other said he had none.

Everything that asks "how many copies of this slot do I hold?" is tested here
together, because the bug was not a wrong answer — it was four answers.
"""
import json

import pytest

from tombot.config import Config
from tombot.services.repository import PokemonRepo

HIMENO = "Kagemaru Himeno"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "m.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    r = PokemonRepo(Config.DB_PATH)
    r.init_db()
    r.upsert_official_set({"id": "fo", "name": "Fossil", "series": "Base",
                           "printed_total": 3, "total": 3, "release_date": "1999/10/10",
                           "ptcgo_code": "FO", "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        # The same Muk twice: the holo print and the plain one, one illustrator.
        {"id": "fo-13", "official_set_id": "fo", "name": "Muk", "number": "13",
         "rarity": "Rare Holo", "artist": HIMENO},
        {"id": "fo-28", "official_set_id": "fo", "name": "Muk", "number": "28",
         "rarity": "Rare", "artist": HIMENO},
        # A card with no other printing at all, to keep an honest missing row.
        {"id": "fo-40", "official_set_id": "fo", "name": "Ditto", "number": "40",
         "rarity": "Rare", "artist": "Ken Sugimori"},
        # Shares the name and nothing else. It must never fill the Muk slot.
        {"id": "fo-50", "official_set_id": "fo", "name": "Muk", "number": "50",
         "rarity": "Common", "artist": "Mitsuhiro Arita"},
    ])
    # "Sin holos": the holo Muk is in the catalogue but is not a slot, which is
    # how Tom has Fossil set up.
    r.upsert_collection_set({"id": "fo-completo", "name": "Fossil",
                             "rules_json": json.dumps({"include_sets": ["fo"],
                                                       "exclude_rarities": ["Rare Holo"]})})
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.extensions["setbuilder"].build("fo-completo")
    repo = a.extensions["repo"]
    repo.set_card_target("fo-28", 2)         # he wants two Muk
    repo.upsert_collection_item({"card_id": "fo-13", "variant": "holo",
                                 "condition": "GD", "language": "es"})
    return a


def _missing_row(app, card_id="fo-28"):
    rows = {m["card_id"]: m for m in app.extensions["repo"].missing_slots("fo-completo")}
    return rows.get(card_id)


def test_strict_still_ignores_the_other_printing(app):
    """Default behaviour is unchanged: the holo is a different card."""
    row = _missing_row(app)
    assert row["held"] == 0
    assert row["still_needed"] == 2
    assert row["missing_entirely"]


def test_loose_counts_the_other_printing_in_the_missing_view(app):
    """The bug: this said 'faltan 2' while the Cartas grid showed the card owned."""
    app.extensions["repo"].set_loose_completion("fo-completo", True)
    row = _missing_row(app)
    assert row["held"] == 1
    assert row["still_needed"] == 1
    assert not row["missing_entirely"]


def test_a_slot_met_by_another_printing_leaves_the_missing_list(app):
    repo = app.extensions["repo"]
    repo.set_card_target("fo-28", 1)         # one copy is enough
    repo.set_loose_completion("fo-completo", True)
    assert _missing_row(app) is None
    # The card with no other printing is still missing, so the list is not empty
    # for the wrong reason.
    assert _missing_row(app, "fo-40") is not None


def test_a_namesake_by_another_illustrator_does_not_count(app):
    """Two Muk by different artists are two cards, loose or not."""
    repo = app.extensions["repo"]
    repo.set_loose_completion("fo-completo", True)
    # fo-50 shares only the name with fo-28; it is its own slot and stays missing.
    assert _missing_row(app, "fo-50")["held"] == 0


def test_every_view_gives_the_same_answer(app):
    """The regression this file exists for: four screens, one number."""
    repo = app.extensions["repo"]
    repo.set_loose_completion("fo-completo", True)

    progress = repo.set_progress("fo-completo")[0]
    slots = {s["card_id"]: s for s in repo.get_set_slots("fo-completo")}
    missing = repo.missing_slots("fo-completo")
    totals = repo.slots_ownership_totals("fo-completo")
    grid = {c["id"]: c["owned_qty"] for c in repo.set_cards_with_state("fo-completo")}

    # The slot is held everywhere, not just on the Sets page.
    assert slots["fo-28"]["quantity"] == 1
    assert slots["fo-28"]["owned"] == 1
    assert slots["fo-28"]["complete"] == 0        # one of two copies
    assert grid["fo-28"] == 1

    # Headers cannot contradict the list underneath them.
    assert totals["owned_slots"] == progress["owned"] == 1
    assert totals["slots"] == progress["target"] == len(slots)
    assert len(missing) == progress["target"] - progress["complete"]


def test_the_toggle_changes_every_view_at_once(app):
    repo = app.extensions["repo"]
    before = (repo.set_progress("fo-completo")[0]["owned"],
              repo.slots_ownership_totals("fo-completo")["owned_slots"],
              len(repo.missing_slots("fo-completo")))
    repo.set_loose_completion("fo-completo", True)
    after = (repo.set_progress("fo-completo")[0]["owned"],
             repo.slots_ownership_totals("fo-completo")["owned_slots"],
             len(repo.missing_slots("fo-completo")))
    assert before == (0, 0, 3)
    assert after == (1, 1, 3)                 # still short of two copies, but held


def test_the_missing_endpoint_reports_it(app):
    app.extensions["repo"].set_loose_completion("fo-completo", True)
    rows = app.test_client().get("/api/sets/fo-completo/missing").get_json()["data"]
    muk = next(m for m in rows if m["card_id"] == "fo-28")
    assert muk["held"] == 1 and muk["still_needed"] == 1


def test_the_cartas_grid_marks_the_tile_held_by_another_version(app):
    """The header counts the slot, so the tile under it cannot read plain missing.

    It is badged "otra versión" rather than owned: the copy in hand is the holo,
    and calling the plain Muk owned would put the holo's condition and price on
    a card Tom does not have (#76 drew this distinction first).
    """
    repo = app.extensions["repo"]
    rows, _ = repo.list_slots_with_ownership(set_id="fo-completo")
    muk = next(r for r in rows if r["card_id"] == "fo-28")
    assert not muk["owned"] and not muk["reprint_owned"]   # strict: nothing to say

    repo.set_loose_completion("fo-completo", True)
    rows, _ = repo.list_slots_with_ownership(set_id="fo-completo")
    by_id = {r["card_id"]: r for r in rows}
    assert by_id["fo-28"]["reprint_owned"]                 # held, as another print
    assert not by_id["fo-28"]["owned"]                     # but not this printing
    assert not by_id["fo-40"]["reprint_owned"]             # no other printing held
    assert not by_id["fo-50"]["reprint_owned"]             # namesake, other artist


def test_the_grid_and_its_header_agree(app):
    """The count above the grid and the tiles in it come from the same flag."""
    repo = app.extensions["repo"]
    repo.set_loose_completion("fo-completo", True)
    rows, _ = repo.list_slots_with_ownership(set_id="fo-completo")
    counted = repo.slots_ownership_totals("fo-completo")["owned_slots"]
    assert sum(1 for r in rows if r["owned"] or r["reprint_owned"]) == counted
