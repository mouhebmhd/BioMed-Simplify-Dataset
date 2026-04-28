"""
pipeline.py — Master pipeline: run all collectors and merge into a unified dataset.

Usage:
    python pipeline.py --query "diabetes" --pubmed-max 300 --pmc-max 30 --europepmc-max 100

Outputs (in output/merged/):
    all_records.json    — full metadata
    all_records.csv     — flat CSV (paragraphs joined)
    corpus.txt          — one paragraph per line, ready for NLP training
    stats.json          — collection statistics
"""

import argparse
import json
import logging
import os
from datetime import datetime

import config
from utils import save_json, save_csv, save_text_corpus, ensure_output_dir
from pubmed_collector    import PubMedCollector
from pmc_collector       import PMCCollector
from europepmc_collector import EuropePMCCollector

logger = logging.getLogger("pipeline")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def run_pipeline(
    query: str,
    pubmed_max: int  = 200,
    pmc_max: int     = 30,
    epmc_max: int    = 100,
    skip_pubmed: bool    = False,
    skip_pmc: bool       = False,
    skip_europepmc: bool = False,
    fetch_fulltext: bool = True,
) -> dict:
    all_records: list[dict] = []
    stats = {
        "query":      query,
        "timestamp":  datetime.utcnow().isoformat(),
        "pubmed":     {"requested": pubmed_max, "collected": 0},
        "pmc":        {"requested": pmc_max,    "collected": 0, "total_paragraphs": 0},
        "europepmc":  {"requested": epmc_max,   "collected": 0, "total_paragraphs": 0},
    }

    # ── 1. PubMed abstracts ────────────────────────────────────────────────────
    if not skip_pubmed and pubmed_max > 0:
        logger.info("═══ PubMed Abstracts ═══")
        pubmed = PubMedCollector()
        pm_records = pubmed.collect(query=query, max_results=pubmed_max)
        # Normalise: add empty paragraphs field
        for r in pm_records:
            r.setdefault("paragraphs", [r["abstract"]] if r.get("abstract") else [])
        all_records.extend(pm_records)
        stats["pubmed"]["collected"] = len(pm_records)
        logger.info("PubMed: %d abstracts collected", len(pm_records))

    # ── 2. PMC full text ───────────────────────────────────────────────────────
    if not skip_pmc and pmc_max > 0:
        logger.info("═══ PMC Full Text ═══")
        pmc = PMCCollector()
        pmc_records = pmc.collect(query=query, max_results=pmc_max)
        all_records.extend(pmc_records)
        total_p = sum(r["n_paragraphs"] for r in pmc_records)
        stats["pmc"]["collected"]         = len(pmc_records)
        stats["pmc"]["total_paragraphs"]  = total_p
        logger.info("PMC: %d articles, %d paragraphs", len(pmc_records), total_p)

    # ── 3. Europe PMC ──────────────────────────────────────────────────────────
    if not skip_europepmc and epmc_max > 0:
        logger.info("═══ Europe PMC ═══")
        epmc = EuropePMCCollector()
        epmc_records = epmc.collect(query=query, max_results=epmc_max, fetch_fulltext=fetch_fulltext)
        all_records.extend(epmc_records)
        total_p = sum(len(r.get("paragraphs", [])) for r in epmc_records)
        stats["europepmc"]["collected"]        = len(epmc_records)
        stats["europepmc"]["total_paragraphs"] = total_p
        logger.info("EuropePMC: %d articles, %d paragraphs", len(epmc_records), total_p)

    # ── Collect all paragraphs ─────────────────────────────────────────────────
    all_paragraphs: list[str] = []
    for r in all_records:
        paras = r.get("paragraphs", [])
        if isinstance(paras, list):
            all_paragraphs.extend(paras)
        elif isinstance(paras, str) and paras:
            all_paragraphs.extend(paras.split(" || "))

    stats["total_records"]    = len(all_records)
    stats["total_paragraphs"] = len(all_paragraphs)

    # ── Save outputs ───────────────────────────────────────────────────────────
    subdir = "merged"
    save_json(all_records, "all_records.json", subdir)

    flat = []
    for r in all_records:
        row = {k: v for k, v in r.items() if k != "paragraphs"}
        paras = r.get("paragraphs", [])
        if isinstance(paras, list):
            row["paragraphs"] = " || ".join(paras)
        else:
            row["paragraphs"] = str(paras)
        flat.append(row)
    save_csv(flat, "all_records.csv", subdir)

    save_text_corpus(all_paragraphs, "corpus.txt", subdir)

    stats_path = os.path.join(ensure_output_dir(subdir), "stats.json")
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    logger.info("Stats saved → %s", stats_path)

    return stats


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Unified medical paragraph collection pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--query",          default="diabetes mellitus", help="Search query (shared across all sources)")
    parser.add_argument("--pubmed-max",     type=int, default=200)
    parser.add_argument("--pmc-max",        type=int, default=30)
    parser.add_argument("--europepmc-max",  type=int, default=100)
    parser.add_argument("--skip-pubmed",    action="store_true")
    parser.add_argument("--skip-pmc",       action="store_true")
    parser.add_argument("--skip-europepmc", action="store_true")
    parser.add_argument("--no-fulltext",    action="store_true", help="Skip full-text fetching for Europe PMC")
    args = parser.parse_args()

    stats = run_pipeline(
        query           = args.query,
        pubmed_max      = args.pubmed_max,
        pmc_max         = args.pmc_max,
        epmc_max        = args.europepmc_max,
        skip_pubmed     = args.skip_pubmed,
        skip_pmc        = args.skip_pmc,
        skip_europepmc  = args.skip_europepmc,
        fetch_fulltext  = not args.no_fulltext,
    )

    print("\n" + "═" * 50)
    print("  COLLECTION COMPLETE")
    print("═" * 50)
    print(f"  Query            : {stats['query']}")
    print(f"  PubMed abstracts : {stats['pubmed']['collected']}")
    print(f"  PMC articles     : {stats['pmc']['collected']}  ({stats['pmc']['total_paragraphs']} paragraphs)")
    print(f"  Europe PMC       : {stats['europepmc']['collected']}  ({stats['europepmc']['total_paragraphs']} paragraphs)")
    print(f"  ─────────────────────────────────────────────")
    print(f"  Total records    : {stats['total_records']}")
    print(f"  Total paragraphs : {stats['total_paragraphs']}")
    print(f"  Output dir       : {config.OUTPUT_DIR}/merged/")
    print("═" * 50)


if __name__ == "__main__":
    main()
