#!/usr/bin/env bash
# Container entrypoint.
#
#   serve       (default) prepare, then run gunicorn
#   scheduler   run the monthly price/snapshot job on a cron schedule
#   <anything>  run it verbatim, e.g. `docker compose run --rm app flask prices`
set -euo pipefail

log() { echo "[tombot] $*"; }

# --- ownership -------------------------------------------------------------
# data/ and media/ are bind-mounted from the host. Running as root would leave
# root-owned files on the host; running as a fixed uid would fail to write when
# the host user is not that uid. So: fix ownership as root, then drop to PUID.
prepare_dirs() {
    mkdir -p "$DATA_DIR" "$MEDIA_DIR"/{catalog,collection,thumbs}
    if [ "$(id -u)" = "0" ]; then
        if ! chown -R "$PUID:$PGID" "$DATA_DIR" "$MEDIA_DIR" 2>/dev/null; then
            log "WARN: could not chown $DATA_DIR / $MEDIA_DIR (read-only mount?)"
        fi
    fi
}

as_app() {
    if [ "$(id -u)" = "0" ]; then
        exec gosu "$PUID:$PGID" "$@"
    else
        exec "$@"
    fi
}

run_as_app() {                      # same, but returns instead of exec'ing
    if [ "$(id -u)" = "0" ]; then
        gosu "$PUID:$PGID" "$@"
    else
        "$@"
    fi
}

# --- first run -------------------------------------------------------------
bootstrap() {
    # init-db is idempotent and instant; always safe to run.
    run_as_app flask init-db

    if [ "${AUTO_BOOTSTRAP:-1}" != "1" ]; then
        log "AUTO_BOOTSTRAP=0 — skipping catalog import"
        return
    fi

    local count
    count=$(run_as_app python -c "
from tombot.config import Config
from tombot.services.repository import PokemonRepo
print(PokemonRepo(Config.DB_PATH).count_cards())
" 2>/dev/null || echo 0)

    if [ "$count" -gt 0 ]; then
        log "catalog present ($count cards) — skipping import"
        return
    fi

    log "empty catalog: importing ~1,100 cards. This takes a few minutes and the"
    log "upstream API is flaky; failed sets are retried on the next start."
    run_as_app flask import-catalog   || log "WARN: catalog import incomplete — re-run 'make links' / restart to retry"
    run_as_app flask seed-sets        || log "WARN: set seeding incomplete"
    run_as_app flask resolve-links    || log "WARN: Cardmarket link resolution incomplete"
    log "bootstrap done"
}

case "${1:-serve}" in
    serve)
        prepare_dirs
        bootstrap
        log "serving on 0.0.0.0:${PORT} (${WEB_CONCURRENCY} workers x ${WEB_THREADS} threads)"
        as_app gunicorn \
            --workers "${WEB_CONCURRENCY}" \
            --threads "${WEB_THREADS}" \
            --bind "0.0.0.0:${PORT}" \
            --timeout "${WEB_TIMEOUT}" \
            --access-logfile - \
            --error-logfile - \
            app:app
        ;;
    scheduler)
        prepare_dirs
        log "scheduler starting (monthly price refresh + snapshot)"
        as_app flask scheduler
        ;;
    *)
        prepare_dirs
        as_app "$@"
        ;;
esac
