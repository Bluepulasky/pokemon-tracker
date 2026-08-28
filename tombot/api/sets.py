import json

from flask import Blueprint, jsonify, request

from . import repo, svc
from .. import ApiError

bp = Blueprint("sets", __name__, url_prefix="/api/sets")


def _with_progress(rows):
    for r in rows:
        target = r.get("target") or 0
        r["completion_pct"] = round(100.0 * (r.get("owned") or 0) / target, 1) if target else 0.0
    return rows


@bp.get("")
def list_sets():
    sets_by_id = {s["id"]: s for s in repo().list_collection_sets()}
    rows = _with_progress(repo().set_progress())
    for r in rows:
        r["description"] = (sets_by_id.get(r["id"]) or {}).get("description")
    return jsonify({"data": rows})


@bp.get("/<set_id>")
def get_set(set_id):
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    progress = _with_progress(repo().set_progress(set_id))
    cset["progress"] = progress[0] if progress else None
    cset["slots"] = repo().get_set_slots(set_id)
    # What the rule left out, so nothing in a set is invisible.
    cset["excluded"] = repo().cards_excluded_from_set(set_id)
    return jsonify(cset)


@bp.get("/<set_id>/missing")
def missing(set_id):
    if not repo().get_collection_set(set_id):
        raise ApiError("set no encontrado", "not_found", 404)
    return jsonify({"data": repo().missing_slots(set_id, request.args.get("sort", "number"))})


@bp.post("")
def create_set():
    body = request.get_json(silent=True) or {}
    if not body.get("id") or not body.get("name"):
        raise ApiError("id y name son obligatorios")
    _save(body)
    return jsonify(repo().get_collection_set(body["id"])), 201


@bp.put("/<set_id>")
def update_set(set_id):
    if not repo().get_collection_set(set_id):
        raise ApiError("set no encontrado", "not_found", 404)
    body = request.get_json(silent=True) or {}
    body["id"] = set_id
    _save(body)
    return jsonify(repo().get_collection_set(set_id))


def _save(body):
    rules = body.get("rules")
    repo().upsert_collection_set({
        "id": body["id"],
        "name": body.get("name") or body["id"],
        "description": body.get("description"),
        "group_name": body.get("group_name"),
        "position": int(body.get("position", 0)),
        "rules_json": json.dumps(rules) if rules is not None else body.get("rules_json"),
    })


@bp.delete("/<set_id>")
def delete_set(set_id):
    repo().delete_collection_set(set_id)
    return jsonify({"deleted": set_id})


@bp.post("/<set_id>/rebuild")
def rebuild(set_id):
    """Re-materialise slots from rules_json. Manual slots survive (PLAN.md §2.10)."""
    return jsonify(svc("setbuilder").build(set_id))


# The collection rule is a call on the set's completion state, kept separate
# from the set itself: the catalogue is always the whole set, and the rule
# decides which of it you are trying to complete. Named modes keep the common
# choices one click away; the rule underneath stays fully editable.
COLLECTION_MODES = {
    "all":        {"label": "Todas"},
    "no-holos":   {"label": "Sin holos",  "exclude_rarities": ["Rare Holo"]},
    "holos-only": {"label": "Solo holos", "include_rarities": ["Rare Holo"]},
    "no-commons": {"label": "Sin comunes", "exclude_rarities": ["Common"]},
}


@bp.get("/<set_id>/mode")
def get_mode(set_id):
    """Which named mode the set's current rule matches, if any."""
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    rules = json.loads(cset.get("rules_json") or "{}")
    excl = set(rules.get("exclude_rarities") or [])
    incl = set(rules.get("include_rarities") or [])
    current = "custom"
    if not excl and not incl:
        current = "all"
    elif excl == {"Rare Holo"} and not incl:
        current = "no-holos"
    elif incl == {"Rare Holo"} and not excl:
        current = "holos-only"
    elif excl == {"Common"} and not incl:
        current = "no-commons"
    return jsonify({
        "set_id": set_id, "mode": current,
        "options": [{"key": k, "label": v["label"]} for k, v in COLLECTION_MODES.items()],
    })


@bp.put("/<set_id>/mode")
def set_mode(set_id):
    """Change what part of the set you are collecting, and re-materialise slots.

    The set's include_sets are preserved; only the rarity filter changes. Manual
    slots survive the rebuild.
    """
    cset = repo().get_collection_set(set_id)
    if not cset:
        raise ApiError("set no encontrado", "not_found", 404)
    mode = (request.get_json(silent=True) or {}).get("mode")
    if mode not in COLLECTION_MODES:
        raise ApiError(f"modo desconocido: {mode}", "invalid_mode")

    rules = json.loads(cset.get("rules_json") or "{}")
    # Keep what the set is over; replace only the rarity call.
    new_rules = {k: v for k, v in rules.items()
                 if k in ("include_sets", "include_cards", "exclude_cards", "merge")}
    spec = COLLECTION_MODES[mode]
    if spec.get("exclude_rarities"):
        new_rules["exclude_rarities"] = spec["exclude_rarities"]
    if spec.get("include_rarities"):
        new_rules["include_rarities"] = spec["include_rarities"]

    repo().upsert_collection_set({
        "id": set_id, "name": cset["name"], "description": cset.get("description"),
        "group_name": cset.get("group_name"), "position": cset.get("position", 0),
        "rules_json": json.dumps(new_rules),
    })
    built = svc("setbuilder").build(set_id)
    return jsonify({"set_id": set_id, "mode": mode, **built})
