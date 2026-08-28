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
# There is no bootstrap. A fresh install is an empty schema; sets are imported
# one at a time from the Mantenimiento tab. So startup only ensures the schema
# exists, which init-db does idempotently.
prepare_schema() {
    if run_as_app flask init-db; then
        log "schema ready — add sets from Mantenimiento → Sets"
    else
        log "WARN: could not initialise the schema; retry: docker compose restart app"
    fi
}

case "${1:-serve}" in
    serve)
        prepare_dirs
        prepare_schema
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
