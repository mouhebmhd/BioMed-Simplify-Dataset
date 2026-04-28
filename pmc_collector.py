"""
pmc_collector.py — Collect full-text paragraphs from PubMed Central (PMC)
                   via the NCBI Entrez API (XML format).

Usage (CLI):
    python pmc_collector.py --query "COVID-19 treatment[MeSH]" --max 30

Usage (module):
    from pmc_collector import PMCCollector
    collector = PMCCollector()
    records = collector.collect(query="stroke rehabilitation", max_results=20)
"""

import argparse
import logging
import time
from typing import Optional, Union

from Bio import Entrez
from bs4 import BeautifulSoup
from tqdm import tqdm

import config
from utils import clean_text, is_long_enough, save_json, save_csv, save_text_corpus

logger = logging.getLogger("pmc_collector")

Entrez.email = config.ENTREZ_EMAIL
if config.NCBI_API_KEY:
    Entrez.api_key = config.NCBI_API_KEY

# Sections to SKIP (non-scientific body content)
SKIP_SECTION_TITLES = {
    "references", "acknowledgements", "acknowledgments",
    "conflict of interest", "competing interests", "funding",
    "author contributions", "supplementary", "abbreviations",
    "ethics", "data availability", "availability of data",
}


class PMCCollector:
    """
    Fetches full-text XML from PMC and extracts body paragraphs.

    Each record contains:
        pmcid, pmid, title, journal, year, paragraphs (list), abstract
    """

    def __init__(self, min_paragraph_len: int = config.PMC_MIN_PARAGRAPH_LEN):
        self.min_len = min_paragraph_len

    # ── Public API ─────────────────────────────────────────────────────────────

    def search_ids(self, query: str, max_results: int) -> list[str]:
        logger.info("Searching PMC: '%s' (max %d)", query, max_results)
        handle = Entrez.esearch(db="pmc", term=query, retmax=max_results)
        record = Entrez.read(handle)
        handle.close()
        ids = record.get("IdList", [])
        logger.info("Found %d PMC IDs", len(ids))
        return ids

    def fetch_full_text(self, pmc_id: str) -> Optional[str]:
        """Return raw XML for a single PMC article."""
        try:
            handle = Entrez.efetch(db="pmc", id=pmc_id, rettype="full", retmode="xml")
            xml_data = handle.read()
            handle.close()
            return xml_data
        except Exception as exc:
            logger.warning("Failed to fetch PMC %s: %s", pmc_id, exc)
            return None

    def parse_full_text(self, xml_data: Union[bytes, str]) -> dict:
        """Parse PMC XML and extract metadata + body paragraphs."""
        soup = BeautifulSoup(xml_data, "lxml-xml")

        # ── Metadata ──────────────────────────────────────────────────────────
        title   = self._get_text(soup.find("article-title"))
        journal = self._get_text(soup.find("journal-title"))
        year    = self._get_text(soup.find("year"))
        pmcid   = self._get_text(soup.find("article-id", {"pub-id-type": "pmc"}))
        pmid    = self._get_text(soup.find("article-id", {"pub-id-type": "pmid"}))
        doi     = self._get_text(soup.find("article-id", {"pub-id-type": "doi"}))

        # ── Abstract ──────────────────────────────────────────────────────────
        abstract_parts = []
        abstract_tag = soup.find("abstract")
        if abstract_tag:
            for p in abstract_tag.find_all("p"):
                text = clean_text(p.get_text(" ", strip=True))
                if text:
                    abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # ── Body paragraphs ───────────────────────────────────────────────────
        paragraphs = self._extract_paragraphs(soup)

        return {
            "pmcid":      f"PMC{pmcid}" if pmcid and not pmcid.startswith("PMC") else pmcid,
            "pmid":       pmid,
            "doi":        doi,
            "title":      clean_text(title),
            "journal":    clean_text(journal),
            "year":       year,
            "abstract":   abstract,
            "paragraphs": paragraphs,
            "n_paragraphs": len(paragraphs),
            "source":     "PMC",
        }

    def collect(
        self,
        query: str = config.PMC_DEFAULT_QUERY,
        max_results: int = config.PMC_DEFAULT_MAX,
    ) -> list[dict]:
        ids     = self.search_ids(query, max_results)
        records = []

        for pmc_id in tqdm(ids, desc="Fetching PMC articles"):
            xml_data = self.fetch_full_text(pmc_id)
            if xml_data:
                try:
                    record = self.parse_full_text(xml_data)
                    if record["paragraphs"]:
                        records.append(record)
                except Exception as exc:
                    logger.warning("Parse error for PMC %s: %s", pmc_id, exc)
            time.sleep(0.4 if not config.NCBI_API_KEY else 0.15)

        logger.info("Collected %d PMC articles with paragraphs", len(records))
        return records

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        body = soup.find("body")
        if not body:
            return []

        paragraphs = []
        for section in body.find_all("sec", recursive=True):
            # Check section title — skip boilerplate sections
            sec_title_tag = section.find("title", recursive=False)
            if sec_title_tag:
                sec_title = sec_title_tag.get_text().lower().strip()
                if any(skip in sec_title for skip in SKIP_SECTION_TITLES):
                    continue

            for p_tag in section.find_all("p", recursive=False):
                text = clean_text(p_tag.get_text(" ", strip=True))
                if is_long_enough(text, self.min_len):
                    paragraphs.append(text)

        # Paragraphs directly under <body> (outside any <sec>)
        for p_tag in body.find_all("p", recursive=False):
            text = clean_text(p_tag.get_text(" ", strip=True))
            if is_long_enough(text, self.min_len):
                paragraphs.append(text)

        return paragraphs

    @staticmethod
    def _get_text(tag) -> str:
        return tag.get_text(strip=True) if tag else ""


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Collect PMC full-text paragraphs")
    parser.add_argument("--query",  default=config.PMC_DEFAULT_QUERY)
    parser.add_argument("--max",    type=int, default=config.PMC_DEFAULT_MAX)
    parser.add_argument("--output", choices=["json", "csv", "txt", "all"], default="all")
    args = parser.parse_args()

    collector = PMCCollector()
    records   = collector.collect(query=args.query, max_results=args.max)

    if not records:
        logger.warning("No records collected.")
        return

    subdir = "pmc"
    if args.output in ("json", "all"):
        save_json(records, "pmc_articles.json", subdir)
    if args.output in ("csv", "all"):
        # Flatten paragraphs list → join for CSV
        flat = [{**{k: v for k, v in r.items() if k != "paragraphs"},
                 "paragraphs": " || ".join(r["paragraphs"])} for r in records]
        save_csv(flat, "pmc_articles.csv", subdir)
    if args.output in ("txt", "all"):
        all_paras = [p for r in records for p in r["paragraphs"]]
        save_text_corpus(all_paras, "pmc_corpus.txt", subdir)

    total_paras = sum(r["n_paragraphs"] for r in records)
    print(f"\n✅ Done. {len(records)} articles, {total_paras} paragraphs total.")


if __name__ == "__main__":
    main()
