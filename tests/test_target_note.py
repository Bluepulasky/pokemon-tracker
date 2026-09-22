"""A free-text note on a card's target: which printing to chase, etc. (#94)."""
import sqlite3

import pytest

from tombot.config import Config
from tombot.services import bulk
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "n.db")
    r.init_db()
    r.upsert_official_set({"id": "bs", "name": "Base", "series": "Base", "printed_total": 2,
                           "total": 2, "release_date": "1999/01/09", "ptcgo_code": None,
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "bs-2", "official_set_id": "bs", "name": "Blastoise", "number": "2"},
        {"id": "bs-4", "official_set_id": "bs", "name": "Charizard", "number": "4"},
    ])
    r.upsert_collection_set({"id": "base", "name": "Base"})
    r.replace_rule_slots("base", [
        {"position": 0, "label": "Blastoise", "cards": ["bs-2"], "display_card_id": "bs-2"},
        {"position": 1, "label": "Charizard", "cards": ["bs-4"], "display_card_id": "bs-4"},
    ])
    return r


@pytest.fixture()
def client(tmp_path, monkeypatch, repo):
    for attr, value in (("DB_PATH", tmp_path / "n.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"), ("CATALOG_IMG_DIR", tmp_path / "m/c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m/i"), ("THUMB_DIR", tmp_path / "m/t")):
        monkeypatch.setattr(Config, attr, value)
    from tombot import create_app
    app = create_app(Config)
    app.config["TESTING"] = True
    return app.test_client()


# ------------------------------------------------------------------ storage

def test_note_and_target_are_kept_independently(repo):
    repo.set_card_target("bs-2", 2)
    repo.set_card_target("bs-2", note="buscar de Celebrations")
    assert repo.get_card_target_row("bs-2") == {"target": 2, "note": "buscar de Celebrations"}
    repo.set_card_target("bs-2", 3)
    assert repo.get_card_target_row("bs-2") == {"target": 3, "note": "buscar de Celebrations"}


def test_a_note_alone_keeps_a_row_with_the_default_target(repo):
    repo.set_card_target("bs-4", note="first edition preferido")
    assert repo.get_card_target_row("bs-4") == {"target": 1, "note": "first edition preferido"}


def test_clearing_both_removes_the_row(repo):
    repo.set_card_target("bs-4", 2, "x")
    repo.set_card_target("bs-4", 1, "  ")
    assert repo.get_card_target_row("bs-4") == {"target": 1, "note": None}
    with sqlite3.connect(repo.db_path) as c:
        assert c.execute("SELECT COUNT(*) FROM card_targets").fetchone()[0] == 0


def test_an_existing_database_gains_the_column_on_init(repo):
    """A card_targets created before the column exists gets it on the next start,
    keeping its rows — schema.sql alone cannot add a column to an existing table."""
    repo.set_card_target("bs-2", 2)
    with sqlite3.connect(repo.db_path) as c:
        c.execute("ALTER TABLE card_targets DROP COLUMN note")
    PokemonRepo(repo.db_path).init_db()
    assert repo.get_card_target_row("bs-2") == {"target": 2, "note": None}


# ---------------------------------------------------------------------- api

def test_put_target_accepts_either_field_alone(client):
    assert client.put("/api/cards/bs-2/target", json={"target": 2}).get_json() == {
        "card_id": "bs-2", "target": 2, "note": None}
    assert client.put("/api/cards/bs-2/target", json={"note": " buscar de Celebrations "}
                      ).get_json() == {"card_id": "bs-2", "target": 2,
                                       "note": "buscar de Celebrations"}
    assert client.get("/api/cards/bs-2").get_json()["note"] == "buscar de Celebrations"
    assert client.put("/api/cards/bs-2/target", json={}).status_code == 400
    assert client.put("/api/cards/bs-2/target", json={"note": "x" * 201}).status_code == 400


def test_missing_rows_carry_the_note_only_when_there_is_one(client, repo):
    repo.set_card_target("bs-2", 2, "buscar de Celebrations")
    rows = {r["card_id"]: r for r in client.get("/api/sets/base/missing").get_json()["data"]}
    assert rows["bs-2"]["note"] == "buscar de Celebrations"
    assert rows["bs-4"]["note"] is None


# ---------------------------------------------------------------------- csv

def test_export_carries_the_note_and_the_import_reads_it_back(client, repo):
    repo.set_card_target("bs-2", 2, "buscar de Celebrations")
    text = client.get("/api/maintenance/targets/export").get_data(as_text=True)
    assert text.splitlines()[0].lstrip("﻿") == "card_id;card_name;target_quantity;note"
    rows, errors = bulk.parse_csv(text)
    assert errors == []
    assert {r["card_id"]: r["note"] for r in rows} == {"bs-2": "buscar de Celebrations",
                                                        "bs-4": ""}


def test_a_blank_or_absent_note_cell_leaves_the_note_alone(repo):
    repo.set_card_target("bs-2", 2, "keep me")
    rows, _ = bulk.parse_csv("card_id;target_quantity;note\nbs-2;2;\n")
    assert bulk.apply_targets(repo, rows)["unchanged"] == ["bs-2"]
    rows, _ = bulk.parse_csv("card_id;target_quantity\nbs-2;3\n")
    result = bulk.apply_targets(repo, rows)
    assert result["updated"] == [{"card_id": "bs-2", "from": 2, "to": 3}]
    assert repo.get_card_target_row("bs-2")["note"] == "keep me"


def test_a_note_change_counts_as_an_update_and_is_reported(repo):
    rows, _ = bulk.parse_csv("card_id;target_quantity;nota\nbs-4;1;first edition preferido\n")
    result = bulk.apply_targets(repo, rows)
    assert result["updated"] == [{"card_id": "bs-4", "from": 1, "to": 1,
                                  "note": "first edition preferido"}]
    assert repo.get_card_target_row("bs-4") == {"target": 1, "note": "first edition preferido"}
