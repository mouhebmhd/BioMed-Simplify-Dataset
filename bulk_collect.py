"""
bulk_collect.py — HPC-optimised parallel biomedical collector
              Uses ThreadPoolExecutor for I/O (NCBI fetching)
              and ProcessPoolExecutor for CPU-bound XML parsing.

Usage:
    python bulk_collect.py --keywords keywords.txt --per-query 100 --workers 16
    python bulk_collect.py --keywords keywords.txt --per-query 150 --workers 32 --source pubmed
"""

import argparse
import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

import config
from utils import save_json, save_csv, save_text_corpus

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

try:
    from europepmc_collector import EuropePMCCollector
    HAS_EPMC = True
except ImportError:
    HAS_EPMC = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bulk_collect")


# ── NCBI rate limiter ──────────────────────────────────────────────────────────
# With API key: 10 req/s  →  safe at 9 req/s
# Without     :  3 req/s  →  safe at 2.5 req/s

class RateLimiter:
    """Token-bucket rate limiter shared across all threads."""

    def __init__(self, calls_per_second: float):
        self.interval = 1.0 / calls_per_second
        self._lock    = threading.Lock()
        self._last    = 0.0

    def wait(self):
        with self._lock:
            now  = time.monotonic()
            wait = self.interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


# ── Keyword loader ─────────────────────────────────────────────────────────────

def load_keywords(path: str) -> list[str]:
    queries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                queries.append(line)
    logger.info("Loaded %d queries from %s", len(queries), path)
    return queries


# ── Deduplication ──────────────────────────────────────────────────────────────

def deduplicate(records: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for r in records:
        key = r.get("pmid") or r.get("pmcid") or r.get("doi") or r.get("id")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(r)
    return unique


# ── Per-query worker (runs in a thread) ───────────────────────────────────────

def fetch_query(
    query:        str,
    per_query:    int,
    source:       str,
    rate_limiter: RateLimiter,
) -> list[dict]:
    """Fetch records for a single query from all requested sources."""
    results = []

    if source in ("pubmed", "both") and HAS_PUBMED:
        try:
            rate_limiter.wait()
            records = PubMedCollector().collect(query=query, max_results=per_query)
            results.extend(records)
        except Exception as exc:
            logger.warning("PubMed error [%s]: %s", query[:60], exc)

    if source in ("pmc", "both") and HAS_PMC:
        try:
            rate_limiter.wait()
            records = PMCCollector().collect(query=query, max_results=per_query)
            results.extend(records)
        except Exception as exc:
            logger.warning("PMC error [%s]: %s", query[:60], exc)

    if source in ("epmc", "both") and HAS_EPMC:
        try:
            rate_limiter.wait()
            records = EuropePMCCollector().collect(query=query, max_results=per_query)
            results.extend(records)
        except Exception as exc:
            logger.warning("EuropePMC error [%s]: %s", query[:60], exc)

    return results


# ── Main parallel collection ───────────────────────────────────────────────────

def bulk_collect(
    queries:     list[str],
    per_query:   int  = 100,
    source:      str  = "both",
    target:      int  = 10_000,
    workers:     int  = 16,
    has_api_key: bool = True,
) -> list[dict]:

    rate_limiter = RateLimiter(calls_per_second=9.0 if has_api_key else 2.5)
    all_records: list[dict] = []
    lock = threading.Lock()

    print(f"\n⚙️  Parallel config : {workers} threads | "
          f"{'9 req/s (API key)' if has_api_key else '2.5 req/s (no key)'} | "
          f"target {target:,} records\n")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_query, q, per_query, source, rate_limiter): q
            for q in queries
        }

        with tqdm(total=len(queries), desc="Queries", unit="q") as pbar:
            for future in as_completed(futures):
                query = futures[future]
                try:
                    records = future.result()
                    with lock:
                        all_records.extend(records)
                        current = len(all_records)

                    pbar.set_postfix(collected=current, q=query[:35])
                    pbar.update(1)

                    if current >= target:
                        logger.info("Target %d reached — cancelling remaining futures.", target)
                        for f in futures:
                            f.cancel()
                        break

                except Exception as exc:
                    logger.warning("Future error for '%s': %s", query[:60], exc)
                    pbar.update(1)

    before = len(all_records)
    all_records = deduplicate(all_records)
    logger.info("Deduplicated: %d → %d unique records", before, len(all_records))

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
                row["paragraphs"]   = " || ".join(r["paragraphs"])
                row["n_paragraphs"] = len(r["paragraphs"])
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
    print(f"{'─'*55}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="HPC parallel biomedical data collector",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--keywords",  default="keywords.txt",
                        help="Path to keywords file")
    parser.add_argument("--per-query", type=int, default=100,
                        help="Max results per query per source")
    parser.add_argument("--target",    type=int, default=10_000,
                        help="Stop after collecting this many records")
    parser.add_argument("--source",    choices=["pubmed", "pmc", "epmc", "both"],
                        default="both",
                        help="Source(s) to collect from")
    parser.add_argument("--workers",   type=int, default=16,
                        help="Parallel threads (16–32 recommended on HPC)")
    parser.add_argument("--output",    choices=["json", "csv", "txt", "all"],
                        default="all",
                        help="Output format(s)")
    args = parser.parse_args()

    if not os.path.exists(args.keywords):
        raise FileNotFoundError(f"Keywords file not found: {args.keywords}")

    has_api_key = bool(getattr(config, "NCBI_API_KEY", None))
    queries     = load_keywords(args.keywords)

    print(f"\n🔬 BioMed Bulk Collector — HPC Mode")
    print(f"   Keywords : {args.keywords}  ({len(queries)} queries)")
    print(f"   Per query: {args.per_query} results × source")
    print(f"   Source   : {args.source}")
    print(f"   Workers  : {args.workers} threads")
    print(f"   Target   : {args.target:,} records")
    print(f"   API key  : {'✅ yes (9 req/s)' if has_api_key else '❌ no (2.5 req/s)'}")

    start   = time.monotonic()
    records = bulk_collect(
        queries=queries,
        per_query=args.per_query,
        source=args.source,
        target=args.target,
        workers=args.workers,
        has_api_key=has_api_key,
    )
    elapsed = time.monotonic() - start

    save_results(records, args.output)
    print(f"  ⏱️  Total time        : {elapsed:>7.1f}s  "
          f"({len(records) / max(elapsed, 1):.1f} records/s)")


if __name__ == "__main__":
    main()