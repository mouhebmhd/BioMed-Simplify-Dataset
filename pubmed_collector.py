"""
pubmed_collector.py — Collect abstracts from PubMed / MEDLINE via Entrez E-utilities.

Usage (CLI):
    python pubmed_collector.py --query "diabetes type 2[MeSH]" --max 500

Usage (module):
    from pubmed_collector import PubMedCollector
    collector = PubMedCollector()
    records = collector.collect(query="hypertension", max_results=200)
"""

import argparse
import logging
import time
from typing import Optional

from Bio import Entrez
from tqdm import tqdm

import config
from utils import clean_text, is_long_enough, save_json, save_csv, save_text_corpus

logger = logging.getLogger("pubmed_collector")

# Configure Biopython's Entrez
Entrez.email = config.ENTREZ_EMAIL
if config.NCBI_API_KEY:
    Entrez.api_key = config.NCBI_API_KEY


class PubMedCollector:
    """
    Fetches PubMed abstracts using NCBI Entrez E-utilities (via Biopython).

    Each returned record contains:
        pmid, title, abstract, authors, journal, year, doi, keywords
    """

    def __init__(self, min_abstract_len: int = config.PUBMED_MIN_ABSTRACT_LEN):
        self.min_len = min_abstract_len

    # ── Public API ─────────────────────────────────────────────────────────────

    def search_ids(self, query: str, max_results: int) -> list[str]:
        """Return a list of PubMed IDs matching *query*."""
        logger.info("Searching PubMed: '%s' (max %d)", query, max_results)
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, usehistory="y")
        record = Entrez.read(handle)
        handle.close()
        ids = record.get("IdList", [])
        logger.info("Found %d IDs", len(ids))
        return ids

    def fetch_batch(self, ids: list[str]) -> list[dict]:
        """Fetch and parse a batch of PubMed records by PMID list."""
        id_str = ",".join(ids)
        handle = Entrez.efetch(db="pubmed", id=id_str, rettype="xml", retmode="xml")
        records = Entrez.read(handle)
        handle.close()
        return self._parse_records(records)

    def collect(
        self,
        query: str = config.PUBMED_DEFAULT_QUERY,
        max_results: int = config.PUBMED_DEFAULT_MAX,
        batch_size: int = config.PUBMED_BATCH_SIZE,
    ) -> list[dict]:
        """
        Full pipeline: search → batch-fetch → parse → filter.
        Returns a list of cleaned record dicts.
        """
        ids = self.search_ids(query, max_results)
        all_records: list[dict] = []

        batches = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]
        for batch in tqdm(batches, desc="Fetching PubMed batches"):
            try:
                records = self.fetch_batch(batch)
                all_records.extend(records)
            except Exception as exc:
                logger.warning("Batch fetch error: %s", exc)
            # NCBI rate-limit: 3 req/s without key, 10 req/s with key
            time.sleep(0.35 if not config.NCBI_API_KEY else 0.12)

        filtered = [r for r in all_records if is_long_enough(r.get("abstract", ""), self.min_len)]
        logger.info("Retained %d / %d records after length filter", len(filtered), len(all_records))
        return filtered

    # ── Parsing helpers ────────────────────────────────────────────────────────

    def _parse_records(self, records) -> list[dict]:
        parsed = []
        articles = records.get("PubmedArticle", [])
        for article in articles:
            try:
                parsed.append(self._parse_single(article))
            except Exception as exc:
                logger.debug("Skipping malformed record: %s", exc)
        return parsed

    def _parse_single(self, article) -> dict:
        medline = article["MedlineCitation"]
        art     = medline["Article"]

        # ── Abstract ──────────────────────────────────────────────────────────
        abstract_texts = []
        if "Abstract" in art:
            ab = art["Abstract"].get("AbstractText", [])
            if isinstance(ab, list):
                for section in ab:
                    label = getattr(section, "attributes", {}).get("Label", "")
                    text  = str(section)
                    if label:
                        abstract_texts.append(f"{label}: {text}")
                    else:
                        abstract_texts.append(text)
            else:
                abstract_texts.append(str(ab))

        abstract = clean_text(" ".join(abstract_texts))

        # ── Authors ───────────────────────────────────────────────────────────
        authors = []
        for author in art.get("AuthorList", []):
            last  = author.get("LastName", "")
            first = author.get("ForeName", "")
            if last:
                authors.append(f"{last} {first}".strip())

        # ── Journal & year ────────────────────────────────────────────────────
        journal_info = art.get("Journal", {})
        journal      = str(journal_info.get("Title", ""))
        pub_date     = journal_info.get("JournalIssue", {}).get("PubDate", {})
        year         = str(pub_date.get("Year", pub_date.get("MedlineDate", "")))

        # ── DOI ───────────────────────────────────────────────────────────────
        doi = ""
        for loc_id in art.get("ELocationID", []):
            if getattr(loc_id, "attributes", {}).get("EIdType") == "doi":
                doi = str(loc_id)
                break

        # ── Keywords ──────────────────────────────────────────────────────────
        keywords = [str(kw) for kw in medline.get("KeywordList", [[]])[0]] if medline.get("KeywordList") else []

        return {
            "pmid":     str(medline["PMID"]),
            "title":    clean_text(str(art.get("ArticleTitle", ""))),
            "abstract": abstract,
            "authors":  "; ".join(authors),
            "journal":  journal,
            "year":     year,
            "doi":      doi,
            "keywords": "; ".join(keywords),
            "source":   "PubMed",
        }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Collect PubMed abstracts")
    parser.add_argument("--query",  default=config.PUBMED_DEFAULT_QUERY, help="PubMed search query")
    parser.add_argument("--max",    type=int, default=config.PUBMED_DEFAULT_MAX, help="Max articles to fetch")
    parser.add_argument("--output", choices=["json", "csv", "txt", "all"], default="all")
    args = parser.parse_args()

    collector = PubMedCollector()
    records   = collector.collect(query=args.query, max_results=args.max)

    if not records:
        logger.warning("No records collected.")
        return

    subdir = "pubmed"
    if args.output in ("json", "all"):
        save_json(records, "pubmed_abstracts.json", subdir)
    if args.output in ("csv", "all"):
        save_csv(records, "pubmed_abstracts.csv", subdir)
    if args.output in ("txt", "all"):
        paragraphs = [r["abstract"] for r in records if r["abstract"]]
        save_text_corpus(paragraphs, "pubmed_corpus.txt", subdir)

    print(f"\n✅ Done. Collected {len(records)} abstracts.")


if __name__ == "__main__":
    main()
