"""Catalog import. Resumable, set by set.

Spec §20: external data must never overwrite collection state. The importer only
writes official_sets and cards; it never touches collection_sets, set_slots,
collection_items or photos.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class CatalogImporter:
    def __init__(self, repo, source, config):
        self.repo = repo
        self.source = source
        self.config = config

    def import_sets(self, set_ids: list[str]) -> dict:
        result = {"sets": {}, "cards": 0, "failed": []}
        for sid in set_ids:
            try:
                meta = self.source.fetch_set(sid)
                self.repo.upsert_official_set(meta)
                cards = list(self.source.fetch_cards(sid))
                n = self.repo.upsert_cards(cards)
                result["sets"][sid] = n
                result["cards"] += n
                log.info("imported %s: %d cards", sid, n)
            except Exception as e:
                # One flaky set must not lose the sets already imported.
                log.error("import failed for %s: %s", sid, e)
                result["failed"].append({"set": sid, "error": str(e)})
        self.repo.set_meta("last_catalog_import", str(result["cards"]))
        return result

    def resolve_market_links(self, limit: int = 5000, workers: int = 8,
                             batch: int = 100, progress=None) -> dict:
        """Resolve and store each card's Cardmarket product URL.

        Only prices.pokemontcg.io is contacted — the redirect is read, never
        followed into Cardmarket. Resumable: already-resolved cards are skipped,
        so a partial run just needs re-running.

        Writes are committed in batches. Committing per card holds the SQLite
        write lock almost continuously across a 1100-card run and makes
        concurrent reads (i.e. the web UI) block until they time out.
        """
        todo = self.repo.cards_missing_market_url(limit)
        if not todo:
            return {"resolved": 0, "failed": 0,
                    "total_with_links": self.repo.count_market_urls()}

        ok = fail = 0
        pending: list[tuple[str, str]] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.source.resolve_market_url, r["id"]): r["id"]
                       for r in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                card_id = futures[fut]
                try:
                    url = fut.result()
                except Exception as e:
                    log.debug("resolve failed for %s: %s", card_id, e)
                    url = None
                if url:
                    pending.append((card_id, url))
                    ok += 1
                else:
                    fail += 1
                if len(pending) >= batch:
                    self.repo.set_card_market_urls(pending)
                    pending.clear()
                    if progress:
                        progress(i, len(todo))

        self.repo.set_card_market_urls(pending)
        return {"resolved": ok, "failed": fail,
                "total_with_links": self.repo.count_market_urls()}

    def cache_images(self, limit: int = 5000) -> dict:
        """Download catalog thumbnails locally so the grid does not depend on a
        third-party CDN on every page load (PLAN.md §2.14). ~40MB for 1,100 cards."""
        target: Path = self.config.CATALOG_IMG_DIR
        target.mkdir(parents=True, exist_ok=True)
        todo = self.repo.cards_missing_local_image(limit)
        ok = fail = 0
        with requests.Session() as s:
            s.headers["User-Agent"] = "tombot-pokemon-tracker/0.1"
            for row in todo:
                dest = target / f"{row['id']}.png"
                try:
                    if not dest.exists():
                        r = s.get(row["image_small_url"], timeout=self.config.HTTP_TIMEOUT)
                        r.raise_for_status()
                        dest.write_bytes(r.content)
                    self.repo.set_card_image_local(row["id"], f"catalog/{dest.name}")
                    ok += 1
                except Exception as e:
                    log.warning("image download failed for %s: %s", row["id"], e)
                    fail += 1
        return {"downloaded": ok, "failed": fail, "remaining": max(0, len(todo) - ok)}
