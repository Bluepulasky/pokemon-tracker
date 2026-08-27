"""Bulk target quantities from a CSV (issue #23).

The parser is forgiving about what a spreadsheet emits and strict about what it
means, so most of these are about the shapes Excel actually produces.
"""
import io

import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services import bulk
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "b.db")
    r.init_db(DEFAULT_MODIFIERS)
    r.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                           "printed_total": 102, "total": 102,
                           "release_date": "1999/01/09", "ptcgo_code": None,
                           "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "base1-4", "official_set_id": "base1", "name": "Charizard", "number": "4"},
        {"id": "base1-7", "official_set_id": "base1", "name": "Hitmonchan", "number": "7"},
    ])
    r.upsert_collection_set({"id": "mine", "name": "Mi Base Set"})
    r.replace_rule_slots("mine", [
        {"position": 0, "label": "Charizard", "cards": ["base1-4"],
         "display_card_id": "base1-4"},
        {"position": 1, "label": "Hitmonchan", "cards": ["base1-7"],
         "display_card_id": "base1-7"},
    ])
    return r


@pytest.fixture()
def app(tmp_path, monkeypatch, repo):
    for attr, value in (("DB_PATH", tmp_path / "b.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    return a


# ------------------------------------------------------------------ parsing

def test_excel_in_a_spanish_locale_parses():
    """Semicolons and a UTF-8 BOM are what Excel writes here, not user error."""
    text = "﻿card_id;card_name;target_quantity\r\nbase1-4;Charizard;3\r\n"
    rows, errors = bulk.parse_csv(text)
    assert errors == []
    assert rows == [{"card_id": "base1-4", "target": 3,
                     "name": "Charizard", "line": 2}]


def test_the_column_name_from_the_issue_and_the_one_the_app_uses_both_work():
    for header in ("card_id,target_quantity", "card_id,target"):
        rows, errors = bulk.parse_csv(f"{header}\nbase1-4,2\n")
        assert errors == [], header
        assert rows[0]["target"] == 2, header


def test_a_missing_column_names_what_it_found():
    """The message has to say what the file had, or it is a guessing game."""
    rows, errors = bulk.parse_csv("nombre,cantidad\nCharizard,2\n")
    assert rows == []
    assert "card_id" in errors[0]["error"]
    assert "nombre" in errors[0]["error"]


@pytest.mark.parametrize("value,fragment", [
    ("0", "al menos 1"),
    ("-3", "al menos 1"),
    ("abc", "no es un número"),
    ("", "vacío"),
    ("1000", "máximo"),
])
def test_a_bad_quantity_is_rejected_with_its_line(value, fragment):
    rows, errors = bulk.parse_csv(f"card_id,target_quantity\nbase1-4,{value}\n")
    assert rows == []
    assert errors[0]["line"] == 2
    assert fragment in errors[0]["error"]


def test_a_spanish_decimal_comma_is_read_as_the_number_it_is():
    """`3,0` in a semicolon file is one field meaning three, not a parse error.

    Only reachable with `;` separators — under `,` the same text would be two
    fields — which is exactly the combination Excel produces in this locale.
    """
    rows, errors = bulk.parse_csv("card_id;target_quantity\nbase1-4;3,0\n")
    assert errors == []
    assert rows[0]["target"] == 3


def test_two_rows_for_one_card_is_an_error_not_a_race():
    """Silently taking the last one would apply a number the user never chose."""
    rows, errors = bulk.parse_csv(
        "card_id,target_quantity\nbase1-4,2\nbase1-7,1\nbase1-4,5\n")
    assert [r["card_id"] for r in rows] == ["base1-4", "base1-7"]
    assert rows[0]["target"] == 2                  # the first, not the last
    assert len(errors) == 1
    assert errors[0]["line"] == 4
    assert "repetido" in errors[0]["error"]


def test_every_bad_row_is_reported_in_one_pass():
    """Fixing a spreadsheet one error per upload is the tedium being removed."""
    rows, errors = bulk.parse_csv(
        "card_id,target_quantity\nbase1-4,x\n,2\nbase1-7,0\n")
    assert rows == []
    assert [e["line"] for e in errors] == [2, 3, 4]


def test_a_row_with_every_field_empty_is_skipped_not_reported():
    """Excel writes `,` for a row whose contents were cleared, not deleted.

    Truly blank lines never reach the guard — csv drops those itself — so the
    empty delimited row is the case that matters.
    """
    rows, errors = bulk.parse_csv("card_id,target_quantity\nbase1-4,2\n,\n")
    assert len(rows) == 1
    assert errors == []


# ------------------------------------------------------------------ applying

def test_unknown_cards_are_refused_and_the_rest_still_apply(repo):
    rows, _ = bulk.parse_csv(
        "card_id,target_quantity\nbase1-4,3\nbase9-99,2\nbase1-7,4\n")
    result = bulk.apply_targets(repo, rows)

    assert [c["card_id"] for c in result["updated"]] == ["base1-4", "base1-7"]
    assert result["missing"][0]["card_id"] == "base9-99"
    assert repo.get_card_target("base1-4") == 3
    assert repo.get_card_target("base1-7") == 4


def test_reapplying_the_same_file_reports_no_changes(repo):
    """Re-uploading is normal; claiming 2 updates when nothing moved is a lie."""
    rows, _ = bulk.parse_csv("card_id,target_quantity\nbase1-4,3\nbase1-7,4\n")
    bulk.apply_targets(repo, rows)

    again = bulk.apply_targets(repo, rows)
    assert again["updated"] == []
    assert sorted(again["unchanged"]) == ["base1-4", "base1-7"]


def test_the_change_records_what_it_moved_from(repo):
    repo.set_card_target("base1-4", 2)
    rows, _ = bulk.parse_csv("card_id,target_quantity\nbase1-4,5\n")
    result = bulk.apply_targets(repo, rows)
    assert result["updated"] == [{"card_id": "base1-4", "from": 2, "to": 5}]


# ---------------------------------------------------------------- endpoints

def test_upload_applies_and_summarises(app):
    client = app.test_client()
    csv_bytes = "card_id,target_quantity\nbase1-4,3\nbase9-99,1\n".encode()
    r = client.post("/api/maintenance/targets/import",
                    data={"file": (io.BytesIO(csv_bytes), "t.csv")},
                    content_type="multipart/form-data")

    assert r.status_code == 200
    body = r.get_json()
    assert body["updated"] == 1
    assert body["errors"] == 1
    assert body["problems"][0]["card_id"] == "base9-99"
    assert app.extensions["repo"].get_card_target("base1-4") == 3


def test_export_round_trips_through_the_import(app):
    """What the export writes must be something the import accepts."""
    repo = app.extensions["repo"]
    repo.set_card_target("base1-4", 4)
    client = app.test_client()

    exported = client.get("/api/maintenance/targets/export")
    assert exported.status_code == 200
    assert "attachment" in exported.headers["Content-Disposition"]

    text = exported.get_data(as_text=True)
    rows, errors = bulk.parse_csv(text)
    assert errors == []
    assert {r["card_id"]: r["target"] for r in rows}.get("base1-4") == 4


def test_a_windows_encoded_file_does_not_crash_the_upload(app):
    """cp1252 is what Excel writes unless told otherwise; accents must survive."""
    client = app.test_client()
    body = "card_id,card_name,target_quantity\nbase1-4,Pokémon,2\n".encode("cp1252")
    r = client.post("/api/maintenance/targets/import",
                    data={"file": (io.BytesIO(body), "t.csv")},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["updated"] == 1
