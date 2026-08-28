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
    # Which sets this card counts towards, and whether a rule put it there or
    # someone did. A card excluded by a rule looks identical to one that does
    # not exist, until you can see the difference.
    card["in_sets"] = repo().sets_containing_card(card_id)
    # Empty when the card has no sibling printings, so the UI can skip the
    # edition selector rather than showing a one-option dropdown.
    printings = repo().printings_for_card(card_id)
    # Parse the variant list so the client does not have to, and fall back to the
    # era rules for a card that has no printing row of its own.
    for pr in printings:
        pr["variants"] = json.loads(pr.get("variants_json") or "[]")
    if not printings:
        from ..services.printing_variants import variants_for
        printings = [{
            "id": None, "card_id": card_id,
            "official_set_id": card["official_set_id"],
            "display_name": card.get("set_name"), "is_reprint": 0,
            "variants": variants_for(card["official_set_id"], card.get("rarity")),
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
    """Global search across catalog and collection (spec §19).

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


@bp.post("/maintenance/rebuild")
def rebuild_database():
    """The web equivalent of `flask bootstrap`.

    Same code path as the CLI: schema, any incomplete sets, personal sets,
    printings. Idempotent, so pressing it twice is harmless.
    """
    def work():
        from ..cli import run_bootstrap
        return run_bootstrap()

    started, state = svc("jobs").start("rebuild", work)
    return jsonify({"started": started, **state}), (202 if started else 409)


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
        slots = [s for cs in repo().list_collection_sets()
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


@bp.post("/catalog/import")
def import_catalog():
    """Long-running: kept as an explicit POST, not something a page load triggers."""
    body = request.get_json(silent=True) or {}
    set_ids = body.get("sets")
    if not set_ids:
        from ..services.seed_sets import required_official_sets
        set_ids = required_official_sets()
    result = svc("importer").import_sets(set_ids)
    if body.get("cache_images", True):
        result["images"] = svc("importer").cache_images()
    if body.get("resolve_links", True):
        result["market_links"] = svc("importer").resolve_market_links()
    return jsonify(result)
