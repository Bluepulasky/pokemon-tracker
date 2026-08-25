"""Flask CLI commands.

Every scheduled job is also a CLI command. That matters: the upstream API throws
500s often enough that "run it again by hand" is a normal operation, and a cron
entry inside a container hides its failures (PLAN.md §2.13).
"""
from __future__ import annotations

import json
import os
from datetime import date

import click
from flask import current_app
from flask.cli import with_appcontext

from ..config import DEFAULT_MODIFIERS
from ..services.seed_sets import PERSONAL_SETS, required_official_sets


def _repo():
    return current_app.extensions["repo"]


@click.command("init-db")
@with_appcontext
def init_db():
    """Create the schema and seed the default price modifiers."""
    _repo().init_db(DEFAULT_MODIFIERS)
    click.echo(f"schema ready at {current_app.extensions['config'].DB_PATH}")


@click.command("import-catalog")
@click.option("--sets", "set_ids", default="", help="Comma-separated set ids; default = all needed")
@click.option("--images/--no-images", default=True, help="Cache catalog images locally")
@with_appcontext
def import_catalog(set_ids, images):
    """Import the official catalog from the configured source."""
    ids = [s.strip() for s in set_ids.split(",") if s.strip()] or required_official_sets()
    click.echo(f"importing {len(ids)} sets: {', '.join(ids)}")
    result = current_app.extensions["importer"].import_sets(ids)
    for sid, n in result["sets"].items():
        click.echo(f"  {sid:<8} {n:>4} cards")
    for f in result["failed"]:
        click.secho(f"  {f['set']:<8} FAILED: {f['error']}", fg="red")
    click.echo(f"total: {result['cards']} cards")
    if images:
        click.echo(f"images: {current_app.extensions['importer'].cache_images()}")
    if result["failed"]:
        click.secho("re-run to retry the failed sets (import is idempotent)", fg="yellow")


@click.command("resolve-links")
@click.option("--limit", type=int, default=5000)
@with_appcontext
def resolve_links(limit):
    """Resolve each card's Cardmarket product URL. Resumable; safe to re-run."""
    with click.progressbar(length=100, label="resolving") as bar:
        state = {"pct": 0}

        def progress(done, total):
            pct = int(100 * done / total)
            bar.update(pct - state["pct"])
            state["pct"] = pct

        r = current_app.extensions["importer"].resolve_market_links(
            limit, progress=progress)
    click.echo(f"resolved {r['resolved']}, failed {r['failed']}, "
               f"{r['total_with_links']} cards now have a Cardmarket link")
    if r["failed"]:
        click.secho("re-run to retry the failures", fg="yellow")


@click.command("seed-sets")
@click.option("--rebuild/--no-rebuild", default=True, help="Materialise slots from rules")
@with_appcontext
def seed_sets(rebuild):
    """Create the personal sets and build their slots. Never touches collection data."""
    repo = _repo()
    for s in PERSONAL_SETS:
        repo.upsert_collection_set({
            "id": s["id"], "name": s["name"], "description": s.get("description"),
            "group_name": s.get("group_name"), "position": s.get("position", 0),
            "rules_json": json.dumps(s["rules"]),
        })
    click.echo(f"{len(PERSONAL_SETS)} personal sets written")
    if rebuild:
        for r in current_app.extensions["setbuilder"].build_all():
            click.echo(f"  {r['set']:<36} {r.get('slots', 0):>4} slots "
                       f"({r.get('excluded', 0)} excluded by rules)")


@click.command("prices")
@click.option("--all", "all_cards", is_flag=True, help="Ignore cache age")
@click.option("--stale-days", type=int, default=None)
@with_appcontext
def prices(all_cards, stale_days):
    """Refresh prices for cards in the collection (spec §30)."""
    click.echo(current_app.extensions["pricing"].refresh(
        stale_days=stale_days, all_cards=all_cards))


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


@click.command("bootstrap")
@click.option("--force-catalog", is_flag=True,
              help="Re-import every set even if the catalog looks complete")
@click.pass_context
@with_appcontext
def bootstrap(ctx, force_catalog):
    """Set up or repair the install: schema, catalog, personal sets, links.

    This is the repair command as much as the install command, so it must make
    progress on every run. It checks the catalog per set rather than asking
    "are there any cards", because a partial import is the normal outcome when
    the upstream is throwing 500s, and treating that as done leaves the app
    permanently half-built.

    Set seeding and link resolution always run: both are idempotent, both are
    cheap when there is nothing to do, and neither depends on the import having
    succeeded.
    """
    ctx.invoke(init_db)
    repo = _repo()

    required = required_official_sets()
    gaps = repo.catalog_gaps(required)

    if force_catalog:
        click.echo(f"--force-catalog: re-importing all {len(required)} sets")
        ctx.invoke(import_catalog, set_ids=",".join(required), images=True)
    elif gaps:
        for g in gaps:
            expected = g["expected"] if g["expected"] is not None else "?"
            click.echo(f"  {g['set']:<8} {g['have']}/{expected}  {g['why']}")
        click.echo(f"importing {len(gaps)} incomplete set(s)")
        ctx.invoke(import_catalog, set_ids=",".join(g["set"] for g in gaps), images=True)
    else:
        click.echo(f"catalog complete ({repo.count_cards()} cards across "
                   f"{len(required)} sets)")

    ctx.invoke(seed_sets, rebuild=True)
    ctx.invoke(resolve_links, limit=5000)

    remaining = repo.catalog_gaps(required)
    if remaining:
        click.secho(f"{len(remaining)} set(s) still incomplete: "
                    f"{', '.join(g['set'] for g in remaining)}", fg="yellow")
        click.secho("re-run to retry — imports resume where they left off", fg="yellow")
    else:
        click.secho("bootstrap complete", fg="green")


def register(app):
    for cmd in (init_db, import_catalog, seed_sets, resolve_links,
                prices, snapshot, monthly, scheduler, bootstrap):
        app.cli.add_command(cmd)
