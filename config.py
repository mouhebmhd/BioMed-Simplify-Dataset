"""
config.py — Central configuration for all medical abstract collectors.
Edit ENTREZ_EMAIL and OUTPUT_DIR before running.
"""

import os

# ── Entrez / NCBI ──────────────────────────────────────────────────────────────
# REQUIRED: NCBI asks every API user to supply a valid e-mail.
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "mouheb.mehdoui@protonmail.com")

# Optional: get a free API key at https://www.ncbi.nlm.nih.gov/account/
# Raises the rate-limit from 3 req/s to 10 req/s.
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "1d0228439f89df69b2aabbc6b2c14eaf2409")

# ── Output ─────────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

# ── PubMed / MEDLINE defaults ──────────────────────────────────────────────────
PUBMED_DEFAULT_QUERY   = "machine learning[MeSH] AND clinical[tiab]"
PUBMED_DEFAULT_MAX     = 200          # articles to fetch per run
PUBMED_BATCH_SIZE      = 100          # IDs per EFetch call
PUBMED_MIN_ABSTRACT_LEN = 100        # characters; skip very short stubs

# ── PMC full-text defaults ─────────────────────────────────────────────────────
PMC_DEFAULT_QUERY      = "diabetes[MeSH] AND free full text[filter]"
PMC_DEFAULT_MAX        = 50
PMC_MIN_PARAGRAPH_LEN  = 80          # characters; skip captions / headers

# ── Europe PMC defaults ────────────────────────────────────────────────────────
EUROPEPMC_DEFAULT_QUERY   = "cancer treatment"
EUROPEPMC_DEFAULT_MAX     = 1500000
EUROPEPMC_BASE_URL        = "https://www.ebi.ac.uk/europepmc/webservices/rest"
EUROPEPMC_MIN_PARAGRAPH_LEN = 80

# ── Request settings ───────────────────────────────────────────────────────────
REQUEST_TIMEOUT   = 30    # seconds
RETRY_ATTEMPTS    = 3
RETRY_BACKOFF     = 2.0   # seconds between retries
