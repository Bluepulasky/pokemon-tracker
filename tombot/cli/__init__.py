"""Flask CLI commands.

Every scheduled job is also a CLI command. That matters: the upstream API throws
500s often enough that "run it again by hand" is a normal operation, and a cron
entry inside a container hides its failures.
"""
from __future__ import annotations

import json
import os
from datetime import date

import click
from flask import current_app
from flask.cli import with_appcontext


def _repo():
    return current_app.extensions["repo"]


@click.command("init-db")
@with_appcontext
def init_db():
    """Create the schema (idempotent)."""
    _repo().init_db()
    click.echo(f"schema ready at {current_app.extensions['config'].DB_PATH}")


@click.command("backfill-card-meta")
@with_appcontext
def backfill_card_meta():
    """Fill card metadata (illustrator, supertype) from the tcggo cache, no network.

    The illustrator is the reprint-group key and the supertype drives the Cartas
    type filter. Sets imported before those were stored have them blank; this
    reads them back out of the cached responses so existing installs get them
    without re-importing (which would cost the metered cap)."""
    from ..services.catalog_backfill import scan_cache_for_card_meta

    cfg = current_app.extensions["config"]
    meta = scan_cache_for_card_meta(getattr(cfg, "DATA_DIR", None))
    if not meta:
        click.echo("no cached card data found — import a set or check the cache dir")
        return
    result = _repo().backfill_card_meta(meta)
    click.echo(f"metadata found for {len(meta)} products; "
               f"updated {result['products']} products, {result['cards']} cards")


@click.command("prices")
@click.option("--all", "all_cards", is_flag=True, help="Ignore cache age")
@click.option("--stale-days", type=int, default=None)
@with_appcontext
def prices(all_cards, stale_days):
    """Refresh prices for cards in the collection."""
    # Prices are read from the imported products, so --all/--stale-days no
    # longer change anything: every owned card is re-priced from local data.
    click.echo(current_app.extensions["pricing"].refresh())


@click.command("snapshot")
@with_appcontext
def snapshot():
    """Write a collection snapshot — the only way §29's history charts can exist."""
    click.echo(take_snapshot())


@click.command("monthly")
@with_appcontext
def monthly():
    """prices + snapshot. This is what cron should call."""
    click.echo(current_app.extensions["pricing"].refresh())
    click.echo(take_snapshot())


def take_snapshot() -> dict:
    repo = _repo()
    totals = repo.collection_totals()
    progress = repo.set_progress()
    target = sum(p.get("target") or 0 for p in progress)
    owned = sum(p.get("owned") or 0 for p in progress)
    value = current_app.extensions["pricing"].value_collection()
    snap = {
        "captured_on": date.today().isoformat(),
        "unique_cards": totals["unique_cards"],
        "physical_cards": totals["physical_cards"],
        "sets_total": len(progress),
        "sets_complete": sum(1 for p in progress
                             if p.get("target") and p["owned"] == p["target"]),
        "completion_pct": round(100.0 * owned / target, 2) if target else 0.0,
        "value_eur": value["total_eur"],
        "breakdown_json": json.dumps({"sets": progress, "value": value}),
    }
    repo.write_snapshot(snap)
    return {k: v for k, v in snap.items() if k != "breakdown_json"}


@click.command("scheduler")
@with_appcontext
def scheduler():
    """Run the monthly price refresh + snapshot on a schedule, and block.

    Deliberately its own process (its own container in compose). An in-process
    scheduler inside gunicorn would fire once per worker — with WEB_CONCURRENCY=2
    every price run would happen twice.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    cfg = current_app.extensions["config"]
    pricing = current_app.extensions["pricing"]
    app = current_app._get_current_object()

    def job():
        with app.app_context():
            try:
                click.echo(f"[scheduler] prices: {pricing.refresh()}")
                click.echo(f"[scheduler] snapshot: {take_snapshot()}")
            except Exception as e:                     # never kill the scheduler
                click.secho(f"[scheduler] run failed: {e}", fg="red")

    sched = BlockingScheduler(timezone=os.environ.get("TZ", "UTC"))
    trigger = CronTrigger(day=cfg.SCHEDULER_CRON_DAY, hour=cfg.SCHEDULER_CRON_HOUR,
                          minute=0)
    sched.add_job(job, trigger, id="monthly", max_instances=1,
                  coalesce=True, misfire_grace_time=6 * 3600)
    click.echo(f"[scheduler] monthly job: day {cfg.SCHEDULER_CRON_DAY} "
               f"at {cfg.SCHEDULER_CRON_HOUR:02d}:00 ({sched.timezone})")

    if _bool_env("RUN_ON_START"):
        click.echo("[scheduler] RUN_ON_START set — running once now")
        job()

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        click.echo("[scheduler] stopping")


def _bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def register(app):
    for cmd in (init_db, backfill_card_meta, prices, snapshot, monthly, scheduler):
        app.cli.add_command(cmd)
