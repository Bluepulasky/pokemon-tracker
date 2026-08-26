"""App factory."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request, send_from_directory

from .config import Config, DEFAULT_MODIFIERS
from .services.repository import PokemonRepo
from .services.sources import get_source
from .services.pricing import PricingService
from .services.importer import CatalogImporter
from .services.setbuilder import SetBuilder


class ApiError(Exception):
    def __init__(self, message: str, code: str = "bad_request", status: int = 400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


def create_app(config: type[Config] = Config) -> Flask:
    logging.basicConfig(level=logging.DEBUG if config.DEBUG else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config.ensure_dirs()

    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.config.from_object(config)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    repo = PokemonRepo(config.DB_PATH)
    source = get_source(config.SOURCE, config)

    app.extensions["repo"] = repo
    app.extensions["source"] = source
    app.extensions["config"] = config
    # Prices come from their own source. The catalog keeps using pokemontcg.io
    # until TCGdex is proven to cover images and set data as well.
    price_source = get_source(getattr(config, "PRICE_SOURCE", config.SOURCE), config)
    app.extensions["price_source"] = price_source
    app.extensions["pricing"] = PricingService(repo, price_source, config)
    app.extensions["importer"] = CatalogImporter(repo, source, config)
    app.extensions["setbuilder"] = SetBuilder(repo)

    # --- optional shared secret (PLAN.md §2.7) -----------------------------
    @app.before_request
    def _guard():
        token = config.APP_TOKEN
        if not token or not request.path.startswith("/api/"):
            return None
        if request.path == "/api/healthz":
            return None
        supplied = request.headers.get("X-App-Token") or request.cookies.get("app_token")
        if supplied != token:
            return jsonify({"error": {"code": "unauthorized",
                                      "message": "token inválido"}}), 401
        return None

    # --- uniform error envelope -------------------------------------------
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return jsonify({"error": {"code": e.code, "message": e.message}}), e.status

    @app.errorhandler(404)
    def _not_found(_e):
        if request.path.startswith("/api/") or request.path.startswith("/media/"):
            return jsonify({"error": {"code": "not_found", "message": "no encontrado"}}), 404
        return render_template("index.html")      # SPA fallback for hash-less deep links

    @app.errorhandler(413)
    def _too_large(_e):
        return jsonify({"error": {
            "code": "payload_too_large",
            "message": f"imagen demasiado grande (máx {config.MAX_UPLOAD_MB} MB)"}}), 413

    @app.errorhandler(Exception)
    def _unhandled(e):
        app.logger.exception("unhandled error")
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "internal", "message": str(e)}}), 500
        raise e

    # --- blueprints --------------------------------------------------------
    from .api import catalog, sets, collection, prices, stats
    for mod in (catalog, sets, collection, prices, stats):
        app.register_blueprint(mod.bp)

    # --- media + SPA -------------------------------------------------------
    @app.route("/media/<path:filename>")
    def media(filename):
        return send_from_directory(config.MEDIA_DIR, filename, max_age=86400)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app
