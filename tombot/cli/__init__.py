"""Flask CLI commands.

Every scheduled job is also a CLI command. That matters: the upstream API throws
500s often enough that "run it again by hand" is a normal operation, and a cron
entry inside a container hides its failures (PLAN.md §2.13).
"""
from __future__ import annotations

import json
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


@click.command("bootstrap")
@click.pass_context
@with_appcontext
def bootstrap(ctx):
    """init-db + import-catalog + seed-sets. One command for a fresh install."""
    ctx.invoke(init_db)
    ctx.invoke(import_catalog, set_ids="", images=True)
    ctx.invoke(seed_sets, rebuild=True)
    click.secho("bootstrap complete", fg="green")


def register(app):
    for cmd in (init_db, import_catalog, seed_sets, prices, snapshot, monthly, bootstrap):
        app.cli.add_command(cmd)
