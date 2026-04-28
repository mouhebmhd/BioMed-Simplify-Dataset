"""
utils.py — Shared helpers: retry logic, text cleaning, JSON/CSV saving.
"""

import os
import json
import time
import logging
import csv
import re
from typing import Any, Callable, Optional

import requests

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("utils")


# ── HTTP with retry ────────────────────────────────────────────────────────────

def safe_get(url: str, params: dict = None, **kwargs) -> Optional[requests.Response]:
    """GET with automatic retry and exponential back-off."""
    for attempt in range(1, config.RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(
                url,
                params=params,
                timeout=config.REQUEST_TIMEOUT,
                **kwargs,
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, config.RETRY_ATTEMPTS, url, exc)
            if attempt < config.RETRY_ATTEMPTS:
                time.sleep(config.RETRY_BACKOFF * attempt)
    logger.error("All %d attempts failed for %s", config.RETRY_ATTEMPTS, url)
    return None


# ── Text cleaning ──────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Normalise whitespace, remove control characters."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return text.strip()


def is_long_enough(text: str, min_len: int) -> bool:
    return len(text.strip()) >= min_len


# ── Persistence ────────────────────────────────────────────────────────────────

def ensure_output_dir(subdir: str = "") -> str:
    path = os.path.join(config.OUTPUT_DIR, subdir) if subdir else config.OUTPUT_DIR
    os.makedirs(path, exist_ok=True)
    return path


def save_json(data: list[dict], filename: str, subdir: str = "") -> str:
    out_dir = ensure_output_dir(subdir)
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    logger.info("Saved %d records → %s", len(data), filepath)
    return filepath


def save_csv(data: list[dict], filename: str, subdir: str = "") -> str:
    if not data:
        logger.warning("Nothing to save for %s", filename)
        return ""
    out_dir = ensure_output_dir(subdir)
    filepath = os.path.join(out_dir, filename)
    fieldnames = list(dict.fromkeys(k for row in data for k in row))
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    logger.info("Saved %d rows → %s", len(data), filepath)
    return filepath


def save_text_corpus(paragraphs: list[str], filename: str, subdir: str = "") -> str:
    """One paragraph per line — ready for language model training."""
    out_dir = ensure_output_dir(subdir)
    filepath = os.path.join(out_dir, filename)
    with open(filepath, "w", encoding="utf-8") as fh:
        for para in paragraphs:
            fh.write(para.strip() + "\n")
    logger.info("Saved %d paragraphs → %s", len(paragraphs), filepath)
    return filepath
