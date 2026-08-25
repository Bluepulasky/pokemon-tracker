"""HTTP layer. No SQL here — everything goes through PokemonRepo (spec §22)."""
from __future__ import annotations

from flask import current_app, jsonify, request


def repo():
    return current_app.extensions["repo"]


def svc(name: str):
    return current_app.extensions[name]


def cfg():
    return current_app.extensions["config"]


def paginate_args(default_size: int = 60) -> tuple[int, int]:
    page = max(1, request.args.get("page", 1, type=int))
    size = min(500, max(1, request.args.get("page_size", default_size, type=int)))
    return page, size


def page_response(rows, total, page, page_size):
    return jsonify({"data": rows, "page": page, "page_size": page_size, "total": total})
