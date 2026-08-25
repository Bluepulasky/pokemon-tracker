from flask import Blueprint, jsonify

from . import repo, svc

bp = Blueprint("stats", __name__, url_prefix="/api")


@bp.get("/dashboard")
def dashboard():
    """Everything spec §16 asks for, in one payload."""
    r = repo()
    totals = r.collection_totals()
    progress = r.set_progress()
    for p in progress:
        target = p.get("target") or 0
        p["completion_pct"] = round(100.0 * (p.get("owned") or 0) / target, 1) if target else 0.0
        p["missing"] = target - (p.get("owned") or 0)

    target_total = sum(p.get("target") or 0 for p in progress)
    owned_total = sum(p.get("owned") or 0 for p in progress)
    value = svc("pricing").value_collection()

    by_completion = sorted(progress, key=lambda p: p["completion_pct"], reverse=True)
    by_missing = sorted(progress, key=lambda p: p["missing"], reverse=True)

    return jsonify({
        "unique_cards": totals["unique_cards"],
        "physical_cards": totals["physical_cards"],
        "sets_total": len(progress),
        "sets_complete": sum(1 for p in progress if p["target"] and p["owned"] == p["target"]),
        "completion_pct": round(100.0 * owned_total / target_total, 1) if target_total else 0.0,
        "target_cards": target_total,
        "owned_cards": owned_total,
        "value": value,
        "sets": progress,
        "most_complete": by_completion[:5],
        "most_missing": by_missing[:5],
        "top_value": _top_value(),
        "last_price_refresh": r.get_meta("last_price_refresh"),
    })


def _top_value(limit: int = 10):
    r = repo()
    pricing = svc("pricing")
    mods = r.get_modifiers()
    rows, _ = r.list_collection(page=1, page_size=500)
    valued = []
    for row in rows:
        est = pricing.estimate_item(row, mods)
        if est["total"] is not None:
            valued.append({"card_id": row["card_id"], "name": row["name"],
                           "number": row["number"], "set_name": row.get("set_name"),
                           "variant": row["variant"], "condition": row["condition"],
                           "quantity": row["quantity"], "value": est["total"]})
    return sorted(valued, key=lambda v: v["value"], reverse=True)[:limit]


@bp.get("/stats/history")
def history():
    """Collection evolution (spec §29). Comes from snapshots, because current
    state cannot answer 'how many did I own in March' (PLAN.md §2.6)."""
    return jsonify({"data": list(reversed(repo().list_snapshots()))})
