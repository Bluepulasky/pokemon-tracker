"""Apply card-metadata fixes from a CSV.

Some catalog fields tcggo returns — the illustrator (the reprint-group key) and
the supertype (the card-type filter) — were not stored by imports that predate
those columns, so cards from older imports have them blank. This fills the gaps
from a CSV keyed by `card_id`, which the app also ships pre-baked
(`tombot/data/card_meta.csv`) so an install can self-heal with no re-import.

Only blank fields are filled — an existing value is never overwritten, so a fix
file can be applied repeatedly and safely. The fixable columns are `artist` and
`supertype` today; more can be added without touching the format.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

# The columns this tool can write onto a card. Add here to fix a new field; the
# CSV simply grows a column, and old files (without it) keep working.
FIXABLE = ("artist", "supertype")

ID_KEYS = ("card_id", "id", "cardid")

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "card_meta.csv"


def _norm(header: str) -> str:
    return (header or "").strip().lower().replace(" ", "_").replace("﻿", "")


def bundled_text() -> str | None:
    """The shipped fix file's contents, or None if it is missing."""
    try:
        return BUNDLED.read_text(encoding="utf-8")
    except OSError:
        return None


def parse_csv(text: str) -> tuple[list[dict], list[dict]]:
    """(rows, errors). A row is {card_id, artist?, supertype?, line}.

    Forgiving about what a spreadsheet emits (Excel's `;` and BOM), strict about
    what it means. Never raises: every problem is collected for one report.
    """
    if not text.strip():
        return [], [{"line": 0, "error": "el archivo está vacío"}]
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return [], [{"line": 0, "error": "no se encontró una cabecera"}]

    headers = {_norm(h): h for h in reader.fieldnames}
    id_col = next((headers[k] for k in ID_KEYS if k in headers), None)
    if id_col is None:
        return [], [{"line": 0, "error": "falta la columna card_id"}]
    fix_cols = {f: headers[f] for f in FIXABLE if f in headers}
    if not fix_cols:
        return [], [{"line": 0,
                     "error": f"ninguna columna para corregir ({', '.join(FIXABLE)})"}]

    rows, errors = [], []
    for i, raw in enumerate(reader, start=2):
        cid = (raw.get(id_col) or "").strip()
        if not cid:
            continue                                   # blank line, skip quietly
        row = {"card_id": cid, "line": i}
        for field, col in fix_cols.items():
            val = (raw.get(col) or "").strip()
            if val:
                row[field] = val
        if len(row) > 2:                               # more than card_id + line
            rows.append(row)
    return rows, errors


def apply_fixes(repo, rows: list[dict], overwrite: bool = False) -> dict:
    """Write fields on the named cards. Returns per-field counts + misses.

    Fills blanks only by default; overwrite=True also replaces existing values.
    """
    known = repo.existing_card_ids({r["card_id"] for r in rows})
    updates: dict[str, list[tuple[str, str]]] = {f: [] for f in FIXABLE}
    missing = []
    for r in rows:
        if r["card_id"] not in known:
            missing.append({"card_id": r["card_id"], "line": r.get("line")})
            continue
        for f in FIXABLE:
            if r.get(f):
                updates[f].append((r[f], r["card_id"]))
    changed = repo.fill_card_fields(updates, overwrite=overwrite)
    return {"changed": changed, "overwrite": overwrite, "missing": missing,
            "cards_in_file": len(rows)}
