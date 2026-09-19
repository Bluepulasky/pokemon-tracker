"""App factory."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request, send_from_directory

from .config import Config
from .services.repository import PokemonRepo
from .services.pricing import PricingService
from .services.budget import RequestBudget
from .services.jobs import JobRunner
from .services.setbuilder import SetBuilder


class ApiError(Exception):
    def __init__(self, message: str, code: str = "bad_request", status: int = 400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


FRONTEND_MISSING = """\
The frontend has not been built: {path}/index.html does not exist.

  make frontend          # or: cd frontend && npm ci && npm run build

`make run`, `make dev` and the Docker image all build it for you.
"""


def create_app(config: type[Config] = Config) -> Flask:
    logging.basicConfig(level=logging.DEBUG if config.DEBUG else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config.ensure_dirs()

    frontend_dist = getattr(config, "FRONTEND_DIST", Config.FRONTEND_DIST)
    app = Flask(__name__, static_folder=str(frontend_dist), static_url_path="/static")
    app.config.from_object(config)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    repo = PokemonRepo(config.DB_PATH)

    app.extensions["repo"] = repo
    app.extensions["config"] = config

    # tcggo is the only source: catalog, images, versions and prices all come
    # from importing a set. It is metered, so its request budget is counted in
    # the database — a restart cannot hand back a fresh allowance.
    budgets = {"tcggo": RequestBudget(
        repo, "tcggo", getattr(config, "TCGGO_DAILY_LIMIT", 0),
        per_minute=getattr(config, "TCGGO_PER_MINUTE_LIMIT", 0))}
    app.extensions["budgets"] = budgets

    from .services.httpcache import HttpCache
    from .services.sources.tcggo import TcggoSource
    data_dir = getattr(config, "DATA_DIR", None)
    cache_dir = (data_dir / ".cache-tcggo"
                 if hasattr(data_dir, "__truediv__") else ".cache/tcggo")
    tcggo = TcggoSource(config, budget=budgets["tcggo"],
                        cache=HttpCache(cache_dir))
    app.extensions["versions_source"] = tcggo
    app.extensions["source"] = tcggo

    # Prices are read from the imported products, so pricing needs no live
    # source — importing a set is what fetches them.
    app.extensions["pricing"] = PricingService(repo, config)
    app.extensions["setbuilder"] = SetBuilder(repo)
    app.extensions["jobs"] = JobRunner(app)

    # --- optional shared secret -----------------------------
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
        return spa_index()                        # SPA fallback for hash-less deep links

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

    def spa_index():
        """The React app's entry page, or a 503 saying how to build it."""
        if not (frontend_dist / "index.html").is_file():
            return (FRONTEND_MISSING.format(path=frontend_dist), 503,
                    {"Content-Type": "text/plain; charset=utf-8"})
        # Never cached: it names the hashed asset files, so a stale copy keeps a
        # browser on the previous build. The assets themselves cache freely.
        response = send_from_directory(frontend_dist, "index.html", max_age=0)
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/")
    def index():
        return spa_index()

    return app
