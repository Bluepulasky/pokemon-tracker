import json

from flask import Blueprint, Response, current_app, jsonify, request

from . import cfg, page_response, paginate_args, repo, svc
from .. import ApiError
from ..services import bulk
from ..services.market import attach, market_url

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/healthz")
def healthz():
    r = repo()
    from ..version import get_version
    return jsonify({"ok": True, "cards": r.count_cards(),
                    "schema_version": r.get_meta("schema_version"),
                    "version": get_version()})


@bp.get("/meta")
def meta():
    """Vocabularies the UI needs, so the front end never hardcodes them."""
    from ..config import (CONDITIONS, CONDITION_LABELS, LANGUAGES, LANGUAGE_LABELS,
                          RATING_LABELS, VARIANTS, VARIANT_LABELS)
    r = repo()
    return jsonify({
        "conditions": [{"key": k, "label": CONDITION_LABELS[k]} for k in CONDITIONS],
        "languages": [{"key": k, "label": LANGUAGE_LABELS[k]} for k in LANGUAGES],
        "variants": [{"key": k, "label": VARIANT_LABELS[k]} for k in VARIANTS],
        "rarities": r.rarities(),
        "types": r.card_types(),
        "editions": [{"key": "first_edition", "label": "1st Edition"},
                     {"key": "unlimited", "label": "Unlimited"}],
        "ratings": [{"value": v, "label": lbl} for v, lbl in
                    sorted(RATING_LABELS.items())],
        "official_sets": r.list_official_sets(),
        "last_price_refresh": r.get_meta("last_price_refresh"),
        "version": __import__("tombot.version", fromlist=["get_version"]).get_version(),
    })


@bp.get("/cards")
def list_cards():
    page, size = paginate_args()
    rows, total = repo().search_cards(
        q=request.args.get("q", ""),
        official_set=request.args.get("set", ""),
        rarity=request.args.get("rarity", ""),
        page=page, page_size=size,
    )
    return page_response(attach(rows, locale=cfg().CARDMARKET_LOCALE), total, page, size)


@bp.get("/cards/<card_id>")
def get_card(card_id):
    card = repo().get_card(card_id)
    if not card:
        raise ApiError("carta no encontrada", "not_found", 404)
    card["items"] = repo().items_by_card(card_id)
    card["prices"] = repo().get_prices_for_card(card_id)
    card["market_url"] = market_url(card, locale=cfg().CARDMARKET_LOCALE)
    # Empty when the card has no sibling printings, so the UI can skip the
    # edition selector rather than showing a one-option dropdown.
    printings = repo().printings_for_card(card_id)
    # Parse the variant list so the client does not have to, and fall back to the
    # era rules for a card that has no printing row of its own.
    for pr in printings:
        pr["variants"] = json.loads(pr.get("variants_json") or "[]")
    # What print runs this card exists in is a fact we imported, not something
    # to infer from a hardcoded list of set ids. Those ids were pokemontcg.io's
    # ("base1"), so under any other catalogue they match nothing and the app
    # concludes a set had no 1st Edition — while the products sitting in the
    # database say otherwise.
    products = repo().market_products_for_card(card_id)
    card["editions"] = sorted({p["version"] for p in products if p["version"]})

    if not printings:
        from ..services.printing_variants import variants_for
        printings = [{
            "id": None, "card_id": card_id,
            "official_set_id": card["official_set_id"],
            "display_name": card.get("set_name"), "is_reprint": 0,
            "variants": variants_for(
                card["official_set_id"], card.get("rarity"),
                (repo().get_official_set(card["official_set_id"]) or {}).get("release_date")),
            "source": "single",
        }]
    card["available_printings"] = printings
    card["rating"] = repo().get_card_rating(card_id)
    card["target"] = repo().get_card_target(card_id)
    return jsonify(card)


@bp.put("/cards/<card_id>/target")
def set_card_target(card_id):
    """How many copies of this card count as complete.

    Belongs to the card, like the rank: wanting three Charizards is a statement
    about the card, not about any one copy.
    """
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    body = request.get_json(silent=True) or {}
    try:
        target = int(body.get("target"))
    except (TypeError, ValueError):
        raise ApiError("el objetivo debe ser un entero >= 1", "invalid_target") from None
    if target < 1:
        raise ApiError("el objetivo debe ser al menos 1", "invalid_target")
    repo().set_card_target(card_id, target)
    return jsonify({"card_id": card_id, "target": repo().get_card_target(card_id)})


@bp.put("/cards/<card_id>/rating")
def set_card_rating(card_id):
    """Hall of Fame rank for the card itself.

    It lived on the collection row, which meant ranking the holo and the non-holo
    of one card separately — two answers to a question that has one.
    """
    from ..config import MAX_RATING
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    body = request.get_json(silent=True) or {}
    try:
        rating = int(body.get("rating"))
    except (TypeError, ValueError):
        raise ApiError(f"el rating debe ser un entero entre 0 y {MAX_RATING}",
                       "invalid_rating") from None
    if not 0 <= rating <= MAX_RATING:
        raise ApiError(f"el rating debe estar entre 0 y {MAX_RATING}", "invalid_rating")
    repo().set_card_rating(card_id, rating)
    return jsonify({"card_id": card_id, "rating": repo().get_card_rating(card_id)})


@bp.get("/search")
def search():
    """Global search across catalog and collection.

    A rating filter narrows the collection half only — the catalog has no ranks,
    and silently dropping catalog hits when one is set would look like the search
    was broken.
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"cards": [], "collection": []})

    from .collection import _rating_arg
    rating = _rating_arg("rating")
    rating_min = _rating_arg("rating_min")
    rating_max = _rating_arg("rating_max")

    cards, _ = repo().search_cards(q=q, page=1, page_size=25)
    items, _ = repo().list_collection(
        q=q, rating=rating, rating_min=rating_min, rating_max=rating_max,
        page=1, page_size=25)
    return jsonify({"cards": attach(cards, locale=cfg().CARDMARKET_LOCALE),
                    "collection": items})


@bp.post("/maintenance/sync-catalog")
def sync_catalog():
    """Pull tcggo's whole set list into the local cache, once.

    The set search matches tcggo's own names, which disagree with what people
    type (it calls Base Set "Base"), and it only looks past the local cache when
    nothing local matches — so uncached sets stay invisible. Caching every set
    up front makes the search fully local: instant, complete, and free per
    query. It spends about a dozen requests (one per page); importing a set
    still costs its own. Not idempotent in cost — each run re-fetches — so the
    button warns before it runs.
    """
    source = svc("versions_source")
    if source is None or not source.configured:
        raise ApiError("no hay fuente configurada (TCGGO_API_KEY)",
                       "not_configured", 503)
    try:
        episodes = source.list_all_episodes()
    except Exception as e:                                   # noqa: BLE001
        # Includes the budget running out mid-sync: report it, keep what cached.
        raise ApiError(str(e), "source_error", 502) from None
    stored = repo().remember_episodes(episodes)
    return jsonify({"synced": stored})


@bp.get("/maintenance/targets/export")
def export_targets():
    """The current targets as CSV, ready to edit and send back.

    The import needs card ids, and copying 100 of them by hand is the tedium it
    was meant to remove, so the file the user edits comes from here.
    """
    import csv
    import io

    set_id = request.args.get("set_id")
    if set_id:
        if not repo().get_collection_set(set_id):
            raise ApiError("set no encontrado", "not_found", 404)
        slots = repo().get_set_slots(set_id)
    else:
        hidden = {s["id"] for s in repo().list_hidden_sets()}
        slots = [s for cs in repo().list_collection_sets()
                 if cs["id"] not in hidden
                 for s in repo().get_set_slots(cs["id"])]

    buf = io.StringIO()
    # utf-8-sig on the way out: Excel shows accents as mojibake without a BOM.
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["card_id", "card_name", "target_quantity"])
    seen = set()
    for slot in slots:
        card_id = slot.get("card_id")
        if not card_id or card_id in seen:
            continue
        seen.add(card_id)
        writer.writerow([card_id, slot.get("name") or slot.get("label") or "",
                         slot.get("target") or 1])

    name = f"objetivos-{set_id}.csv" if set_id else "objetivos.csv"
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@bp.post("/maintenance/targets/import")
def import_targets():
    """Apply a CSV of target quantities.

    Every problem is reported at once with its line number: a spreadsheet gets
    fixed in one pass, not by resubmitting to discover the next bad row.
    """
    if "file" in request.files:
        raw = request.files["file"].read()
    else:
        raw = request.get_data()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel on Windows still writes cp1252 unless told otherwise.
        text = raw.decode("cp1252", errors="replace")

    rows, errors = bulk.parse_csv(text)
    result = bulk.apply_targets(repo(), rows)
    problems = errors + result["missing"]
    return jsonify({
        "updated": len(result["updated"]),
        "unchanged": len(result["unchanged"]),
        "errors": len(problems),
        "changes": result["updated"][:200],
        "problems": problems[:200],
    })


@bp.get("/maintenance/episodes")
def list_episodes():
    """Sets available to add, with whether they are already imported.

    Answers from what we already know first. Only an explicit search with no
    local match reaches the network, because the set list pages twenty at a
    time and pulling all of it costs about twenty requests to answer a question
    nobody asked.
    """
    q = (request.args.get("q") or "").strip()
    known = repo().search_known_episodes(q or None)

    if q and not known:
        source = svc("versions_source")
        if source is not None and source.configured:
            try:
                found = source.search_episodes(q)
                repo().remember_episodes(found)
                known = repo().search_known_episodes(q)
            except Exception as e:                           # noqa: BLE001
                raise ApiError(str(e), "source_error", 502) from None

    return jsonify({"query": q, "episodes": [{
        "id": e["episode_id"], "code": e["code"], "name": e["name"],
        "released_at": e["released_at"], "logo": e["logo"],
        "cards_total": e["cards_total"],
        "imported": bool(e["products"]), "products": e["products"],
    } for e in known]})


@bp.post("/maintenance/episodes/<int:episode_id>/import")
def import_episode(episode_id):
    """Bring one set in: its products, its cards, and the set itself."""
    from ..services.market_import import MarketImporter
    from ..services.tcggo_catalog import TcggoCatalog

    source = svc("versions_source")
    if source is None or not source.configured:
        raise ApiError("no hay fuente configurada (TCGGO_API_KEY)",
                       "not_configured", 503)

    episode = repo()._one(
        "SELECT * FROM market_episodes WHERE episode_id=?", (episode_id,))
    if not episode:
        raise ApiError("set desconocido; buscalo primero", "not_found", 404)

    budget = (current_app.extensions.get("budgets") or {}).get("tcggo")
    if budget is not None and not budget.can_afford(6):
        raise ApiError(
            f"quedan {budget.remaining()} consultas y un set necesita unas 6. "
            f"Probá de nuevo cuando se libere la cuota.", "budget", 429)

    importer = MarketImporter(repo(), source, budget)
    result = importer.import_episode(episode_id)
    built = TcggoCatalog(repo()).build_set({
        "id": episode_id, "code": episode["code"], "name": episode["name"],
        "released_at": episode["released_at"], "logo": episode["logo"],
        "cards_total": episode["cards_total"],
    })

    # Importing a set adds it to the catalogue; the Sets page lists what you
    # are collecting. Adding one without the other means pressing "Añadir" and
    # seeing nothing happen, so a goal to collect the whole set comes with it.
    # It is a starting point — narrowing it later is what the rules are for.
    goal = _ensure_collection_set(built.get("set_id"), episode["name"])
    return jsonify({**result, **built, "name": episode["name"],
                    "collection_set": goal})


def _ensure_collection_set(set_id: str | None, name: str) -> dict | None:
    """A goal to collect this set, unless one already covers it."""
    if not set_id:
        return None
    import json as _json

    for existing in repo().list_collection_sets():
        rules = _json.loads(existing.get("rules_json") or "{}")
        if set_id in (rules.get("include_sets") or []):
            return {"id": existing["id"], "name": existing["name"],
                    "created": False}

    # No group is assigned here: the Sets view groups by the catalogue set's
    # series and orders by its release date, so an imported set files itself
    # into its era. There is no "added vs seeded" distinction any more.
    goal_id = f"{set_id}-completo"
    repo().upsert_collection_set({
        "id": goal_id, "name": name, "description": f"{name} completo.",
        "rules_json": _json.dumps({"include_sets": [set_id]}),
    })
    slots = svc("setbuilder").build(goal_id)
    return {"id": goal_id, "name": name, "created": True,
            "slots": slots.get("slots") if isinstance(slots, dict) else slots}


@bp.get("/maintenance/hidden-sets")
def maintenance_hidden_sets():
    """Sets hidden from the collection, so they can be shown again from here.

    Hiding lives on the Sets page (its X); showing again lives here, so a hidden
    set never clutters the grid it was hidden from.
    """
    return jsonify({"data": repo().list_hidden_sets()})


@bp.get("/maintenance/health")
def maintenance_health():
    """Look for vocabulary mismatches before they become wrong numbers.

    Every silent-fallback bug this app has had answered plausibly instead of
    failing: a missing multiplier is 1.00, an unknown set id is "modern". These
    checks look for the mismatch itself, so the next rename shows up here
    rather than in a price nobody questions.
    """
    from ..config import CONDITIONS
    from ..services.health import run_checks

    return jsonify(run_checks(repo(), CONDITIONS))


@bp.get("/maintenance/status")
def maintenance_status():
    """Job state, plus what is left of the metered allowance.

    Shown because the number is otherwise invisible until a run stops halfway:
    knowing 62 of 80 remain is what lets someone decide whether to press the
    button now or tomorrow.
    """
    return jsonify({**svc("jobs").status(), "budgets": _budget_status()})


def _budget_status() -> list[dict]:
    budgets = current_app.extensions.get("budgets") or {}
    out = []
    for name, budget in budgets.items():
        if not budget.limit:
            continue                    # not configured, nothing to report
        out.append({
            "provider": name,
            "used": budget.used(),
            "limit": budget.limit,
            "remaining": budget.remaining(),
            "window_hours": 24,
        })
    return out

