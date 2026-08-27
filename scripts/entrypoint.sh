#!/usr/bin/env bash
# Container entrypoint.
#
#   serve       (default) prepare, then run the web server
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
# `flask bootstrap` is itself idempotent and decides whether the catalog needs
# importing, so this just delegates rather than duplicating that check here.
bootstrap() {
    if [ "${AUTO_BOOTSTRAP:-1}" != "1" ]; then
        log "AUTO_BOOTSTRAP=0 — skipping setup; run 'make docker-bootstrap' yourself"
        run_as_app flask init-db
        return
    fi

    log "setting up (first run imports ~1,100 cards; the upstream API is flaky,"
    log "anything that fails is retried on the next start)"
    if run_as_app flask bootstrap; then
        log "setup complete"
    else
        log "WARN: setup incomplete — retry with: docker compose restart app"
        log "                            or: make docker-bootstrap"
    fi
}

case "${1:-serve}" in
    serve)
        prepare_dirs
        bootstrap
        log "serving on 0.0.0.0:${PORT} (${WEB_THREADS} threads, one process)"
        # One process, threads for concurrency.
        #
        # This is a single-user app, so nothing here needed multiple worker
        # processes — and having them was actively wrong: background job state
        # lives in the process that started the job, so a second worker
        # answered "idle" to half the status polls and would happily start a
        # second price refresh against a metered API.
        as_app waitress-serve \
            --host=0.0.0.0 \
            --port="${PORT}" \
            --threads="${WEB_THREADS}" \
            --channel-timeout="${WEB_TIMEOUT}" \
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
