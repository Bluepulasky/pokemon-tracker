"""How Flask hands out the built React app."""
import pytest

from tombot import create_app
from tombot.config import Config


def _app(tmp_path, dist):
    class TestConfig(Config):
        DATA_DIR = tmp_path / "data"
        MEDIA_DIR = tmp_path / "media"
        DB_PATH = tmp_path / "data" / "test.db"
        CATALOG_IMG_DIR = MEDIA_DIR / "catalog"
        COLLECTION_IMG_DIR = MEDIA_DIR / "collection"
        THUMB_DIR = MEDIA_DIR / "thumbs"
        FRONTEND_DIST = dist

    return create_app(TestConfig).test_client()


def test_missing_build_says_how_to_build_it(tmp_path):
    res = _app(tmp_path, tmp_path / "no-such-dist").get("/")
    assert res.status_code == 503
    assert "make frontend" in res.get_data(as_text=True)


@pytest.fixture()
def built(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    return _app(tmp_path, dist)


def test_index_is_never_cached_so_a_new_build_is_picked_up(built):
    res = built.get("/")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-cache"


def test_build_output_is_served_under_static(built):
    assert built.get("/static/assets/app-abc123.js").get_data(as_text=True) == "console.log(1)"


def test_unknown_page_falls_back_to_the_app_but_unknown_api_stays_json(built):
    assert "id=root" in built.get("/some/deep/link").get_data(as_text=True)
    res = built.get("/api/nope")
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "not_found"
