# Medical Abstract & Paragraph Collector

A modular Python toolkit for collecting biomedical text from **PubMed**, **PubMed Central (PMC)**, and **Europe PMC** — ready for NLP training (summarization, simplification, NER, etc.).

---

## Project Structure

```
medical_collector/
├── config.py               ← Central settings (email, API key, paths)
├── utils.py                ← Shared helpers (retry, cleaning, saving)
├── pubmed_collector.py     ← PubMed abstracts via Entrez
├── pmc_collector.py        ← PMC full-text paragraphs via Entrez XML
├── europepmc_collector.py  ← Europe PMC abstracts + full text via REST API
├── pipeline.py             ← Master pipeline (all sources → merged dataset)
└── requirements.txt
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your NCBI email (required by NCBI)
Edit `config.py`:
```python
ENTREZ_EMAIL = "your_email@example.com"
```
Or use environment variables:
```bash
export ENTREZ_EMAIL="your_email@example.com"
export NCBI_API_KEY="your_optional_key"   # raises rate limit 3→10 req/s
```

### 3. Run the full pipeline
```bash
python pipeline.py --query "diabetes mellitus" --pubmed-max 300 --pmc-max 30 --europepmc-max 100
```

---

## Individual Collectors

### PubMed Abstracts
```bash
python pubmed_collector.py --query "cancer immunotherapy[MeSH]" --max 500 --output all
```

### PMC Full-text Paragraphs
```bash
python pmc_collector.py --query "COVID-19 treatment" --max 30 --output all
```

### Europe PMC
```bash
python europepmc_collector.py --query "Alzheimer disease" --max 100 --output all
```

---

## Output Files

All outputs go to `output/` (configurable in `config.py`):

| File | Description |
|---|---|
| `merged/all_records.json` | Full metadata + paragraphs (JSON) |
| `merged/all_records.csv` | Flat CSV (paragraphs joined with `\|\|`) |
| `merged/corpus.txt` | **One paragraph per line** — ready for LM training |
| `merged/stats.json` | Collection statistics |
| `pubmed/pubmed_abstracts.*` | PubMed-only outputs |
| `pmc/pmc_articles.*` | PMC-only outputs |
| `europepmc/europepmc_articles.*` | Europe PMC-only outputs |

---

## Record Schema

```json
{
  "pmid": "12345678",
  "pmcid": "PMC1234567",
  "doi": "10.1000/xyz123",
  "title": "Effect of metformin on ...",
  "abstract": "Background: ... Methods: ... Results: ...",
  "journal": "The Lancet",
  "year": "2023",
  "authors": "Smith J; Doe A",
  "keywords": "diabetes; metformin; glycemia",
  "paragraphs": ["Paragraph 1 text...", "Paragraph 2 text..."],
  "source": "PMC"
}
```

---

## Use as a Python Module

```python
from pubmed_collector import PubMedCollector
from pmc_collector import PMCCollector
from europepmc_collector import EuropePMCCollector

# PubMed abstracts
pm = PubMedCollector()
records = pm.collect(query="stroke rehabilitation", max_results=100)

# PMC full text paragraphs
pmc = PMCCollector()
articles = pmc.collect(query="BRCA1 mutation", max_results=20)
all_paras = [p for a in articles for p in a["paragraphs"]]

# Europe PMC
epmc = EuropePMCCollector()
results = epmc.collect(query="COVID-19 vaccine efficacy", max_results=50)
```

---

## Tips

- **Rate limits**: NCBI allows 3 requests/sec without an API key, 10/sec with one. Get a free key at https://www.ncbi.nlm.nih.gov/account/
- **PMC max**: Keep `--pmc-max` ≤ 50 per run to avoid timeouts on large XML files.
- **Paragraph quality**: Minimum paragraph length is set in `config.py` (`PMC_MIN_PARAGRAPH_LEN`, etc.).
- **Open access only**: Europe PMC full-text fetching is restricted to open-access articles automatically.
