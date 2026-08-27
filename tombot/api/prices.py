from flask import Blueprint, jsonify, request

from . import repo, svc
from .. import ApiError
from ..config import VARIANTS

bp = Blueprint("prices", __name__, url_prefix="/api/prices")


@bp.get("/<card_id>")
def card_prices(card_id):
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    return jsonify({"card_id": card_id, "prices": repo().get_prices_for_card(card_id)})


@bp.post("/refresh")
def refresh():
    """Manual trigger for the same code path the scheduler runs — important
    because the upstream API is flaky and reruns are routine (PLAN.md §2.2)."""
    body = request.get_json(silent=True) or {}
    return jsonify(svc("pricing").refresh(
        stale_days=body.get("stale_days"),
        all_cards=bool(body.get("all", False)),
    ))


@bp.post("/refresh-async")
def refresh_async():
    """Kick off a price refresh and return immediately.

    The synchronous endpoint holds a worker for as long as the upstream takes,
    which is minutes for a full collection.
    """
    started, state = svc("jobs").start(
        "prices", lambda: svc("pricing").refresh(all_cards=True))
    return jsonify({"started": started, **state}), (202 if started else 409)


@bp.get("/history")
def history():
    return jsonify({"data": repo().price_history(
        card_id=request.args.get("card_id"),
        set_id=request.args.get("set_id"),
    )})


@bp.get("/modifiers")
def modifiers():
    return jsonify(repo().get_modifiers())


@bp.put("/modifiers/<kind>/<key>")
def set_modifier(kind, key):
    """Edit a price multiplier.

    The 1st-edition premium lives here because no source prices a 1st edition
    apart from its unstamped twin. One number cannot be right for a Charizard and
    a common at once, so it has to be adjustable.
    """
    if kind not in ("condition", "language", "variant"):
        raise ApiError(f"tipo de multiplicador desconocido: {kind}", "invalid_modifier")
    body = request.get_json(silent=True) or {}
    try:
        value = float(body.get("multiplier"))
    except (TypeError, ValueError):
        raise ApiError("el multiplicador debe ser un número", "invalid_modifier") from None
    if not 0 < value <= 100:
        raise ApiError("el multiplicador debe estar entre 0 y 100", "invalid_modifier")
    repo().set_modifier(kind, key, value)
    return jsonify({"kind": kind, "key": key, "multiplier": value})


@bp.put("/manual/<card_id>/<variant>")
def set_manual(card_id, variant):
    """A price typed in by hand for one printing.

    Needed because the feed has real gaps — every WOTC promo comes back with no
    price at all — and because a listing you are looking at beats an average.
    Stored as its own source so a refresh never overwrites it; sending null
    removes it and hands the printing back to the feed.
    """
    if not repo().get_card(card_id):
        raise ApiError("carta no encontrada", "not_found", 404)
    if variant not in VARIANTS:
        raise ApiError(f"variante inválida: {variant}")
    body = request.get_json(silent=True) or {}
    raw = body.get("price")
    if raw in (None, ""):
        repo().set_manual_price(card_id, variant, None)
        return jsonify({"card_id": card_id, "variant": variant, "price": None})
    try:
        price = float(raw)
    except (TypeError, ValueError):
        raise ApiError("el precio debe ser un número", "invalid_price") from None
    if price < 0:
        raise ApiError("el precio no puede ser negativo", "invalid_price")
    repo().set_manual_price(card_id, variant, price)
    return jsonify({"card_id": card_id, "variant": variant, "price": price})
