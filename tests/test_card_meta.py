"""CSV-driven card-metadata fixes (fill blank artist/supertype).

Older imports never stored the illustrator or supertype, so cards from them have
those blank. A CSV keyed by card_id fills the gaps — only blanks, never
overwriting — and the app ships a pre-baked file so an install can self-heal.
"""
import pytest

from tombot.config import Config
from tombot.services import card_meta
from tombot.services.repository import PokemonRepo


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
    r.upsert_official_set({"id": "bs", "name": "Base Set", "series": "Base",
                           "printed_total": 2, "total": 2, "release_date": "1999/01/09",
                           "ptcgo_code": "BS", "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        {"id": "bs-2", "official_set_id": "bs", "name": "Blastoise", "number": "2"},
        {"id": "bs-4", "official_set_id": "bs", "name": "Charizard", "number": "4",
         "artist": "Mitsuhiro Arita"},          # already has an artist
    ])
    return r


# ------------------------------------------------------------------- parsing
def test_parse_reads_id_and_fixable_columns():
    rows, errors = card_meta.parse_csv(
        "card_id,name,artist,supertype\nbs-2,Blastoise,Ken Sugimori,Pokémon\n")
    assert not errors
    assert rows == [{"card_id": "bs-2", "line": 2,
                     "artist": "Ken Sugimori", "supertype": "Pokémon"}]


def test_parse_tolerates_bom_and_semicolons():
    rows, errors = card_meta.parse_csv("﻿card_id;artist\nbs-2;Ken Sugimori\n")
    assert not errors and rows[0]["artist"] == "Ken Sugimori"


def test_parse_requires_card_id_column():
    _, errors = card_meta.parse_csv("name,artist\nBlastoise,Ken\n")
    assert errors and "card_id" in errors[0]["error"]


def test_parse_requires_a_fixable_column():
    _, errors = card_meta.parse_csv("card_id,name\nbs-2,Blastoise\n")
    assert errors and "corregir" in errors[0]["error"]


# -------------------------------------------------------------------- apply
def test_apply_fills_blank_but_never_overwrites(repo):
    rows, _ = card_meta.parse_csv(
        "card_id,artist,supertype\n"
        "bs-2,Ken Sugimori,Pokémon\n"        # blank -> filled
        "bs-4,SOMEONE ELSE,Pokémon\n"        # already set -> artist kept, supertype filled
        "zz-9,Nobody,Pokémon\n")             # unknown -> reported
    result = card_meta.apply_fixes(repo, rows)

    assert repo.get_card("bs-2")["artist"] == "Ken Sugimori"
    assert repo.get_card("bs-4")["artist"] == "Mitsuhiro Arita"   # NOT overwritten
    assert repo.get_card("bs-2")["supertype"] == "Pokémon"
    assert result["changed"]["artist"] == 1                       # only bs-2
    assert result["changed"]["supertype"] == 2                    # bs-2 and bs-4
    assert [m["card_id"] for m in result["missing"]] == ["zz-9"]


def test_apply_is_idempotent(repo):
    rows, _ = card_meta.parse_csv("card_id,artist\nbs-2,Ken Sugimori\n")
    card_meta.apply_fixes(repo, rows)
    again = card_meta.apply_fixes(repo, rows)
    assert again["changed"]["artist"] == 0       # nothing left blank


def test_overwrite_replaces_an_existing_value(repo):
    """With overwrite, a CSV value corrects a wrong one it would otherwise skip."""
    rows, _ = card_meta.parse_csv("card_id,artist\nbs-4,Corrected Name\n")
    result = card_meta.apply_fixes(repo, rows, overwrite=True)
    assert repo.get_card("bs-4")["artist"] == "Corrected Name"
    assert result["changed"]["artist"] == 1 and result["overwrite"] is True


def test_overwrite_counts_only_real_changes(repo):
    """Overwriting with the value already there is a no-op, reported as 0."""
    rows, _ = card_meta.parse_csv("card_id,artist\nbs-4,Mitsuhiro Arita\n")
    result = card_meta.apply_fixes(repo, rows, overwrite=True)
    assert result["changed"]["artist"] == 0


# ------------------------------------------------------------------ bundled
def test_meta_export_query_runs(repo):
    """`set` is a SQL keyword: the export query must quote it, or it 500s
    (regression — this crashed 'Descargar CSV actual')."""
    rows = repo.cards_meta_rows()
    assert rows and set(rows[0]) >= {"card_id", "name", "set", "supertype", "artist"}
    assert any(r["card_id"] == "bs-4" for r in rows)


def test_the_bundled_fix_file_exists_and_parses():
    text = card_meta.bundled_text()
    assert text is not None
    rows, errors = card_meta.parse_csv(text)
    assert not errors and len(rows) > 100
    assert any(r["card_id"] == "bs-2" and r.get("artist") for r in rows)
