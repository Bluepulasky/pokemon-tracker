"""PokemonRepo — the only module in the app that issues SQL.

Spec §22/§31: Flask routes must never touch SQLite directly. Services call the
repo too; nothing else opens a connection.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

log = logging.getLogger(__name__)

from ..config import CONDITIONS, DEFAULT_CONDITION, RETIRED_CONDITIONS
from .printing_variants import variants_for

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = "1"


def _number_sort(number: str) -> float:
    """Sort key for card numbers.

    Numbers are strings ('4', 'H12', 'SH1', 'TG04'); sorting lexically puts #10
    before #2. Prefixed numbers sort after plain ones so promos land at the end.
    """
    if not number:
        return 999999.0
    m = re.search(r"(\d+)", number)
    if not m:
        return 999998.0
    n = float(m.group(1))
    return n + 100000.0 if number[0].isalpha() else n


class PokemonRepo:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    # ------------------------------------------------------------------ conn
    # Columns of collection_items are listed explicitly wherever a query also
    # computes `rating`. An upgraded database still carries the retired
    # collection_items.rating column, and `SELECT i.*` would emit a second
    # column of that name which shadows the real value — a bug that appears only
    # on installs that have been through the migration.

    def connect(self) -> sqlite3.Connection:
        """This thread's connection, opened once and reused.

        Opening a fresh connection per query cost 362 connections for a single
        collection page, each re-running the four PRAGMAs below. `journal_mode =
        WAL` needs a brief exclusive lock, so with a writer active (a catalog
        import, a price run) those all queued on the lock and the app stalled.
        One connection per thread removes that contention entirely.
        """
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.row_factory = sqlite3.Row
            # SQLite defaults foreign_keys OFF; without this every FK is decorative.
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")  # writers must not block readers
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA synchronous = NORMAL")
        except Exception:
            conn.close()        # a half-configured connection must not leak
            raise
        self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextmanager
    def tx(self):
        """Transaction scope, re-entrant.

        Several repo methods call others (get_collection_item -> get_photos), so
        nested blocks must join the outer transaction rather than commit half of
        it and leave the rest uncommitted.
        """
        conn = self.connect()
        depth = getattr(self._local, "depth", 0)
        self._local.depth = depth + 1
        try:
            yield conn
            if depth == 0:
                conn.commit()
        except Exception:
            if depth == 0:
                conn.rollback()
            raise
        finally:
            self._local.depth = depth

    def _all(self, sql: str, params: Sequence = ()) -> list[dict]:
        with self.tx() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: Sequence = ()) -> dict | None:
        with self.tx() as c:
            r = c.execute(sql, params).fetchone()
            return dict(r) if r else None

    def _scalar(self, sql: str, params: Sequence = ()) -> Any:
        with self.tx() as c:
            r = c.execute(sql, params).fetchone()
            return r[0] if r else None

    # ---------------------------------------------------------------- schema
    def init_db(self) -> None:
        """Create the schema. schema.sql is the single source of truth.

        Every statement is CREATE ... IF NOT EXISTS, so this is safe to run on
        every start and does nothing to an existing database. There are no
        migrations: a schema change is a change to schema.sql, and a database
        from before it is recreated (the app is rebuilt from set imports, so
        there is nothing to preserve). Keep it that simple."""
        with self.tx() as c:
            c.executescript(SCHEMA_PATH.read_text())
            c.execute(
                "INSERT INTO app_meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=datetime('now')", (SCHEMA_VERSION,))

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        v = self._scalar("SELECT value FROM app_meta WHERE key = ?", (key,))
        return v if v is not None else default

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO app_meta(key, value) VALUES (?,?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                (key, value),
            )

    # --------------------------------------------------------------- catalog
    def upsert_official_set(self, s: dict) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO official_sets
                     (id,name,series,printed_total,total,release_date,ptcgo_code,logo_url,symbol_url,source)
                   VALUES (:id,:name,:series,:printed_total,:total,:release_date,:ptcgo_code,
                           :logo_url,:symbol_url,:source)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, series=excluded.series,
                     printed_total=excluded.printed_total, total=excluded.total,
                     release_date=excluded.release_date, ptcgo_code=excluded.ptcgo_code,
                     logo_url=excluded.logo_url, symbol_url=excluded.symbol_url,
                     updated_at=datetime('now')""",
                {"source": "pokemontcgio", **s},
            )

    def upsert_cards(self, cards: Iterable[dict]) -> int:
        """Bulk upsert. Never clears image_local — a re-import must not throw away
        the cached image files (external data must not overwrite local state)."""
        rows = []
        for c in cards:
            rows.append({
                "id": c["id"],
                "official_set_id": c["official_set_id"],
                "name": c["name"],
                "number": str(c.get("number") or ""),
                "number_sort": _number_sort(str(c.get("number") or "")),
                "rarity": c.get("rarity"),
                "supertype": c.get("supertype"),
                "subtypes_json": json.dumps(c.get("subtypes") or []),
                "types_json": json.dumps(c.get("types") or []),
                "artist": c.get("artist"),
                "image_small_url": c.get("image_small_url"),
                "image_large_url": c.get("image_large_url"),
                "external_ids_json": json.dumps(c.get("external_ids") or {}),
                "source": c.get("source", "pokemontcgio"),
            })
        if not rows:
            return 0
        with self.tx() as conn:
            conn.executemany(
                """INSERT INTO cards
                     (id,official_set_id,name,number,number_sort,rarity,supertype,
                      subtypes_json,types_json,artist,image_small_url,image_large_url,
                      external_ids_json,source)
                   VALUES (:id,:official_set_id,:name,:number,:number_sort,:rarity,:supertype,
                           :subtypes_json,:types_json,:artist,:image_small_url,:image_large_url,
                           :external_ids_json,:source)
                   ON CONFLICT(id) DO UPDATE SET
                     official_set_id=excluded.official_set_id, name=excluded.name,
                     number=excluded.number, number_sort=excluded.number_sort,
                     rarity=excluded.rarity, supertype=excluded.supertype,
                     subtypes_json=excluded.subtypes_json, types_json=excluded.types_json,
                     artist=excluded.artist, image_small_url=excluded.image_small_url,
                     image_large_url=excluded.image_large_url,
                     external_ids_json=excluded.external_ids_json,
                     updated_at=datetime('now')""",
                rows,
            )
        return len(rows)

    def set_card_image_local(self, card_id: str, rel_path: str) -> None:
        with self.tx() as c:
            c.execute("UPDATE cards SET image_local=? WHERE id=?", (rel_path, card_id))

    def set_card_market_url(self, card_id: str, url: str) -> None:
        """Store the resolved Cardmarket product URL alongside the other external ids."""
        with self.tx() as c:
            c.execute(
                "UPDATE cards SET external_ids_json = "
                "json_set(COALESCE(external_ids_json, '{}'), '$.cardmarket_direct', ?), "
                "updated_at = datetime('now') WHERE id = ?",
                (url, card_id),
            )

    def set_card_market_urls(self, pairs: list[tuple[str, str]]) -> int:
        """Store many resolved URLs in ONE transaction.

        The per-card version below is fine for a handful, but a full catalog run
        is 1100+ writes: taken one transaction at a time it holds the write lock
        almost continuously and starves concurrent reads, which makes the web UI
        hang while an import is running.
        """
        if not pairs:
            return 0
        with self.tx() as c:
            c.executemany(
                "UPDATE cards SET external_ids_json = "
                "json_set(COALESCE(external_ids_json, '{}'), '$.cardmarket_direct', ?), "
                "updated_at = datetime('now') WHERE id = ?",
                [(url, cid) for cid, url in pairs],
            )
        return len(pairs)

    def count_market_urls(self) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM cards "
            "WHERE json_extract(external_ids_json, '$.cardmarket_direct') IS NOT NULL"
        ) or 0

    def cards_missing_local_image(self, limit: int = 5000) -> list[dict]:
        return self._all(
            "SELECT id, image_small_url FROM cards "
            "WHERE image_local IS NULL AND image_small_url IS NOT NULL LIMIT ?", (limit,)
        )

    def get_card(self, card_id: str) -> dict | None:
        return self._one(
            "SELECT c.*, os.name AS set_name, os.ptcgo_code "
            "FROM cards c JOIN official_sets os ON os.id=c.official_set_id WHERE c.id=?",
            (card_id,),
        )

    def list_official_sets(self) -> list[dict]:
        return self._all("SELECT * FROM official_sets ORDER BY release_date")

    def search_cards(self, q: str = "", official_set: str = "", rarity: str = "",
                     page: int = 1, page_size: int = 60) -> tuple[list[dict], int]:
        where, params = ["1=1"], []
        if q:
            where.append("(c.name LIKE ? OR c.number LIKE ? OR c.id LIKE ?)")
            params += [f"%{q}%", f"{q}%", f"%{q}%"]
        if official_set:
            where.append("c.official_set_id = ?")
            params.append(official_set)
        if rarity:
            where.append("c.rarity = ?")
            params.append(rarity)
        w = " AND ".join(where)
        total = self._scalar(f"SELECT COUNT(*) FROM cards c WHERE {w}", params) or 0
        rows = self._all(
            f"""SELECT c.*, os.name AS set_name FROM cards c
                JOIN official_sets os ON os.id=c.official_set_id
                WHERE {w} ORDER BY os.release_date, c.number_sort
                LIMIT ? OFFSET ?""",
            params + [page_size, (page - 1) * page_size],
        )
        return rows, total

    def count_cards(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM cards") or 0

    # ------------------------------------------------------------- printings
    def printings_for_card(self, card_id: str) -> list[dict]:
        """Every catalog printing of the logical card this card belongs to.

        Returns [] when the card has no siblings — the UI then has nothing to ask
        about and skips the edition selector entirely.
        """
        return self._all(
            """SELECT p.*, c.name, c.number, c.rarity, c.image_local,
                      c.image_small_url, os.release_date
               FROM card_printings p
               JOIN cards c ON c.id = p.card_id
               JOIN official_sets os ON os.id = p.official_set_id
               WHERE p.print_group = (SELECT print_group FROM card_printings
                                       WHERE card_id = ? LIMIT 1)
               ORDER BY os.release_date""",
            (card_id,),
        )

    def get_printing(self, printing_id: int) -> dict | None:
        return self._one("SELECT * FROM card_printings WHERE id = ?", (printing_id,))

    def count_printings(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM card_printings") or 0

    # --------------------------------------------------------- personal sets
    def upsert_collection_set(self, s: dict) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO collection_sets(id,name,description,group_name,position,rules_json)
                   VALUES (:id,:name,:description,:group_name,:position,:rules_json)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, description=excluded.description,
                     group_name=excluded.group_name, position=excluded.position,
                     rules_json=excluded.rules_json, updated_at=datetime('now')""",
                {"description": None, "group_name": None, "position": 0, "rules_json": None, **s},
            )

    def get_collection_set(self, set_id: str) -> dict | None:
        return self._one("SELECT * FROM collection_sets WHERE id=?", (set_id,))

    def list_collection_sets(self) -> list[dict]:
        return self._all("SELECT * FROM collection_sets ORDER BY position, name")

    def delete_collection_set(self, set_id: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM collection_sets WHERE id=?", (set_id,))

    # ----------------------------------------------------------- hidden sets
    def set_hidden(self, set_id: str, hidden: bool) -> None:
        """Hide or show a set. Hiding keeps everything; it only marks the set so
        it drops off the Sets page and out of the completion totals."""
        with self.tx() as c:
            if hidden:
                c.execute("INSERT OR IGNORE INTO set_hidden(set_id) VALUES (?)",
                          (set_id,))
            else:
                c.execute("DELETE FROM set_hidden WHERE set_id=?", (set_id,))

    # ------------------------------------------------- loose completion (exp.)
    def set_loose_completion(self, set_id: str, on: bool) -> None:
        """Turn 'any owned printing counts' on or off for one set."""
        with self.tx() as c:
            if on:
                c.execute("INSERT OR IGNORE INTO set_loose_completion(set_id) "
                          "VALUES (?)", (set_id,))
            else:
                c.execute("DELETE FROM set_loose_completion WHERE set_id=?",
                          (set_id,))

    def is_loose_completion(self, set_id: str) -> bool:
        return self._one("SELECT 1 AS x FROM set_loose_completion WHERE set_id=?",
                         (set_id,)) is not None

    def list_hidden_sets(self) -> list[dict]:
        """Hidden sets, with the logo, so Mantenimiento can list and un-hide them."""
        return self._all(
            """SELECT s.id, s.name, h.hidden_at,
                      COALESCE(NULLIF(os.logo_url, ''), me.logo) AS logo_url
                 FROM set_hidden h
                 JOIN collection_sets s ON s.id = h.set_id
                 LEFT JOIN official_sets os
                        ON os.id = json_extract(s.rules_json, '$.include_sets[0]')
                 LEFT JOIN set_episodes se ON se.official_set_id = os.id
                 LEFT JOIN market_episodes me ON me.episode_id = se.episode_id
                ORDER BY os.release_date, s.name""")

    def set_cards_with_state(self, set_id: str) -> list[dict]:
        """Every card in this set's source sets, tagged for the set view.

        The whole set is shown, not just the rule's slots. Each card carries:
          collecting — is it part of what you are trying to complete (a slot)?
          owned      — do you have it, in any variant?
        A rarity rule ("sin holos") flips `collecting` in bulk; the per-card
        toggle overrides it. `owned` is independent of both.
        """
        import json as _json

        cset = self.get_collection_set(set_id)
        if not cset:
            return []
        sources = (_json.loads(cset.get("rules_json") or "{}").get("include_sets") or [])
        if not sources:
            return []

        # Loose completion: a card counts as owned when any same-name printing is
        # held (a Jungle Pikachu marks the Base Set Pikachu owned). Strict: only
        # this exact card_id. Same rule the completion count uses, so the grid and
        # the progress bar agree.
        if self.is_loose_completion(set_id):
            owned_expr = ("COALESCE((SELECT SUM(i.quantity) FROM collection_items i "
                          "JOIN cards ci ON ci.id = i.card_id "
                          "WHERE ci.name = c.name), 0)")
        else:
            owned_expr = ("COALESCE((SELECT SUM(i.quantity) FROM collection_items i "
                          "WHERE i.card_id = c.id), 0)")

        marks = ",".join("?" * len(sources))
        return self._all(
            f"""SELECT c.id, c.name, c.number, c.number_sort, c.rarity,
                       c.image_small_url, c.image_local, c.official_set_id,
                       EXISTS (SELECT 1 FROM set_slot_cards m
                                WHERE m.set_id = ? AND m.card_id = c.id) AS collecting,
                       {owned_expr} AS owned_qty
                  FROM cards c
                 WHERE c.official_set_id IN ({marks})
                 ORDER BY c.number_sort, c.number""",
            (set_id, *sources))

    def replace_rule_slots(self, set_id: str, slots: list[dict]) -> int:
        """Re-materialise rule-built slots. Manual slots and manual member edits survive
        — a catalog refresh must not wipe hand curation."""
        with self.tx() as c:
            manual_cards = {
                r["card_id"] for r in c.execute(
                    "SELECT ssc.card_id FROM set_slot_cards ssc "
                    "JOIN set_slots s ON s.id=ssc.slot_id "
                    "WHERE s.set_id=? AND s.source='manual'", (set_id,)
                ).fetchall()
            }
            c.execute("DELETE FROM set_slots WHERE set_id=? AND source='rule'", (set_id,))
            max_pos = c.execute(
                "SELECT COALESCE(MAX(position), -1) FROM set_slots WHERE set_id=?", (set_id,)
            ).fetchone()[0]
            written = 0
            for i, slot in enumerate(slots):
                members = [cid for cid in slot["cards"] if cid not in manual_cards]
                if not members:
                    continue
                cur = c.execute(
                    "INSERT INTO set_slots(set_id,position,label,display_card_id,source) "
                    "VALUES (?,?,?,?,'rule')",
                    (set_id, slot.get("position", i), slot.get("label"),
                     slot.get("display_card_id") or members[0]),
                )
                slot_id = cur.lastrowid
                c.executemany(
                    "INSERT OR IGNORE INTO set_slot_cards(slot_id,card_id,set_id) VALUES (?,?,?)",
                    [(slot_id, cid, set_id) for cid in members],
                )
                written += 1
            _ = max_pos
            return written

    def get_set_slots(self, set_id: str) -> list[dict]:
        """Slots with ownership state. A slot counts as owned if ANY member card is held —
        this is what makes reprints/variants collapse to one logical card."""
        return self._all(
            """SELECT sl.id AS slot_id, sl.position, sl.source,
                      COALESCE(sl.label, c.name) AS label,
                      c.id AS card_id, c.name, c.number, c.number_sort, c.rarity,
                      c.image_small_url, c.image_local, c.official_set_id,
                      COALESCE(t.target, 1) AS target,
                      -- Three states, not two. Holding a single copy takes the
                      -- card out of the greyed-out treatment; reaching the target
                      -- is what earns the tick.
                      (SELECT COALESCE(SUM(i.quantity), 0) FROM set_slot_cards m
                        JOIN collection_items i ON i.card_id = m.card_id
                       WHERE m.slot_id = sl.id) > 0 AS owned,
                      (SELECT COALESCE(SUM(i.quantity), 0) FROM set_slot_cards m
                        JOIN collection_items i ON i.card_id = m.card_id
                       WHERE m.slot_id = sl.id) >= COALESCE(t.target, 1) AS complete,
                      (SELECT COALESCE(SUM(i.quantity), 0) FROM set_slot_cards m
                        JOIN collection_items i ON i.card_id = m.card_id
                       WHERE m.slot_id = sl.id) AS quantity,
                      (SELECT COUNT(*) FROM set_slot_cards m WHERE m.slot_id = sl.id) AS member_count
               FROM set_slots sl
               LEFT JOIN cards c ON c.id = sl.display_card_id
               LEFT JOIN card_targets t ON t.card_id = sl.display_card_id
               WHERE sl.set_id = ?
               ORDER BY sl.position, c.number_sort""",
            (set_id,),
        )

    def set_progress(self, set_id: str | None = None) -> list[dict]:
        """Completion per personal set. COUNT(DISTINCT slot) on the owned side is what
        stops Charizard-holo + Charizard-non-holo counting twice.

        Listing all sets skips the hidden ones, so they leave both the Sets page
        and every completion total (dashboard, snapshots) at once. Asking for one
        set by id returns it either way — a hidden set is still viewable, e.g. to
        confirm before un-hiding.
        """
        if set_id:
            where = "WHERE s.id = ?"
            params: tuple = (set_id,)
        else:
            where = ("WHERE NOT EXISTS "
                     "(SELECT 1 FROM set_hidden h WHERE h.set_id = s.id)")
            params = ()
        # A slot counts once the copies held reach its target. With no target set
        # the target is 1, which is the same "do I have one" question as before.
        # The set's series and release date come from the catalogue set the rule
        # is built on (its first include_sets entry). They drive the Sets view:
        # grouped by series (Base / Gym / Neo / …), ordered oldest-first. Both
        # are catalogue facts, so a set files itself — no manual group to keep.
        return self._all(
            f"""SELECT s.id, s.name, s.group_name, s.position,
                       os.series AS series, os.release_date AS release_date,
                       -- The set logo: the one stored at import, or the cached
                       -- episode logo when import stored none (tcggo omits it on
                       -- a few, but the catalogue sync has them all).
                       COALESCE(NULLIF(os.logo_url, ''), me.logo) AS logo_url,
                       COUNT(DISTINCT sl.id) AS target,
                       COUNT(DISTINCT CASE WHEN sl.held > 0 THEN sl.id END) AS owned,
                       COUNT(DISTINCT CASE WHEN sl.held >= sl.want THEN sl.id END) AS complete,
                       -- Copy progress caps each slot at its target so a pile of
                       -- spares cannot push the set past 100%.
                       COALESCE(SUM(MIN(sl.held, sl.want)), 0) AS copies_held,
                       COALESCE(SUM(sl.want), 0) AS copies_target
                FROM collection_sets s
                LEFT JOIN official_sets os
                       ON os.id = json_extract(s.rules_json, '$.include_sets[0]')
                LEFT JOIN set_episodes se ON se.official_set_id = os.id
                LEFT JOIN market_episodes me ON me.episode_id = se.episode_id
                LEFT JOIN (
                    SELECT sl.id, sl.set_id,
                           COALESCE(t.target, 1) AS want,
                           -- Strict: only the set's own printing counts. Loose
                           -- (a set_loose_completion row): any owned card of the
                           -- same name as a slot member counts — a Jungle Pikachu
                           -- fills the Base Set Pikachu slot.
                           CASE WHEN lc.set_id IS NOT NULL THEN
                             (SELECT COALESCE(SUM(i.quantity), 0)
                                FROM collection_items i
                                JOIN cards ci ON ci.id = i.card_id
                               WHERE ci.name IN (
                                   SELECT c2.name FROM set_slot_cards m2
                                   JOIN cards c2 ON c2.id = m2.card_id
                                  WHERE m2.slot_id = sl.id))
                           ELSE
                             (SELECT COALESCE(SUM(i.quantity), 0)
                                FROM set_slot_cards m
                                JOIN collection_items i ON i.card_id = m.card_id
                               WHERE m.slot_id = sl.id)
                           END AS held
                      FROM set_slots sl
                      LEFT JOIN card_targets t ON t.card_id = sl.display_card_id
                      LEFT JOIN set_loose_completion lc ON lc.set_id = sl.set_id
                ) sl ON sl.set_id = s.id
                {where}
                GROUP BY s.id, s.name, s.group_name, s.position, os.series,
                         os.release_date, os.logo_url, me.logo
                ORDER BY os.release_date, s.name""",
            params,
        )

    def missing_slots(self, set_id: str, sort: str = "number") -> list[dict]:
        order = {
            "number": "c.number_sort",
            "name": "COALESCE(sl.label, c.name)",
            "rarity": "c.rarity, c.number_sort",
        }.get(sort, "c.number_sort")
        # Short of the target counts as missing, and the shortfall is reported so
        # the wishlist can say how many are still needed rather than just "none".
        return self._all(
            f"""SELECT sl.id AS slot_id, COALESCE(sl.label, c.name) AS label,
                       c.id AS card_id, c.number, c.rarity, c.image_small_url,
                       c.image_local,
                       COALESCE(t.target, 1) AS target,
                       (SELECT COALESCE(SUM(i.quantity), 0) FROM set_slot_cards m
                         JOIN collection_items i ON i.card_id = m.card_id
                        WHERE m.slot_id = sl.id) AS held,
                       COALESCE(t.target, 1) - (
                         SELECT COALESCE(SUM(i.quantity), 0) FROM set_slot_cards m
                          JOIN collection_items i ON i.card_id = m.card_id
                         WHERE m.slot_id = sl.id) AS still_needed,
                       (SELECT COALESCE(SUM(i.quantity), 0) FROM set_slot_cards m
                         JOIN collection_items i ON i.card_id = m.card_id
                        WHERE m.slot_id = sl.id) = 0 AS missing_entirely
                FROM set_slots sl
                LEFT JOIN cards c ON c.id = sl.display_card_id
                LEFT JOIN card_targets t ON t.card_id = sl.display_card_id
                WHERE sl.set_id = ?
                  AND (SELECT COALESCE(SUM(i.quantity), 0) FROM set_slot_cards m
                        JOIN collection_items i ON i.card_id = m.card_id
                       WHERE m.slot_id = sl.id) < COALESCE(t.target, 1)
                ORDER BY {order}""",
            (set_id,),
        )

    # ------------------------------------------------------------ collection
    def upsert_collection_item(self, item: dict, mode: str = "add") -> dict:
        """Insert or update. On the unique combination (card, variant, condition, language)
        `add` increments the quantity instead of creating a duplicate row — without this
        the physical count silently doubles."""
        payload = {
            "card_id": item["card_id"],
            "variant": item.get("variant", "normal"),
            "condition": item.get("condition") or DEFAULT_CONDITION,
            "language": item.get("language", "es"),
            "market_product_id": item.get("market_product_id"),
            "quantity": int(item.get("quantity", 1)),
            "printing_id": item.get("printing_id"),
            "notes": item.get("notes"),
        }
        conflict = ("quantity = collection_items.quantity + excluded.quantity"
                    if mode == "add" else "quantity = excluded.quantity")
        with self.tx() as c:
            c.execute(
                f"""INSERT INTO collection_items
                      (card_id,variant,condition,language,quantity,printing_id,
                       market_product_id,notes)
                    VALUES (:card_id,:variant,:condition,:language,:quantity,
                            :printing_id,:market_product_id,:notes)
                    ON CONFLICT(card_id,variant,condition,language) DO UPDATE SET
                      {conflict}, notes=COALESCE(excluded.notes, collection_items.notes),
                      printing_id=COALESCE(excluded.printing_id,
                                           collection_items.printing_id),
                      market_product_id=COALESCE(excluded.market_product_id,
                                                 collection_items.market_product_id),
                      updated_at=datetime('now')""",
                payload,
            )
            row = c.execute(
                "SELECT * FROM collection_items WHERE card_id=? AND variant=? "
                "AND condition=? AND language=?",
                (payload["card_id"], payload["variant"], payload["condition"], payload["language"]),
            ).fetchone()
        return dict(row)

    def update_collection_item(self, item_id: int, fields: dict) -> dict | None:
        allowed = {"variant", "condition", "language", "quantity",
                   "printing_id", "notes"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return self.get_collection_item(item_id)
        clause = ", ".join(f"{k}=:{k}" for k in sets)
        sets["id"] = item_id
        with self.tx() as c:
            c.execute(
                f"UPDATE collection_items SET {clause}, updated_at=datetime('now') WHERE id=:id",
                sets,
            )
        return self.get_collection_item(item_id)

    def get_collection_item(self, item_id: int) -> dict | None:
        row = self._one(
            "SELECT i.id, i.card_id, i.variant, i.condition, i.language, i.quantity, i.printing_id, i.market_product_id, i.notes, i.created_at, i.updated_at, c.name, c.number, c.rarity, c.official_set_id, "
            "c.image_small_url, c.image_local, c.external_ids_json, "
            "COALESCE(cr.rating, 0) AS rating "
            "FROM collection_items i JOIN cards c ON c.id=i.card_id "
            "LEFT JOIN card_ratings cr ON cr.card_id = i.card_id WHERE i.id=?",
            (item_id,),
        )
        if row:
            row["photos"] = self.get_photos(item_id)
        return row

    def delete_collection_item(self, item_id: int) -> list[str]:
        """Returns the filenames the caller must unlink — the repo does not touch disk."""
        photos = self.get_photos(item_id)
        with self.tx() as c:
            c.execute("DELETE FROM collection_items WHERE id=?", (item_id,))
        files = []
        for p in photos:
            files.append(p["filename"])
            if p.get("thumb_filename"):
                files.append(p["thumb_filename"])
        return files

    def items_by_card(self, card_id: str) -> list[dict]:
        rows = self._all(
            "SELECT i.id, i.card_id, i.variant, i.condition, i.language, i.quantity, i.printing_id, i.market_product_id, i.notes, i.created_at, i.updated_at, c.name, c.number, c.rarity, c.official_set_id, "
            "c.image_small_url, c.image_local, c.external_ids_json, "
            "os.name AS printing_name, COALESCE(cr.rating, 0) AS rating "
            "FROM collection_items i JOIN cards c ON c.id = i.card_id "
            "JOIN official_sets os ON os.id = c.official_set_id "
            "LEFT JOIN card_ratings cr ON cr.card_id = i.card_id "
            "WHERE i.card_id=? "
            "ORDER BY CASE i.condition WHEN 'M/NM' THEN 0 WHEN 'EX' THEN 1 "
            "WHEN 'GD' THEN 2 WHEN 'PL' THEN 3 ELSE 4 END, i.variant",
            (card_id,),
        )
        for r in rows:
            r["photos"] = self.get_photos(r["id"])
        return rows

    def list_collection(self, *, q: str = "", set_id: str = "", condition: str = "",
                        variant: str = "", language: str = "", rarity: str = "",
                        card_type: str = "", edition: str = "",
                        min_quantity: int | None = None,
                        rating: int | None = None, rating_min: int | None = None,
                        rating_max: int | None = None,
                        sort: str = "set", page: int = 1, page_size: int = 60
                        ) -> tuple[list[dict], int]:
        where, params = ["1=1"], []
        if q:
            where.append("(c.name LIKE ? OR c.number LIKE ? OR c.id LIKE ?)")
            params += [f"%{q}%", f"{q}%", f"%{q}%"]
        if set_id:
            where.append("EXISTS (SELECT 1 FROM set_slot_cards m WHERE m.card_id=i.card_id "
                         "AND m.set_id=?)")
            params.append(set_id)
        for col, val in (("condition", condition), ("variant", variant),
                         ("language", language)):
            if val:
                where.append(f"i.{col} = ?")
                params.append(val)
        if rarity:
            where.append("c.rarity = ?")
            params.append(rarity)
        # Type comes from the catalog's JSON list. LIKE on the quoted value is
        # exact enough here: types are single words and cannot be substrings of
        # one another ("Fire" never appears inside another type name).
        if card_type:
            where.append("c.types_json LIKE ?")
            params.append(f'%"{card_type}"%')
        # Edition maps onto the physical variant. Unlimited is "neither of the
        # early-run markings" rather than a stored value, because that is what it
        # means: an ordinary copy from the open print run.
        if edition == "first_edition":
            where.append("i.variant = 'first_edition'")
        elif edition == "unlimited":
            where.append("i.variant NOT IN ('first_edition', 'shadowless')")
        # Total copies held of the card, not of this one row — "2 or more" is a
        # question about the card, and three copies split across a holo row and a
        # normal row is three copies.
        if min_quantity is not None:
            where.append("(SELECT COALESCE(SUM(q.quantity), 0) FROM collection_items q "
                         "WHERE q.card_id = i.card_id) >= ?")
            params.append(int(min_quantity))
        # COALESCE because an unranked card has no card_ratings row at all.
        if rating is not None:
            where.append("COALESCE(cr.rating, 0) = ?")
            params.append(int(rating))
        # Ranges drive the Top Tier / Favourites quick filters.
        if rating_min is not None:
            where.append("COALESCE(cr.rating, 0) >= ?")
            params.append(int(rating_min))
        if rating_max is not None:
            where.append("COALESCE(cr.rating, 0) <= ?")
            params.append(int(rating_max))
        w = " AND ".join(where)
        order = {
            "set": "os.release_date, c.number_sort",
            "rating": "COALESCE(cr.rating, 0) DESC, c.name",
            "name": "c.name",
            "number": "c.number_sort",
            "rarity": "c.rarity, c.number_sort",
            "recent": "i.created_at DESC",
            "quantity": "i.quantity DESC",
        }.get(sort, "os.release_date, c.number_sort")
        total = self._scalar(
            f"SELECT COUNT(*) FROM collection_items i JOIN cards c ON c.id=i.card_id "
            f"LEFT JOIN card_ratings cr ON cr.card_id = i.card_id WHERE {w}",
            params,
        ) or 0
        rows = self._all(
            f"""SELECT i.id, i.card_id, i.variant, i.condition, i.language, i.quantity, i.printing_id, i.market_product_id, i.notes, i.created_at, i.updated_at, c.name, c.number, c.rarity, c.official_set_id,
                       c.image_small_url, c.image_local, c.external_ids_json,
                       os.name AS set_name, os.name AS printing_name,
                       COALESCE(cr.rating, 0) AS rating
                FROM collection_items i
                JOIN cards c ON c.id = i.card_id
                JOIN official_sets os ON os.id = c.official_set_id
                LEFT JOIN card_ratings cr ON cr.card_id = i.card_id
                WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?""",
            params + [page_size, (page - 1) * page_size],
        )
        for r in rows:
            r["photos"] = self.get_photos(r["id"])
        return rows, total

    def list_slots_with_ownership(
            self, *, q: str = "", set_id: str = "", condition: str = "",
            variant: str = "", language: str = "", rarity: str = "",
            card_type: str = "", edition: str = "",
            min_quantity: int | None = None,
            rating: int | None = None, rating_min: int | None = None,
            rating_max: int | None = None,
            sort: str = "set", page: int = 1, page_size: int = 60
    ) -> tuple[list[dict], int]:
        """Every card in the personal sets, owned or not ("All" view mode).

        One row per owned collection item, or a single placeholder row for a slot
        nothing satisfies. The ownership join goes through a subquery rather than
        joining set_slot_cards directly: a slot can group several catalog cards,
        and a direct join would emit one duplicate placeholder per member card
        for the slots that are not owned at all.

        Filters that describe a physical copy — condition, variant, language,
        rating — can only match owned rows, so applying any of them drops
        placeholders. That is the intended behaviour for the Hall of Fame filter
        and is equally right for the others.
        """
        where, params = ["1=1"], []
        if set_id:
            where.append("sl.set_id = ?")
            params.append(set_id)
        if q:
            where.append("(c.name LIKE ? OR c.number LIKE ? OR c.id LIKE ?)")
            params += [f"%{q}%", f"{q}%", f"%{q}%"]
        if rarity:
            where.append("c.rarity = ?")
            params.append(rarity)
        for col, val in (("condition", condition), ("variant", variant),
                         ("language", language)):
            if val:
                where.append(f"i.{col} = ?")
                params.append(val)
        if card_type:
            where.append("c.types_json LIKE ?")
            params.append(f'%"{card_type}"%')
        # Edition describes a copy in hand, so it drops placeholders — unlike the
        # rank below, which belongs to the card.
        if edition == "first_edition":
            where.append("i.variant = 'first_edition'")
        elif edition == "unlimited":
            where.append("i.variant IS NOT NULL "
                         "AND i.variant NOT IN ('first_edition', 'shadowless')")
        if min_quantity is not None:
            where.append("(SELECT COALESCE(SUM(q.quantity), 0) FROM collection_items q "
                         "WHERE q.card_id = COALESCE(i.card_id, c.id)) >= ?")
            params.append(int(min_quantity))

        # No ownership condition. The rank is a judgement about the card, so a
        # card you have ranked but not yet acquired must still match.
        if rating is not None:
            where.append("COALESCE(cr.rating, 0) = ?")
            params.append(int(rating))
        if rating_min is not None:
            where.append("COALESCE(cr.rating, 0) >= ?")
            params.append(int(rating_min))
        if rating_max is not None:
            where.append("COALESCE(cr.rating, 0) <= ?")
            params.append(int(rating_max))
        w = " AND ".join(where)

        # Placeholders have no collection row, so anything ordering by an item
        # column must fall back to a card column or they sort unpredictably.
        order = {
            "set": "cs.position, c.number_sort",
            "name": "COALESCE(sl.label, c.name)",
            "number": "c.number_sort",
            "rarity": "c.rarity, c.number_sort",
            "rating": "COALESCE(cr.rating, -1) DESC, c.number_sort",
            "quantity": "COALESCE(i.quantity, 0) DESC, c.number_sort",
            "owned": "owned DESC, c.number_sort",
            "recent": "COALESCE(i.created_at, '') DESC, c.number_sort",
        }.get(sort, "cs.position, c.number_sort")

        base = f"""
            FROM set_slots sl
            JOIN collection_sets cs ON cs.id = sl.set_id
            LEFT JOIN cards c ON c.id = sl.display_card_id
            LEFT JOIN official_sets os ON os.id = c.official_set_id
            LEFT JOIN collection_items i
                   ON i.card_id IN (SELECT card_id FROM set_slot_cards
                                     WHERE slot_id = sl.id)
            -- Ranks belong to the card, so a slot has one whether or not a copy
            -- is in hand. Joining on i.card_id gave placeholders a NULL rank and
            -- made them invisible to the Hall of Fame filter — you could rank a
            -- card you were still hunting for and then never find it again.
            LEFT JOIN card_ratings cr ON cr.card_id = COALESCE(i.card_id, c.id)
            WHERE {w}"""

        total = self._scalar(f"SELECT COUNT(*) {base}", params) or 0
        rows = self._all(
            f"""SELECT sl.id AS slot_id, COALESCE(sl.label, c.name) AS label,
                       cs.id AS personal_set_id, cs.name AS personal_set_name,
                       c.id AS card_id, c.name, c.number, c.number_sort, c.rarity,
                       c.official_set_id, c.image_small_url, c.image_local,
                       c.external_ids_json, os.name AS set_name,
                       i.id AS id, i.variant, i.condition, i.language,
                       i.quantity, i.notes,
                       COALESCE(cr.rating, 0) AS rating,
                       i.created_at, i.updated_at,
                       CASE WHEN i.id IS NULL THEN 0 ELSE 1 END AS owned
                {base} ORDER BY {order} LIMIT ? OFFSET ?""",
            params + [page_size, (page - 1) * page_size],
        )
        for r in rows:
            r["owned"] = bool(r["owned"])
            r["photos"] = self.get_photos(r["id"]) if r["id"] else []
        return rows, total

    def slots_ownership_totals(self, set_id: str = "") -> dict:
        where = "WHERE sl.set_id = ?" if set_id else ""
        params = (set_id,) if set_id else ()
        return self._one(
            f"""SELECT COUNT(DISTINCT sl.id) AS slots,
                       COUNT(DISTINCT CASE WHEN i.id IS NOT NULL THEN sl.id END) AS owned_slots
                FROM set_slots sl
                LEFT JOIN collection_items i
                       ON i.card_id IN (SELECT card_id FROM set_slot_cards
                                         WHERE slot_id = sl.id)
                {where}""", params
        ) or {"slots": 0, "owned_slots": 0}

    def collection_totals(self) -> dict:
        """Unique logical cards vs physical copies: 67 cartas / 94 físicas."""
        return self._one(
            "SELECT COUNT(DISTINCT card_id) AS unique_cards, "
            "COALESCE(SUM(quantity), 0) AS physical_cards, "
            "COUNT(*) AS item_rows FROM collection_items"
        ) or {"unique_cards": 0, "physical_cards": 0, "item_rows": 0}

    def set_card_rating(self, card_id: str, rating: int) -> None:
        """0 clears the rank rather than storing it — 0 means unranked, and a row
        saying so is indistinguishable from no row while making every average and
        count query carry a `rating > 0` guard."""
        with self.tx() as c:
            if int(rating) <= 0:
                c.execute("DELETE FROM card_ratings WHERE card_id = ?", (card_id,))
            else:
                c.execute(
                    "INSERT INTO card_ratings(card_id, rating) VALUES (?,?) "
                    "ON CONFLICT(card_id) DO UPDATE SET rating=excluded.rating, "
                    "updated_at=datetime('now')",
                    (card_id, int(rating)),
                )

    def set_card_target(self, card_id: str, target: int) -> None:
        """A target of 1 is stored as absence — it is the default, and a row
        saying so would just be noise to keep in sync."""
        with self.tx() as c:
            if int(target) <= 1:
                c.execute("DELETE FROM card_targets WHERE card_id = ?", (card_id,))
            else:
                c.execute(
                    "INSERT INTO card_targets(card_id, target) VALUES (?,?) "
                    "ON CONFLICT(card_id) DO UPDATE SET target=excluded.target, "
                    "updated_at=datetime('now')",
                    (card_id, int(target)),
                )

    def get_card_target(self, card_id: str) -> int:
        return self._scalar(
            "SELECT target FROM card_targets WHERE card_id = ?", (card_id,)) or 1

    def get_card_rating(self, card_id: str) -> int:
        return self._scalar(
            "SELECT rating FROM card_ratings WHERE card_id = ?", (card_id,)) or 0

    def rating_stats(self) -> dict:
        """Hall of Fame summary.

        The average deliberately excludes rating 0. Zero means "not ranked yet",
        not "ranked zero", so averaging it in would drag the number toward 0 and
        make it say more about how much ranking is left to do than about the
        collection.
        """
        # Counted over cards, not collection rows: two variants of one card are
        # one opinion, and counting them twice would skew the average toward
        # whatever the user happens to own duplicates of.
        row = self._one(
            """SELECT COUNT(*) AS rated,
                      COALESCE(AVG(r.rating), 0) AS average,
                      COALESCE(MAX(r.rating), 0) AS best
               FROM card_ratings r
               WHERE r.rating > 0
                 AND EXISTS (SELECT 1 FROM collection_items i WHERE i.card_id = r.card_id)"""
        ) or {}
        dist = {r["rating"]: r["n"] for r in self._all(
            """SELECT r.rating, COUNT(*) AS n FROM card_ratings r
               WHERE r.rating > 0
                 AND EXISTS (SELECT 1 FROM collection_items i WHERE i.card_id = r.card_id)
               GROUP BY r.rating""")}
        owned_cards = self._scalar(
            "SELECT COUNT(DISTINCT card_id) FROM collection_items") or 0
        return {
            "rated": row.get("rated", 0) or 0,
            "unrated": max(0, owned_cards - (row.get("rated", 0) or 0)),
            "average": round(row.get("average", 0) or 0, 2),
            "best": row.get("best", 0) or 0,
            "top_tier": self._scalar(
                """SELECT COUNT(*) FROM card_ratings r WHERE r.rating >= 7
                   AND EXISTS (SELECT 1 FROM collection_items i
                                WHERE i.card_id = r.card_id)""") or 0,
            "distribution": {str(k): v for k, v in sorted(dist.items())},
        }

    def owned_card_variants(self) -> list[dict]:
        """Distinct (card, variant) pairs actually held — the price job's work list.
        Spec §11/§30: one lookup per card/variant, never one per physical copy."""
        return self._all(
            """SELECT card_id, variant, MAX(market_product_id) AS market_product_id
                 FROM collection_items GROUP BY card_id, variant ORDER BY card_id"""
        )

    # ---------------------------------------------------------------- photos
    def add_photo(self, item_id: int, p: dict) -> dict:
        with self.tx() as c:
            has_primary = c.execute(
                "SELECT COUNT(*) FROM collection_photos WHERE item_id=? AND is_primary=1",
                (item_id,),
            ).fetchone()[0]
            pos = c.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM collection_photos WHERE item_id=?",
                (item_id,),
            ).fetchone()[0]
            cur = c.execute(
                """INSERT INTO collection_photos
                     (item_id,filename,thumb_filename,width,height,bytes,is_primary,position)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (item_id, p["filename"], p.get("thumb_filename"), p.get("width"),
                 p.get("height"), p.get("bytes"), 0 if has_primary else 1, pos),
            )
            row = c.execute("SELECT * FROM collection_photos WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def get_photos(self, item_id: int) -> list[dict]:
        return self._all(
            "SELECT * FROM collection_photos WHERE item_id=? ORDER BY is_primary DESC, position",
            (item_id,),
        )

    def best_photos_for_cards(self, card_ids: Sequence[str]) -> dict[str, dict]:
        """Best photo to represent each card in a grid.

        A card owned in several conditions should show the nicest copy, not
        whichever row happens to sort first — seeing a Damaged scan when a Near
        Mint one exists misrepresents the collection. Ranked by condition, then
        by the primary flag within that condition.

        One query for the whole page rather than one per card.
        """
        if not card_ids:
            return {}
        ids = list(dict.fromkeys(card_ids))
        rows = self._all(
            f"""SELECT i.card_id, i.condition, p.*
                FROM collection_photos p
                JOIN collection_items i ON i.id = p.item_id
                WHERE i.card_id IN ({",".join("?" * len(ids))})
                ORDER BY i.card_id,
                         -- Best condition first. These are the grade keys
                         -- from config.CONDITIONS; a key that is not listed
                         -- sorts last rather than failing, so a rename here
                         -- goes unnoticed unless a test catches it.
                         CASE i.condition WHEN 'M/NM' THEN 0 WHEN 'EX' THEN 1
                                          WHEN 'GD' THEN 2 WHEN 'PL' THEN 3
                                          ELSE 4 END,
                         p.is_primary DESC, p.position""",
            ids,
        )
        best: dict[str, dict] = {}
        for r in rows:
            best.setdefault(r["card_id"], r)      # ORDER BY put the winner first
        return best

    def get_photo(self, photo_id: int) -> dict | None:
        return self._one("SELECT * FROM collection_photos WHERE id=?", (photo_id,))

    def set_primary_photo(self, photo_id: int) -> None:
        with self.tx() as c:
            row = c.execute("SELECT item_id FROM collection_photos WHERE id=?",
                            (photo_id,)).fetchone()
            if not row:
                return
            c.execute("UPDATE collection_photos SET is_primary=0 WHERE item_id=?", (row["item_id"],))
            c.execute("UPDATE collection_photos SET is_primary=1 WHERE id=?", (photo_id,))

    def delete_photo(self, photo_id: int) -> list[str]:
        p = self.get_photo(photo_id)
        if not p:
            return []
        with self.tx() as c:
            c.execute("DELETE FROM collection_photos WHERE id=?", (photo_id,))
            # keep exactly one primary per item
            c.execute(
                "UPDATE collection_photos SET is_primary=1 WHERE id = ("
                "  SELECT id FROM collection_photos WHERE item_id=? ORDER BY position LIMIT 1)"
                " AND NOT EXISTS (SELECT 1 FROM collection_photos WHERE item_id=? AND is_primary=1)",
                (p["item_id"], p["item_id"]),
            )
        files = [p["filename"]]
        if p.get("thumb_filename"):
            files.append(p["thumb_filename"])
        return files

    # ---------------------------------------------------------------- prices
    def upsert_price(self, card_id: str, variant: str, source: str, currency: str,
                     price: float | None, low: float | None, trend: float | None,
                     avg30: float | None, raw: dict | None,
                     variant_key: str | None = None,
                     market_product_id: int | None = None) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO price_cache
                     (card_id,variant,source,currency,price,price_low,price_trend,
                      price_avg30,raw_json,variant_key,market_product_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(card_id,variant,source) DO UPDATE SET
                     currency=excluded.currency, price=excluded.price,
                     price_low=excluded.price_low, price_trend=excluded.price_trend,
                     price_avg30=excluded.price_avg30, raw_json=excluded.raw_json,
                     variant_key=excluded.variant_key,
                     market_product_id=excluded.market_product_id,
                     updated_at=datetime('now')""",
                (card_id, variant, source, currency, price, low, trend, avg30,
                 json.dumps(raw) if raw else None, variant_key, market_product_id),
            )

    def set_manual_price(self, card_id: str, variant: str, price: float | None,
                         currency: str = "EUR") -> None:
        """A price the user typed in. Stored as its own source so a refresh can
        never overwrite it, and so it can be removed to fall back to the feed."""
        with self.tx() as c:
            if price is None:
                c.execute("DELETE FROM price_cache WHERE card_id=? AND variant=? "
                          "AND source='manual'", (card_id, variant))
            else:
                c.execute(
                    """INSERT INTO price_cache
                         (card_id,variant,source,currency,price,variant_key)
                       VALUES (?,?, 'manual', ?, ?, 'manual')
                       ON CONFLICT(card_id,variant,source) DO UPDATE SET
                         price=excluded.price, currency=excluded.currency,
                         updated_at=datetime('now')""",
                    (card_id, variant, currency, float(price)),
                )

    def append_price_history(self, card_id: str, variant: str, source: str,
                             currency: str, price: float | None,
                             captured_on: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO price_history"
                "(card_id,variant,source,currency,price,captured_on) VALUES (?,?,?,?,?,?)",
                (card_id, variant, source, currency, price,
                 captured_on or date.today().isoformat()),
            )

    def get_official_set(self, set_id: str) -> dict | None:
        return self._one("SELECT * FROM official_sets WHERE id=?", (set_id,))

    # ------------------------------------------------------- market episodes
    def remember_episodes(self, episodes: list[dict]) -> int:
        """Keep every set we are told about, so the list fills in as it is used."""
        rows = [{
            "episode_id": e.get("id"), "code": e.get("code"),
            "name": e.get("name") or "", "slug": e.get("slug"),
            "released_at": e.get("released_at"), "logo": e.get("logo"),
            "cards_total": e.get("cards_total"),
        } for e in episodes if e.get("id") and e.get("name")]
        if not rows:
            return 0
        with self.tx() as c:
            c.executemany(
                """INSERT INTO market_episodes(episode_id, code, name, slug,
                       released_at, logo, cards_total, seen_at)
                   VALUES(:episode_id,:code,:name,:slug,:released_at,:logo,
                          :cards_total,datetime('now'))
                   ON CONFLICT(episode_id) DO UPDATE SET
                     code=excluded.code, name=excluded.name, slug=excluded.slug,
                     released_at=excluded.released_at, logo=excluded.logo,
                     cards_total=excluded.cards_total""",
                rows)
        return len(rows)

    def search_known_episodes(self, q: str | None) -> list[dict]:
        """Sets we already know of, with whether they have been imported.

        The match is bidirectional on the name: an episode matches when its name
        contains the query OR the query contains its name. That second half is
        what makes "Base Set" find the set tcggo simply calls "Base" — the typed
        name is longer than the stored one, so a plain contains-search misses
        it. Code is matched the ordinary way.
        """
        sql = """SELECT e.*,
                        (SELECT COUNT(*) FROM market_products m
                          WHERE m.episode_id = e.episode_id) AS products
                   FROM market_episodes e"""
        params: tuple = ()
        if q:
            sql += (" WHERE e.name LIKE ? OR e.code LIKE ?"
                    "    OR ? LIKE '%' || e.name || '%'")
            params = (f"%{q}%", f"%{q}%", q)
        return self._all(sql + " ORDER BY e.released_at DESC", params)

    # -------------------------------------------------------- market products
    def upsert_market_products(self, rows: list[dict]) -> int:
        """Store a set's products. Re-importing refreshes prices in place."""
        if not rows:
            return 0
        with self.tx() as c:
            c.executemany(
                """INSERT INTO market_products(product_id, episode_id, card_id, code,
                       number, name, version, rarity, currency, price, price_low,
                       price_avg30, price_avg7, available, image, market_url,
                       updated_at)
                   VALUES(:product_id,:episode_id,:card_id,:code,:number,:name,
                          :version,:rarity,:currency,:price,:price_low,
                          :price_avg30,:price_avg7,:available,:image,
                          :market_url,datetime('now'))
                   ON CONFLICT(product_id) DO UPDATE SET
                     episode_id=excluded.episode_id, card_id=excluded.card_id,
                     code=excluded.code,
                     number=excluded.number, name=excluded.name,
                     version=excluded.version, rarity=excluded.rarity,
                     currency=excluded.currency, price=excluded.price,
                     price_low=excluded.price_low, price_avg30=excluded.price_avg30,
                     price_avg7=excluded.price_avg7, available=excluded.available,
                     image=excluded.image, market_url=excluded.market_url,
                     updated_at=datetime('now')""",
                rows)
        return len(rows)

    def link_products_to_cards(self, set_id: str, episode_code: str) -> int:
        """Give every product the id of the card it is a version of."""
        with self.tx() as c:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(market_products)")}
            if "card_id" not in cols:
                c.execute("ALTER TABLE market_products ADD COLUMN card_id TEXT")
            cur = c.execute(
                """UPDATE market_products
                      SET card_id = ? || '-' || LOWER(number)
                    WHERE code LIKE ? || ' %'""",
                (episode_code.lower(), episode_code))
            return cur.rowcount

    def market_products_for_card(self, card_id: str) -> list[dict]:
        return self._all(
            "SELECT * FROM market_products WHERE card_id=? ORDER BY version",
            (card_id,))

    def market_products_for_code(self, episode_id: int, code: str) -> list[dict]:
        """Every version of one card, from what was imported."""
        return self._all(
            """SELECT * FROM market_products
                WHERE episode_id=? AND code=? ORDER BY version""",
            (episode_id, code))

    def market_products_for_name(self, name: str) -> list[dict]:
        """Every product of a card by name, across every set already imported.

        This is what makes reprints show up in the version picker: a Pikachu is
        a Pikachu whether it is Base Set, Jungle or Neo Genesis, and someone
        holding one wants to find their exact printing without caring which set
        window they opened. market_products only ever holds imported sets, so
        this costs no request — the reprint is already in the database. Each row
        carries its own card_id and set, so a pick records the printing it is,
        not the card the modal happened to be opened on.
        """
        return self._all(
            """SELECT mp.*, os.name AS set_name, os.release_date AS set_release,
                      c.official_set_id AS set_id
                 FROM market_products mp
                 JOIN cards c ON c.id = mp.card_id
                 JOIN official_sets os ON os.id = c.official_set_id
                WHERE c.name = ?
                ORDER BY os.release_date, mp.code, mp.version""",
            (name,))

    def get_market_product(self, product_id: int) -> dict | None:
        return self._one("SELECT * FROM market_products WHERE product_id=?",
                         (product_id,))

    def market_products_by_ids(self, ids: list[int]) -> dict:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self._all(
            f"SELECT * FROM market_products WHERE product_id IN ({marks})",
            tuple(ids))
        return {r["product_id"]: r for r in rows}

    def market_urls_for_cards(self, card_ids: Sequence[str]) -> dict[str, str]:
        """One representative Cardmarket URL per card, from the imported products.

        Every catalogue card in an imported set maps directly to Cardmarket
        products (tcggo <-> MKM), so a card-level link — the catalog grid, the
        card modal, a collection row that never pinned an exact version — comes
        from that direct match, not from a guess. A card with no product simply
        gets no link: that is an unimported/stale card, and a missing link beats
        a link to the dead redirector.
        """
        ids = [c for c in dict.fromkeys(card_ids) if c]
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self._all(
            f"""SELECT card_id, market_url FROM market_products
                 WHERE card_id IN ({marks})
                   AND market_url IS NOT NULL AND market_url <> ''
                 ORDER BY card_id, version""",
            tuple(ids))
        out: dict[str, str] = {}
        for r in rows:                    # first per card; ORDER BY makes it stable
            out.setdefault(r["card_id"], r["market_url"])
        return out

    def episode_is_imported(self, episode_id: int) -> int:
        row = self._one(
            "SELECT COUNT(*) AS n FROM market_products WHERE episode_id=?",
            (episode_id,))
        return int(row["n"]) if row else 0

    # -------------------------------------------------------------- episodes
    def get_set_episode(self, official_set_id: str) -> dict | None:
        return self._one("SELECT * FROM set_episodes WHERE official_set_id=?",
                         (official_set_id,))

    def set_set_episode(self, official_set_id: str, episode_id: int,
                        name: str | None = None, code: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO set_episodes(official_set_id, episode_id,
                       episode_name, episode_code, updated_at)
                   VALUES(?,?,?,?,datetime('now'))
                   ON CONFLICT(official_set_id) DO UPDATE SET
                     episode_id=excluded.episode_id,
                     episode_name=excluded.episode_name,
                     episode_code=excluded.episode_code,
                     updated_at=datetime('now')""",
                (official_set_id, episode_id, name, code))

    # ---------------------------------------------------------------- budget
    WINDOW_HOURS = 24

    def budget_used_in_window(self, provider: str) -> int:
        row = self._one(
            f"""SELECT COUNT(*) AS n FROM api_requests
                 WHERE provider=? AND sent_at > datetime('now', '-{self.WINDOW_HOURS} hours')""",
            (provider,))
        return int(row["n"]) if row else 0

    def budget_reserve_window(self, provider: str, n: int, limit: int) -> int | None:
        """Claim n requests against a rolling window, or return None.

        The prune runs first on purpose: it is a write, so the transaction takes
        SQLite's write lock before anything is counted. Counting first lets two
        threads both read the last free slot and both take it.
        """
        if n > limit:
            return None
        with self.tx() as c:
            c.execute(
                f"""DELETE FROM api_requests
                     WHERE provider=? AND sent_at <= datetime('now', '-{self.WINDOW_HOURS} hours')""",
                (provider,))
            used = c.execute(
                f"""SELECT COUNT(*) FROM api_requests
                     WHERE provider=? AND sent_at > datetime('now', '-{self.WINDOW_HOURS} hours')""",
                (provider,)).fetchone()[0]
            if used + n > limit:
                return None
            c.executemany(
                "INSERT INTO api_requests(provider, sent_at) VALUES(?, datetime('now'))",
                [(provider,)] * n)
            return used + n

    def budget_used(self, provider: str, day: str) -> int:
        row = self._one("SELECT count FROM api_budget WHERE provider=? AND day=?",
                        (provider, day))
        return int(row["count"]) if row else 0

    def budget_reserve(self, provider: str, day: str, n: int,
                       limit: int) -> int | None:
        """Claim n requests for today, or return None if that would exceed limit.

        The read and the write share one transaction: two threads must not both
        see the same last slot as free and each spend it.
        """
        # Note the absence of a truthiness check on limit: `if limit and ...`
        # would read a limit of 0 as "no limit" and allow every request, which
        # is the exact opposite of what 0 means here.
        if n > limit:
            return None
        with self.tx() as c:
            # One statement decides and writes. Reading the count first and
            # then updating loses the race: two threads both see the last slot
            # free, both increment, and the day ends one request over the cap —
            # which is a charge, not a rounding error. The WHERE on DO UPDATE
            # makes the check part of the write, and the write takes SQLite's
            # lock before anyone else can read.
            cur = c.execute(
                """INSERT INTO api_budget(provider, day, count) VALUES(?,?,?)
                   ON CONFLICT(provider, day)
                   DO UPDATE SET count = api_budget.count + excluded.count
                    WHERE api_budget.count + excluded.count <= ?""",
                (provider, day, n, limit))
            if cur.rowcount == 0:
                return None
            row = c.execute(
                "SELECT count FROM api_budget WHERE provider=? AND day=?",
                (provider, day)).fetchone()
            return int(row["count"])

    def get_prices_for_card(self, card_id: str) -> list[dict]:
        return self._all("SELECT * FROM price_cache WHERE card_id=?", (card_id,))

    # ---------------------------------------------------------------- quotes
    def upsert_quote(self, card_id: str, variant: str, provider: str, market: str,
                     printing: str, currency: str, price, low=None, mid=None,
                     high=None, trend=None, avg30=None, product_id=None,
                     trusted: bool = True, distrust_reason: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO price_quotes(card_id, variant, provider, market,
                       printing, currency, price, price_low, price_mid, price_high,
                       price_trend, price_avg30, product_id, trusted,
                       distrust_reason, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                   ON CONFLICT(card_id, variant, provider, market, printing)
                   DO UPDATE SET currency=excluded.currency, price=excluded.price,
                       price_low=excluded.price_low, price_mid=excluded.price_mid,
                       price_high=excluded.price_high, price_trend=excluded.price_trend,
                       price_avg30=excluded.price_avg30, product_id=excluded.product_id,
                       trusted=excluded.trusted,
                       distrust_reason=excluded.distrust_reason,
                       updated_at=datetime('now')""",
                (card_id, variant, provider, market, printing or "", currency, price,
                 low, mid, high, trend, avg30, product_id,
                 1 if trusted else 0, distrust_reason),
            )

    def quotes_for_card(self, card_id: str, variant: str | None = None) -> list[dict]:
        """Every quote we hold, worst-trusted last so the UI can lead with the good ones."""
        sql = "SELECT * FROM price_quotes WHERE card_id=?"
        params: list = [card_id]
        if variant is not None:
            sql += " AND variant=?"
            params.append(variant)
        return self._all(sql + " ORDER BY trusted DESC, market, provider, printing",
                         tuple(params))

    def get_price(self, card_id: str, variant: str,
                  source: str | None = None) -> dict | None:
        """Price for this printing. A manual entry always wins over the feed."""
        if source:
            return self._one(
                "SELECT * FROM price_cache WHERE card_id=? AND variant=? AND source=?",
                (card_id, variant, source),
            )
        return self._one(
            "SELECT * FROM price_cache WHERE card_id=? AND variant=? "
            "ORDER BY CASE source WHEN 'manual' THEN 0 ELSE 1 END LIMIT 1",
            (card_id, variant),
        )

    def stale_priced_pairs(self, stale_days: int) -> list[dict]:
        """Owned (card, variant) pairs that need re-pricing.

        Age is not the only reason a price is stale. A row written before prices
        were resolved per print run has no `variant_key`, and it is wrong no
        matter how recently it was fetched — it holds one number for every
        printing of the card. Those rows must be refreshed on the next run or a
        collection entered before the change keeps its old prices forever, while
        newly added cards price correctly. That asymmetry is exactly what was
        reported.

        Manual prices are excluded: they are never refreshed.
        """
        return self._all(
            """SELECT DISTINCT i.card_id, i.variant FROM collection_items i
               LEFT JOIN price_cache p
                 ON p.card_id = i.card_id AND p.variant = i.variant
                AND p.source <> 'manual'
               WHERE NOT EXISTS (SELECT 1 FROM price_cache m
                                  WHERE m.card_id = i.card_id
                                    AND m.variant = i.variant
                                    AND m.source = 'manual')
                 AND (p.card_id IS NULL
                      OR p.variant_key IS NULL
                      OR julianday('now') - julianday(p.updated_at) > ?)
               ORDER BY i.card_id""",
            (stale_days,),
        )

    def count_legacy_prices(self) -> int:
        """Cached prices that predate per-print-run resolution."""
        return self._scalar(
            "SELECT COUNT(*) FROM price_cache "
            "WHERE variant_key IS NULL AND source <> 'manual'") or 0

    def price_history(self, card_id: str | None = None, set_id: str | None = None) -> list[dict]:
        if card_id:
            return self._all(
                "SELECT captured_on, SUM(price) AS price FROM price_history "
                "WHERE card_id=? GROUP BY captured_on ORDER BY captured_on", (card_id,)
            )
        if set_id:
            return self._all(
                """SELECT h.captured_on, SUM(h.price) AS price FROM price_history h
                   WHERE h.card_id IN (SELECT card_id FROM set_slot_cards WHERE set_id=?)
                   GROUP BY h.captured_on ORDER BY h.captured_on""", (set_id,)
            )
        return self._all(
            "SELECT captured_on, SUM(price) AS price FROM price_history "
            "GROUP BY captured_on ORDER BY captured_on"
        )

    # ------------------------------------------------------------- snapshots
    def write_snapshot(self, snap: dict) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO collection_snapshots
                     (captured_on,unique_cards,physical_cards,sets_total,sets_complete,
                      completion_pct,value_eur,breakdown_json)
                   VALUES (:captured_on,:unique_cards,:physical_cards,:sets_total,
                           :sets_complete,:completion_pct,:value_eur,:breakdown_json)
                   ON CONFLICT(captured_on) DO UPDATE SET
                     unique_cards=excluded.unique_cards, physical_cards=excluded.physical_cards,
                     sets_total=excluded.sets_total, sets_complete=excluded.sets_complete,
                     completion_pct=excluded.completion_pct, value_eur=excluded.value_eur,
                     breakdown_json=excluded.breakdown_json""",
                snap,
            )

    def list_snapshots(self, limit: int = 365) -> list[dict]:
        return self._all(
            "SELECT * FROM collection_snapshots ORDER BY captured_on DESC LIMIT ?", (limit,)
        )

    # ------------------------------------------------------------ dashboards
    def card_types(self) -> list[str]:
        """Distinct energy types present in the catalog, for the type filter."""
        seen: set[str] = set()
        for row in self._all("SELECT DISTINCT types_json FROM cards "
                             "WHERE types_json IS NOT NULL AND types_json <> '[]'"):
            try:
                seen.update(json.loads(row["types_json"]))
            except (TypeError, ValueError):
                continue
        return sorted(seen)

    def rarities(self) -> list[str]:
        return [r["rarity"] for r in self._all(
            "SELECT DISTINCT rarity FROM cards WHERE rarity IS NOT NULL ORDER BY rarity")]
