"""One primary photo per item, whatever order or speed the uploads arrive in (#93)."""
import os
import sqlite3
import tempfile
import threading

import pytest

from tombot.services.repository import PokemonRepo


def _new_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def _seed(repo):
    repo.upsert_official_set({"id": "bs", "name": "Base", "series": "Base", "printed_total": 1,
                              "total": 1, "release_date": "1999/01/09", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "bs-4", "official_set_id": "bs", "name": "Charizard", "number": "4"}])
    return repo.upsert_collection_item({"card_id": "bs-4", "variant": "holo", "condition": "M/NM",
                                     "language": "en", "quantity": 1})["id"]


def _photo(name):
    return {"filename": f"collection/{name}", "thumb_filename": f"thumbs/{name}",
            "width": 1, "height": 1, "bytes": 1}


def _primaries(path, item_id):
    with sqlite3.connect(path) as c:
        return c.execute("SELECT id, is_primary, position FROM collection_photos "
                         "WHERE item_id=? ORDER BY id", (item_id,)).fetchall()


@pytest.fixture()
def db():
    path = _new_db()
    yield path
    os.unlink(path)


def test_first_photo_is_primary_and_the_rest_are_not(db):
    repo = PokemonRepo(db)
    repo.init_db()
    item = _seed(repo)
    first = repo.add_photo(item, _photo("a.jpg"))
    second = repo.add_photo(item, _photo("b.jpg"))
    assert (first["is_primary"], first["position"]) == (1, 0)
    assert (second["is_primary"], second["position"]) == (0, 1)


def test_simultaneous_uploads_leave_exactly_one_primary(db):
    """Eight threads upload at once, released together by a barrier — the
    read-then-insert version of add_photo made every one of them primary."""
    repo = PokemonRepo(db)
    repo.init_db()
    item = _seed(repo)
    n = 8
    barrier = threading.Barrier(n)
    errors = []

    def upload(i):
        try:
            barrier.wait()
            repo.add_photo(item, _photo(f"{i}.jpg"))
        except Exception as e:                       # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=upload, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    rows = _primaries(db, item)
    assert len(rows) == n
    assert sum(flag for _, flag, _ in rows) == 1
    assert sorted(pos for _, _, pos in rows) == list(range(n))


def test_a_second_primary_cannot_be_written_at_all(db):
    repo = PokemonRepo(db)
    repo.init_db()
    item = _seed(repo)
    repo.add_photo(item, _photo("a.jpg"))
    with sqlite3.connect(db) as c, pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO collection_photos (item_id, filename, is_primary, position) "
                  "VALUES (?, 'x.jpg', 1, 5)", (item,))


def test_init_db_heals_a_database_that_already_has_duplicates(db):
    """A database from before the fix: three photos on one item, all primary,
    and another item whose photos have none. Startup fixes both."""
    repo = PokemonRepo(db)
    repo.init_db()
    item = _seed(repo)
    other = repo.upsert_collection_item({"card_id": "bs-4", "variant": "holo", "condition": "EX",
                                      "language": "en", "quantity": 1})["id"]
    with sqlite3.connect(db) as c:
        c.execute("DROP INDEX idx_photos_one_primary")
        for i in range(3):
            c.execute("INSERT INTO collection_photos (item_id, filename, is_primary, position) "
                      "VALUES (?, ?, 1, ?)", (item, f"{i}.jpg", i))
        c.execute("INSERT INTO collection_photos (item_id, filename, is_primary, position) "
                  "VALUES (?, 'none.jpg', 0, 0)", (other,))

    PokemonRepo(db).init_db()

    assert [flag for _, flag, _ in _primaries(db, item)] == [1, 0, 0]
    assert [flag for _, flag, _ in _primaries(db, other)] == [1]
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT 1 FROM sqlite_master WHERE name='idx_photos_one_primary'").fetchone()
