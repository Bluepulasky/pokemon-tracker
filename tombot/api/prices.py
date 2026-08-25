from flask import Blueprint, jsonify, request

from . import repo, svc
from .. import ApiError

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


@bp.get("/history")
def history():
    return jsonify({"data": repo().price_history(
        card_id=request.args.get("card_id"),
        set_id=request.args.get("set_id"),
    )})


@bp.get("/modifiers")
def modifiers():
    return jsonify(repo().get_modifiers())
