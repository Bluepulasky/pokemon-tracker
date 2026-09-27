"""A cover photo chosen by hand represents the reprint group in the grid (#99)."""
import sqlite3

import pytest

from tombot.services.repository import PokemonRepo


def _build(tmp_path):
    r = PokemonRepo(tmp_path / "r.db")
    r.init_db()
    for sid, name, rd in [("bs", "Base", "1999/01/09"), ("b2", "Base Set 2", "2000/02/24")]:
        r.upsert_official_set({"id": sid, "name": name, "series": "", "printed_total": 2,
                               "total": 2, "release_date": rd, "ptcgo_code": sid.upper(),
                               "logo_url": None, "symbol_url": None})
    r.upsert_cards([
        # One card, two printings: the same reprint group.
        {"id": "bs-92", "official_set_id": "bs", "name": "Energy Removal", "number": "92",
         "rarity": "Common", "artist": "Keiji Kinebuchi"},
        {"id": "b2-117", "official_set_id": "b2", "name": "Energy Removal", "number": "117",
         "rarity": "Common", "artist": "Keiji Kinebuchi"},
        # Another card entirely.
        {"id": "bs-4", "official_set_id": "bs", "name": "Charizard", "number": "4",
         "rarity": "Rare Holo", "artist": "Mitsuhiro Arita"},
    ])
    return r


@pytest.fixture()
def repo(tmp_path):
    return _build(tmp_path)


def _own(repo, card_id, condition):
    return repo.upsert_collection_item({"card_id": card_id, "condition": condition})


def _photo(repo, item, name):
    return repo.add_photo(item["id"], {"filename": name, "thumb_filename": name,
                                       "width": 1, "height": 1, "bytes": 1})


def _tile(repo, name="Energy Removal"):
    rows, _ = repo.list_collection()
    return next(r for r in rows if r["name"] == name)


def test_without_a_cover_the_best_copy_still_wins(repo):
    b1, b2 = _own(repo, "bs-92", "EX"), _own(repo, "b2-117", "M/NM")
    _photo(repo, b1, "base1.jpg")
    _photo(repo, b2, "base2.jpg")
    assert _tile(repo)["display_photo"]["filename"] == "base2.jpg"


def test_a_cover_beats_the_best_condition(repo):
    """The issue's case: Base Set 2 is the nicer copy, but you want the tile to
    show the Base Set one."""
    b1, b2 = _own(repo, "bs-92", "EX"), _own(repo, "b2-117", "M/NM")
    base1 = _photo(repo, b1, "base1.jpg")
    _photo(repo, b2, "base2.jpg")

    repo.set_cover_photo(base1["id"])

    assert _tile(repo)["display_photo"]["filename"] == "base1.jpg"
    assert _tile(repo)["card_id"] == "b2-117", "the tile is still represented by the best copy"
    assert repo.best_photos_for_cards(["bs-92"])["bs-92"]["filename"] == "base1.jpg"


def test_a_cover_beats_the_primary_within_an_item(repo):
    item = _own(repo, "bs-92", "M/NM")
    _photo(repo, item, "first.jpg")            # primary, by being first
    second = _photo(repo, item, "second.jpg")
    repo.set_cover_photo(second["id"])

    assert _tile(repo)["display_photo"]["filename"] == "second.jpg"
    assert repo.best_photos_for_cards(["bs-92"])["bs-92"]["filename"] == "second.jpg"
    strip = repo.get_photos(item["id"])
    assert [p["is_primary"] for p in strip] == [1, 0], "primary is untouched"
    assert [p["is_cover"] for p in strip] == [0, 1]


def test_one_cover_per_reprint_group(repo):
    """Covering the Base Set 2 photo clears the one on the Base Set copy, which
    is another item: the per-item index cannot do this on its own."""
    b1, b2 = _own(repo, "bs-92", "EX"), _own(repo, "b2-117", "M/NM")
    base1, base2 = _photo(repo, b1, "base1.jpg"), _photo(repo, b2, "base2.jpg")

    repo.set_cover_photo(base1["id"])
    repo.set_cover_photo(base2["id"])

    assert repo.get_photo(base1["id"])["is_cover"] == 0
    assert repo.get_photo(base2["id"])["is_cover"] == 1
    assert _tile(repo)["display_photo"]["filename"] == "base2.jpg"


def test_a_cover_on_another_card_is_left_alone(repo):
    er, cz = _own(repo, "bs-92", "EX"), _own(repo, "bs-4", "EX")
    er_photo, cz_photo = _photo(repo, er, "er.jpg"), _photo(repo, cz, "cz.jpg")

    repo.set_cover_photo(cz_photo["id"])
    repo.set_cover_photo(er_photo["id"])

    assert repo.get_photo(cz_photo["id"])["is_cover"] == 1


def test_clearing_the_cover_goes_back_to_the_condition_rule(repo):
    b1, b2 = _own(repo, "bs-92", "EX"), _own(repo, "b2-117", "M/NM")
    base1 = _photo(repo, b1, "base1.jpg")
    _photo(repo, b2, "base2.jpg")
    repo.set_cover_photo(base1["id"])
    repo.set_cover_photo(base1["id"], on=False)

    assert repo.get_photo(base1["id"])["is_cover"] == 0
    assert _tile(repo)["display_photo"]["filename"] == "base2.jpg"


def test_setting_a_cover_on_a_missing_photo_is_a_no_op(repo):
    repo.set_cover_photo(9999)


def test_init_db_adds_the_column_to_an_older_database(tmp_path):
    """A database from before is_cover has the table but not the column. init_db
    must add it before schema.sql creates the partial index on it, or CREATE
    INDEX fails with "no such column"."""
    repo = _build(tmp_path)
    item = _own(repo, "bs-92", "EX")
    photo = _photo(repo, item, "old.jpg")
    with sqlite3.connect(tmp_path / "r.db") as c:
        c.execute("DROP INDEX idx_photos_one_cover")
        c.execute("ALTER TABLE collection_photos DROP COLUMN is_cover")
        assert "is_cover" not in {r[1] for r in c.execute("PRAGMA table_info(collection_photos)")}

    repo.init_db()

    with sqlite3.connect(tmp_path / "r.db") as c:
        assert "is_cover" in {r[1] for r in c.execute("PRAGMA table_info(collection_photos)")}
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='idx_photos_one_cover'").fetchone()
    assert repo.get_photo(photo["id"])["is_cover"] == 0
    repo.set_cover_photo(photo["id"])
    assert repo.get_photo(photo["id"])["is_cover"] == 1


# ------------------------------------------------------------------ the API
@pytest.fixture()
def client(tmp_path, monkeypatch):
    from tombot.config import Config
    for attr, value in (("DB_PATH", tmp_path / "r.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "catalog"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "collection"),
                        ("THUMB_DIR", tmp_path / "m" / "thumbs")):
        monkeypatch.setattr(Config, attr, value)
    repo = _build(tmp_path)
    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.repo = repo
    return a.test_client(), repo


def test_put_is_cover_sets_and_clears(client):
    c, repo = client
    b1, b2 = _own(repo, "bs-92", "EX"), _own(repo, "b2-117", "M/NM")
    base1 = _photo(repo, b1, "base1.jpg")
    _photo(repo, b2, "base2.jpg")

    r = c.put(f"/api/collection/photos/{base1['id']}", json={"is_cover": True})
    assert r.status_code == 200 and r.get_json()["is_cover"] == 1
    assert _tile(repo)["display_photo"]["filename"] == "base1.jpg"

    r = c.put(f"/api/collection/photos/{base1['id']}", json={"is_cover": False})
    assert r.get_json()["is_cover"] == 0
    assert _tile(repo)["display_photo"]["filename"] == "base2.jpg"


def test_put_without_is_cover_leaves_it_alone(client):
    c, repo = client
    item = _own(repo, "bs-92", "EX")
    first = _photo(repo, item, "first.jpg")
    second = _photo(repo, item, "second.jpg")
    repo.set_cover_photo(first["id"])

    c.put(f"/api/collection/photos/{second['id']}", json={"is_primary": True})

    assert repo.get_photo(first["id"])["is_cover"] == 1


def test_put_on_a_missing_photo_is_404(client):
    c, _ = client
    assert c.put("/api/collection/photos/9999", json={"is_cover": True}).status_code == 404
