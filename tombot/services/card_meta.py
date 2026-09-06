"""Apply card-metadata fixes from a CSV.

Some catalog fields tcggo returns — the illustrator (the reprint-group key) and
the supertype (the card-type filter) — were not stored by imports that predate
those columns, so cards from older imports have them blank. And one field tcggo
does not return at all — the energy type / colour (Fire, Water, Psychic…) — can
only ever arrive this way. This fills the gaps from a CSV keyed by `card_id`,
which the app also ships pre-baked (`tombot/data/card_meta.csv`) so an install
can self-heal with no re-import.

Only blank fields are filled — an existing value is never overwritten, so a fix
file can be applied repeatedly and safely. The fixable columns are `artist`,
`supertype` and `types` today; more can be added without touching the format.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

# The columns this tool can write onto a card. Add here to fix a new field; the
# CSV simply grows a column, and old files (without it) keep working.
FIXABLE = ("artist", "supertype", "types")

# CSV columns that hold a list, and the card column each is stored in as JSON.
# `types` is "Fire" or "Fire|Water" in the file and '["Fire","Water"]' on the card.
LIST_FIELDS = {"types": "types_json"}
LIST_SEPARATORS = re.compile(r"\s*[|/+]\s*")

ID_KEYS = ("card_id", "id", "cardid")

BUNDLED = Path(__file__).resolve().parent.parent / "data" / "card_meta.csv"


def _norm(header: str) -> str:
    return (header or "").strip().lower().replace(" ", "_").replace("﻿", "")


def split_list(value: str) -> list[str]:
    """'Fire|Water' -> ['Fire', 'Water']. Also accepts '/' and '+', so a hand-made
    file need not know the canonical separator. Order kept, blanks dropped."""
    return [v for v in (p.strip() for p in LIST_SEPARATORS.split(value or "")) if v]


def join_list(values) -> str:
    """The inverse of split_list, for the export."""
    return "|".join(values or [])


def bundled_text() -> str | None:
    """The shipped fix file's contents, or None if it is missing."""
    try:
        return BUNDLED.read_text(encoding="utf-8")
    except OSError:
        return None


def parse_csv(text: str) -> tuple[list[dict], list[dict]]:
    """(rows, errors). A row is {card_id, artist?, supertype?, types?, line}.

    A list column (`types`) is returned already split: `types: ['Fire']`.

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
            if field in LIST_FIELDS:
                parsed = split_list(val)
                if parsed:
                    row[field] = parsed
            elif val:
                row[field] = val
        if len(row) > 2:                               # more than card_id + line
            rows.append(row)
    return rows, errors


def apply_fixes(repo, rows: list[dict], overwrite: bool = False) -> dict:
    """Write fields on the named cards. Returns per-field counts + misses.

    Fills blanks only by default; overwrite=True also replaces existing values.
    """
    known = repo.existing_card_ids({r["card_id"] for r in rows})
    # Keyed by the card column, which for a list field is its *_json column.
    updates: dict[str, list[tuple[str, str]]] = {
        LIST_FIELDS.get(f, f): [] for f in FIXABLE}
    missing = []
    for r in rows:
        if r["card_id"] not in known:
            missing.append({"card_id": r["card_id"], "line": r.get("line")})
            continue
        for f in FIXABLE:
            if not r.get(f):
                continue
            if f in LIST_FIELDS:
                updates[LIST_FIELDS[f]].append(
                    (json.dumps(r[f], ensure_ascii=False), r["card_id"]))
            else:
                updates[f].append((r[f], r["card_id"]))
    counts = repo.fill_card_fields(updates, overwrite=overwrite)
    # Report under the CSV column name, which is what the user sees.
    col_for = {v: k for k, v in LIST_FIELDS.items()}
    changed = {col_for.get(k, k): n for k, n in counts.items()}
    return {"changed": changed, "overwrite": overwrite, "missing": missing,
            "cards_in_file": len(rows)}
