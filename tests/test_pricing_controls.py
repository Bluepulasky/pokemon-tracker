"""Editing manual prices from the UI, and running maintenance jobs."""
import pytest

from tombot.config import Config
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
    repo.init_db()
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
    est = PricingService(app.repo, Config).estimate_item(item)
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


# -------------------------------------------------- condition multiplier
def test_the_condition_multiplier_scales_the_value(client, app):
    """No source prices by condition, so a played card is the near-mint price
    scaled by an editable factor (PO defaults to 0.35)."""
    from tombot.services.pricing import PricingService
    app.repo.upsert_collection_item({"card_id": "base1-4", "variant": "holo",
                                     "condition": "PO", "quantity": 3}, mode="set")
    app.repo.upsert_price("base1-4", "holo", "cardmarket", "EUR", 100.0,
                          None, None, None, None, variant_key="holo:unlimited")
    svc = PricingService(app.repo, Config)
    item = next(i for i in app.repo.items_by_card("base1-4")
                if i["variant"] == "holo" and i["condition"] == "PO")
    assert svc.estimate_item(item)["unit"] == 35.0           # 100 * 0.35
    assert svc.estimate_item(item)["total"] == 105.0         # x3


def test_first_edition_doubles_the_price_on_every_read_path(client, app):
    """The x2 first-edition factor must show up wherever a price is read, not
    only on a single-item fetch: the card modal (items_by_card) and the Cartas
    grid (list_collection) each carry first_edition into estimate_item."""
    from tombot.services.pricing import PricingService
    app.repo.upsert_price("base1-4", "holo", "cardmarket", "EUR", 100.0,
                          None, None, None, None, variant_key="holo:unlimited")
    svc = PricingService(app.repo, Config)

    item_id = app.repo.items_by_card("base1-4")[0]["id"]
    app.repo.update_collection_item(item_id, {"first_edition": True})   # the edit toggle

    modal = app.repo.items_by_card("base1-4")[0]
    grid = next(i for i in app.repo.list_collection(q="")[0] if i["card_id"] == "base1-4")
    single = app.repo.get_collection_item(modal["id"])
    for row in (modal, grid, single):
        assert row["first_edition"] == 1
        assert svc.estimate_item(row)["unit"] == 200.0
        assert svc.estimate_item(row)["first_edition_multiplier"] == 2.0


def test_the_condition_multiplier_is_editable(client, app):
    assert app.repo.get_modifiers()["condition"]["EX"] == 0.85
    assert client.put("/api/prices/modifiers/condition/EX",
                      json={"multiplier": 0.9}).status_code == 200
    assert app.repo.get_modifiers()["condition"]["EX"] == 0.9


@pytest.mark.parametrize("payload", [{"multiplier": "x"}, {"multiplier": 0}, {"multiplier": -1}])
def test_bad_multipliers_are_rejected(client, payload):
    r = client.put("/api/prices/modifiers/condition/EX", json=payload)
    assert r.status_code >= 400 and r.get_json()["error"]["code"] == "invalid_modifier"


def test_only_condition_multipliers_are_editable(client):
    """Language and variant are priced per-product; those kinds are refused."""
    assert client.put("/api/prices/modifiers/variant/first_edition",
                      json={"multiplier": 2}).get_json()["error"]["code"] == "invalid_modifier"
    assert client.put("/api/prices/modifiers/condition/NM",     # retired grade
                      json={"multiplier": 1}).status_code == 400


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


# ------------------------------------------------- jobs run with an app context

def _await_job(client, timeout=5.0):
    """Poll the status endpoint until the job stops running.

    Bounded and asserted, so a hang fails the test instead of stalling it.
    """
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get("/api/maintenance/status").get_json()
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("job never finished")


def test_background_job_can_reach_app_services(app):
    """A job thread must start inside an application context.

    Regression: the worker resolved `current_app` on its own thread, where it is
    unbound, so both maintenance buttons failed the instant they were pressed
    with "Working outside of application context".
    """
    from flask import current_app

    seen = {}

    def work():
        seen["repo"] = current_app.extensions["repo"]
        return {"ok": True}

    started, _ = app.extensions["jobs"].start("probe", work)
    assert started
    with app.test_client() as client:
        state = _await_job(client)

    assert state["status"] == "done", state["error"]
    assert state["result"] == {"ok": True}
    assert seen["repo"] is app.extensions["repo"]


def test_price_refresh_job_reports_its_outcome(app, client, monkeypatch):
    """The async refresh runs the real service and surfaces what it did."""
    calls = []

    def fake_refresh(*, all_cards=False, stale_days=None):
        # svc() reads current_app: proof the context is live on the thread.
        from flask import current_app
        calls.append((all_cards, current_app.extensions["config"] is not None))
        return {"updated": 3}

    monkeypatch.setattr(app.extensions["pricing"], "refresh", fake_refresh)

    r = client.post("/api/prices/refresh-async")
    assert r.status_code == 202

    state = _await_job(client)
    assert state["status"] == "done", state["error"]
    assert state["result"] == {"updated": 3}
    assert calls == [(True, True)]


def test_only_one_job_runs_at_a_time(app, client):
    """A second press while one is in flight is refused, not queued."""
    import threading

    release = threading.Event()
    app.extensions["jobs"].start("slow", lambda: release.wait(timeout=5))
    try:
        r = client.post("/api/prices/refresh-async")
        assert r.status_code == 409
        assert r.get_json()["started"] is False
        assert r.get_json()["name"] == "slow"
    finally:
        release.set()
    _await_job(client)


def _spy_on_close(repo):
    """Record every repo.close(), with the thread and whether it had work to do."""
    calls = []
    original = repo.close

    def spy():
        import threading
        calls.append({
            "thread": threading.current_thread().name,
            "had_connection": getattr(repo._local, "conn", None) is not None,
        })
        original()

    repo.close = spy
    return calls


def test_job_thread_releases_its_connection(app, client):
    """Each job thread opens its own SQLite connection; it must not keep it.

    Connections are thread-local, so without this the WAL read mark of every
    maintenance run stays open until the process restarts.
    """
    repo = app.extensions["repo"]
    closes = _spy_on_close(repo)

    app.extensions["jobs"].start("probe", lambda: repo.get_card("base1-4") and "worked")
    state = _await_job(client)
    assert state["status"] == "done", state["error"]

    assert [c["thread"] for c in closes] == ["job-probe"]
    assert closes[0]["had_connection"] is True     # it really had one to release


def test_failing_job_still_releases_its_connection(app, client):
    """The cleanup sits in a finally: a crashed rebuild must not leak either."""
    repo = app.extensions["repo"]
    closes = _spy_on_close(repo)

    def work():
        repo.get_card("base1-4")
        raise RuntimeError("upstream died")

    app.extensions["jobs"].start("probe", work)
    state = _await_job(client)

    assert state["status"] == "failed"
    assert "upstream died" in state["error"]
    assert [c["thread"] for c in closes] == ["job-probe"]
    assert closes[0]["had_connection"] is True
