"""Editing prices and multipliers from the UI, and running maintenance jobs."""
import pytest

from tombot.config import DEFAULT_MODIFIERS, Config
from tombot.services.jobs import JobRunner
from tombot.services.repository import PokemonRepo


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "c.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "catalog"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "collection"),
                        ("THUMB_DIR", tmp_path / "m" / "thumbs")):
        monkeypatch.setattr(Config, attr, value)

    repo = PokemonRepo(Config.DB_PATH)
    repo.init_db(DEFAULT_MODIFIERS)
    repo.upsert_official_set({"id": "base1", "name": "Base", "series": "Base",
                              "printed_total": 1, "total": 1,
                              "release_date": "1999/01/09", "ptcgo_code": None,
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "base1-4", "official_set_id": "base1",
                        "name": "Charizard", "number": "4"}])
    repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo"})

    from tombot import create_app
    a = create_app(Config)
    a.config["TESTING"] = True
    a.repo = repo
    return a


@pytest.fixture()
def client(app):
    return app.test_client()


# --------------------------------------------------------------- manual price
def test_a_typed_price_takes_effect_and_is_marked_as_manual(client, app):
    """The feed has real gaps — every WOTC promo comes back unpriced — so a typed
    price has to be usable and distinguishable from a fetched one."""
    r = client.put("/api/prices/manual/base1-4/holo", json={"price": 12.5})
    assert r.status_code == 200

    item = app.repo.items_by_card("base1-4")[0]
    from tombot.services.pricing import PricingService
    est = PricingService(app.repo, None, Config).estimate_item(item, app.repo.get_modifiers())
    assert est["unit"] == 12.5 and est["manual"] is True


def test_clearing_a_typed_price_returns_the_printing_to_the_feed(client, app):
    client.put("/api/prices/manual/base1-4/holo", json={"price": 12.5})
    app.repo.upsert_price("base1-4", "holo", "cardmarket", "EUR", 99.0,
                          None, None, None, None, variant_key="holo:unlimited")

    client.put("/api/prices/manual/base1-4/holo", json={"price": None})
    assert app.repo.get_price("base1-4", "holo")["price"] == 99.0


@pytest.mark.parametrize("payload,code", [
    ({"price": "abc"}, "invalid_price"),
    ({"price": -5}, "invalid_price"),
])
def test_bad_prices_are_rejected(client, payload, code):
    r = client.put("/api/prices/manual/base1-4/holo", json=payload)
    assert r.status_code >= 400 and r.get_json()["error"]["code"] == code


def test_an_unknown_variant_is_rejected(client):
    r = client.put("/api/prices/manual/base1-4/sparkly", json={"price": 1})
    assert r.status_code == 400


# ----------------------------------------------------------------- multiplier
def test_the_first_edition_premium_is_editable(client, app):
    """No source prices a 1st edition apart from its unstamped twin, and one
    figure cannot be right for a Charizard and a common at once."""
    assert app.repo.get_modifiers()["variant"]["first_edition"] == 2.0

    assert client.put("/api/prices/modifiers/variant/first_edition",
                      json={"multiplier": 3.5}).status_code == 200
    assert app.repo.get_modifiers()["variant"]["first_edition"] == 3.5


def test_the_edited_multiplier_changes_the_estimate(client, app):
    app.repo.upsert_collection_item({"card_id": "base1-4", "variant": "first_edition"})
    app.repo.upsert_price("base1-4", "first_edition", "cardmarket", "EUR", 100.0,
                          None, None, None, None, variant_key="holo:shadowless:1st-edition")
    from tombot.services.pricing import PricingService
    svc = PricingService(app.repo, None, Config)

    item = next(i for i in app.repo.items_by_card("base1-4")
                if i["variant"] == "first_edition")
    assert svc.estimate_item(item, app.repo.get_modifiers())["unit"] == 200.0

    client.put("/api/prices/modifiers/variant/first_edition", json={"multiplier": 1.5})
    assert svc.estimate_item(item, app.repo.get_modifiers())["unit"] == 150.0


@pytest.mark.parametrize("payload", [{"multiplier": "x"}, {"multiplier": 0}, {"multiplier": -1}])
def test_bad_multipliers_are_rejected(client, payload):
    r = client.put("/api/prices/modifiers/variant/first_edition", json=payload)
    assert r.status_code >= 400 and r.get_json()["error"]["code"] == "invalid_modifier"


def test_an_unknown_modifier_kind_is_rejected(client):
    r = client.put("/api/prices/modifiers/nonsense/x", json={"multiplier": 2})
    assert r.get_json()["error"]["code"] == "invalid_modifier"


# ----------------------------------------------------------------------- jobs
def test_a_job_reports_its_result():
    runner = JobRunner()
    done = []
    started, _ = runner.start("t", lambda: done.append(1) or {"n": 1})
    assert started
    for _ in range(200):
        if runner.status()["status"] != "running":
            break
        import time
        time.sleep(0.01)
    assert runner.status()["status"] == "done"
    assert runner.status()["result"] == {"n": 1}


def test_a_failing_job_records_why_instead_of_hanging():
    """A job stuck on "running" forever is indistinguishable from a slow one."""
    import time

    runner = JobRunner()
    runner.start("boom", lambda: (_ for _ in ()).throw(RuntimeError("upstream died")))
    for _ in range(200):
        if runner.status()["status"] != "running":
            break
        time.sleep(0.01)
    assert runner.status()["status"] == "failed"
    assert "upstream died" in runner.status()["error"]


def test_only_one_job_runs_at_a_time():
    """Two concurrent catalog rebuilds would race on the same rows for no gain."""
    import threading

    runner = JobRunner()
    release = threading.Event()
    runner.start("first", lambda: release.wait(timeout=5) or {"ok": True})

    started, state = runner.start("second", lambda: {"ok": True})
    assert started is False
    assert state["name"] == "first"
    release.set()


def test_the_maintenance_endpoints_are_reachable(client):
    assert client.get("/api/maintenance/status").get_json()["status"] == "idle"
