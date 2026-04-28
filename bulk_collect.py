"""
bulk_collect.py — Collect 10 000+ abstracts/articles from PubMed & PMC
                  using a keyword file (one query per line).

Usage:
    python bulk_collect.py --keywords keywords.txt --per-query 80 --output all
    python bulk_collect.py --keywords keywords.txt --per-query 50 --source pubmed
"""

import argparse
import logging
import os
import time
from pathlib import Path

from tqdm import tqdm

import config
from utils import save_json, save_csv, save_text_corpus

# ── Optional imports (only what's available in your project) ──────────────────
try:
    from pmc_collector import PMCCollector
    HAS_PMC = True
except ImportError:
    HAS_PMC = False

try:
    from pubmed_collector import PubMedCollector
    HAS_PUBMED = True
except ImportError:
    HAS_PUBMED = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bulk_collect")


# ── Keyword loader ─────────────────────────────────────────────────────────────

def load_keywords(path: str) -> list[str]:
    """Load queries from a file, ignoring blank lines and # comments."""
    queries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                queries.append(line)
    logger.info("Loaded %d queries from %s", len(queries), path)
    return queries


# ── Deduplication ──────────────────────────────────────────────────────────────

def deduplicate(records: list[dict], key: str = "pmid") -> list[dict]:
    """Remove duplicate records by a given key field."""
    seen, unique = set(), []
    for r in records:
        val = r.get(key) or r.get("pmcid") or r.get("doi")
        if val and val not in seen:
            seen.add(val)
            unique.append(r)
        elif not val:
            unique.append(r)  # keep records with no ID rather than silently drop
    return unique


# ── Main collection loop ───────────────────────────────────────────────────────

def bulk_collect(
    queries: list[str],
    per_query: int = 80,
    source: str = "both",          # "pubmed" | "pmc" | "both"
    target: int = 10_000,
    delay_between_queries: float = 1.0,
) -> list[dict]:

    all_records: list[dict] = []
    pmc_collector    = PMCCollector()    if HAS_PMC    and source in ("pmc",    "both") else None
    pubmed_collector = PubMedCollector() if HAS_PUBMED and source in ("pubmed", "both") else None

    if not pmc_collector and not pubmed_collector:
        raise RuntimeError("No collectors available. Check your imports.")

    for i, query in enumerate(tqdm(queries, desc="Queries"), 1):
        if len(all_records) >= target:
            logger.info("Reached target of %d records — stopping early.", target)
            break

        logger.info("[%d/%d] Query: %s", i, len(queries), query)

        # ── PubMed ────────────────────────────────────────────────────────────
        if pubmed_collector:
            try:
                records = pubmed_collector.collect(query=query, max_results=per_query)
                all_records.extend(records)
                logger.info("  PubMed → +%d (total %d)", len(records), len(all_records))
            except Exception as exc:
                logger.warning("  PubMed error for '%s': %s", query, exc)

        # ── PMC ───────────────────────────────────────────────────────────────
        if pmc_collector:
            try:
                records = pmc_collector.collect(query=query, max_results=per_query)
                all_records.extend(records)
                logger.info("  PMC    → +%d (total %d)", len(records), len(all_records))
            except Exception as exc:
                logger.warning("  PMC error for '%s': %s", query, exc)

        time.sleep(delay_between_queries)

    # Deduplicate across all sources
    before = len(all_records)
    all_records = deduplicate(all_records)
    logger.info("Deduplicated: %d → %d records", before, len(all_records))

    return all_records


# ── Save results ───────────────────────────────────────────────────────────────

def save_results(records: list[dict], output: str, subdir: str = "bulk") -> None:
    if not records:
        logger.warning("No records to save.")
        return

    if output in ("json", "all"):
        save_json(records, "bulk_records.json", subdir)

    if output in ("csv", "all"):
        flat = []
        for r in records:
            row = {k: v for k, v in r.items() if k != "paragraphs"}
            if "paragraphs" in r:
                row["paragraphs"] = " || ".join(r["paragraphs"])
                row["n_paragraphs"] = len(r["paragraphs"])
            if "abstract" in r:
                row["abstract"] = r["abstract"]
            flat.append(row)
        save_csv(flat, "bulk_records.csv", subdir)

    if output in ("txt", "all"):
        corpus = []
        for r in records:
            if r.get("abstract"):
                corpus.append(r["abstract"])
            corpus.extend(r.get("paragraphs", []))
        save_text_corpus(corpus, "bulk_corpus.txt", subdir)

    total_abstracts  = sum(1 for r in records if r.get("abstract"))
    total_paragraphs = sum(len(r.get("paragraphs", [])) for r in records)
    print(f"\n{'─'*55}")
    print(f"  ✅ Total records     : {len(records):>8,}")
    print(f"  📄 With abstracts    : {total_abstracts:>8,}")
    print(f"  📝 Total paragraphs  : {total_paragraphs:>8,}")
    print(f"{'─'*55}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bulk biomedical data collector")
    parser.add_argument(
        "--keywords", default="keywords.txt",
        help="Path to keywords file (default: keywords.txt)"
    )
    parser.add_argument(
        "--per-query", type=int, default=80,
        help="Max results per query per source (default: 80)"
    )
    parser.add_argument(
        "--target", type=int, default=10_000,
        help="Stop collecting after this many records (default: 10000)"
    )
    parser.add_argument(
        "--source", choices=["pubmed", "pmc", "both"], default="both",
        help="Which source to collect from (default: both)"
    )
    parser.add_argument(
        "--output", choices=["json", "csv", "txt", "all"], default="all",
        help="Output format(s) (default: all)"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to wait between queries (default: 1.0)"
    )
    args = parser.parse_args()

    if not os.path.exists(args.keywords):
        raise FileNotFoundError(f"Keywords file not found: {args.keywords}")

    queries = load_keywords(args.keywords)
    print(f"\n🔬 Starting bulk collection")
    print(f"   Keywords file : {args.keywords} ({len(queries)} queries)")
    print(f"   Per query     : {args.per_query} results × source")
    print(f"   Source        : {args.source}")
    print(f"   Target        : {args.target:,} records\n")

    records = bulk_collect(
        queries=queries,
        per_query=args.per_query,
        source=args.source,
        target=args.target,
        delay_between_queries=args.delay,
    )

    save_results(records, args.output)


if __name__ == "__main__":
    main()
