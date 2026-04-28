"""
europepmc_collector.py — Collect abstracts and annotated paragraphs from Europe PMC
                          using the Europe PMC REST API.

Usage (CLI):
    python europepmc_collector.py --query "Alzheimer disease treatment" --max 100

Usage (module):
    from europepmc_collector import EuropePMCCollector
    collector = EuropePMCCollector()
    records = collector.collect(query="BRCA1 breast cancer", max_results=50)
"""

import argparse
import logging
import time
from typing import Optional

from bs4 import BeautifulSoup
from tqdm import tqdm

import config
from utils import clean_text, is_long_enough, safe_get, save_json, save_csv, save_text_corpus

logger = logging.getLogger("europepmc_collector")


class EuropePMCCollector:
    """
    Collects records from Europe PMC REST API.
    For open-access articles, also fetches full-text paragraphs.

    Record fields:
        id, pmid, pmcid, doi, title, abstract, journal, year,
        keywords, is_open_access, paragraphs, source
    """

    BASE_URL = config.EUROPEPMC_BASE_URL

    def __init__(self, min_paragraph_len: int = config.EUROPEPMC_MIN_PARAGRAPH_LEN):
        self.min_len = min_paragraph_len

    # ── Search ─────────────────────────────────────────────────────────────────

    def search(self, query: str, max_results: int) -> list[dict]:
        """Search Europe PMC and return a list of article metadata dicts."""
        results  = []
        cursor   = "*"
        page_size = min(100, max_results)

        logger.info("Searching Europe PMC: '%s' (max %d)", query, max_results)

        while len(results) < max_results:
            params = {
                "query":      query,
                "format":     "json",
                "pageSize":   page_size,
                "cursorMark": cursor,
                "resultType": "core",
            }
            resp = safe_get(f"{self.BASE_URL}/search", params=params)
            if resp is None:
                break

            data      = resp.json()
            articles  = data.get("resultList", {}).get("result", [])
            if not articles:
                break

            for art in articles:
                parsed = self._parse_search_result(art)
                if parsed:
                    results.append(parsed)
                if len(results) >= max_results:
                    break

            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            time.sleep(0.3)

        logger.info("Search returned %d results", len(results))
        return results[:max_results]

    def fetch_full_text_paragraphs(self, pmcid: str) -> list[str]:
        """
        Fetch full-text XML for an open-access PMC article and extract paragraphs.
        pmcid should be like 'PMC1234567'.
        """
        url  = f"{self.BASE_URL}/{pmcid}/fullTextXML"
        resp = safe_get(url)
        if resp is None:
            return []

        try:
            soup       = BeautifulSoup(resp.text, "lxml-xml")
            paragraphs = []
            body       = soup.find("body")
            if not body:
                return []
            for p in body.find_all("p"):
                text = clean_text(p.get_text(" ", strip=True))
                if is_long_enough(text, self.min_len):
                    paragraphs.append(text)
            return paragraphs
        except Exception as exc:
            logger.warning("Full-text parse error for %s: %s", pmcid, exc)
            return []

    def collect(
        self,
        query: str = config.EUROPEPMC_DEFAULT_QUERY,
        max_results: int = config.EUROPEPMC_DEFAULT_MAX,
        fetch_fulltext: bool = True,
    ) -> list[dict]:
        """
        Search → optionally enrich open-access articles with full-text paragraphs.
        """
        records = self.search(query, max_results)

        if fetch_fulltext:
            oa_records = [r for r in records if r.get("is_open_access") and r.get("pmcid")]
            logger.info("Fetching full-text for %d open-access articles", len(oa_records))
            for record in tqdm(oa_records, desc="Fetching full texts"):
                paras = self.fetch_full_text_paragraphs(record["pmcid"])
                record["paragraphs"] = paras
                time.sleep(0.3)

        return records

    # ── Parsing ────────────────────────────────────────────────────────────────

    def _parse_search_result(self, art: dict) -> Optional[dict]:
        abstract = clean_text(art.get("abstractText", "") or "")
        if not abstract and not art.get("pmcid"):
            return None   # Skip records with no abstract and no full-text available

        pmcid = art.get("pmcid", "")
        if pmcid and not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"

        keywords = []
        for kw_list in art.get("keywordList", {}).get("keyword", []):
            if isinstance(kw_list, str):
                keywords.append(kw_list)
            elif isinstance(kw_list, list):
                keywords.extend(kw_list)

        return {
            "id":             art.get("id", ""),
            "pmid":           art.get("pmid", ""),
            "pmcid":          pmcid,
            "doi":            art.get("doi", ""),
            "title":          clean_text(art.get("title", "")),
            "abstract":       abstract,
            "journal":        clean_text(art.get("journalTitle", "")),
            "year":           str(art.get("pubYear", "")),
            "keywords":       "; ".join(keywords),
            "is_open_access": art.get("isOpenAccess", "N") == "Y",
            "paragraphs":     [],    # filled later for OA articles
            "source":         "EuropePMC",
        }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Collect Europe PMC abstracts and paragraphs")
    parser.add_argument("--query",       default=config.EUROPEPMC_DEFAULT_QUERY)
    parser.add_argument("--max",         type=int, default=config.EUROPEPMC_DEFAULT_MAX)
    parser.add_argument("--no-fulltext", action="store_true", help="Skip full-text fetching")
    parser.add_argument("--output",      choices=["json", "csv", "txt", "all"], default="all")
    args = parser.parse_args()

    collector = EuropePMCCollector()
    records   = collector.collect(
        query=args.query,
        max_results=args.max,
        fetch_fulltext=not args.no_fulltext,
    )

    if not records:
        logger.warning("No records collected.")
        return

    subdir = "europepmc"
    if args.output in ("json", "all"):
        save_json(records, "europepmc_articles.json", subdir)
    if args.output in ("csv", "all"):
        flat = [{**{k: v for k, v in r.items() if k != "paragraphs"},
                 "paragraphs": " || ".join(r.get("paragraphs", []))} for r in records]
        save_csv(flat, "europepmc_articles.csv", subdir)
    if args.output in ("txt", "all"):
        all_paras = []
        for r in records:
            if r.get("paragraphs"):
                all_paras.extend(r["paragraphs"])
            elif r.get("abstract"):
                all_paras.append(r["abstract"])
        save_text_corpus(all_paras, "europepmc_corpus.txt", subdir)

    total_paras = sum(len(r.get("paragraphs", [])) for r in records)
    print(f"\n✅ Done. {len(records)} articles, {total_paras} full-text paragraphs.")


if __name__ == "__main__":
    main()
