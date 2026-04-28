# 🧠 BioMed-Simplify-Dataset

A curated biomedical text collection built for **medical NLP research**, focusing on:

- Medical text simplification
- Summarization
- Named Entity Recognition (NER)
- Biomedical language modeling

This repository aggregates high-quality open-access biomedical corpora from major scientific sources such as PubMed Central, PubMed, BioNLP corpora, and Europe PMC.

---

## 📊 Dataset Sources

### 🧪 1. PubMed Central (PMC)
- 🔗 https://www.ncbi.nlm.nih.gov/pmc/
- Full-text biomedical research articles
- Includes abstracts + full papers
- Open-access (CC BY license where applicable)

**Use cases:**
- Text simplification
- Summarization
- Medical NLP pretraining
- Information extraction

---

### 📄 2. PubMed / MEDLINE Abstracts
- 🔗 https://pubmed.ncbi.nlm.nih.gov/
- Millions of structured biomedical abstracts
- Accessible via Entrez API

**Use cases:**
- Sentence simplification
- Classification
- Readability modeling
- Large-scale language modeling

---

### 🧬 3. BioNLP Shared Task Corpora
- 🔗 http://2013.bionlp-st.org/
- Curated biomedical NLP datasets
- Includes annotated corpora such as:
  - NCBI Disease Corpus
  - GENIA Corpus
  - BioCreative datasets

**Use cases:**
- Named Entity Recognition (NER)
- Relation extraction
- Event extraction

---

### 📚 4. Europe PMC Annotated Corpus
- 🔗 https://europepmc.org/
- Full-text biomedical articles
- Includes manual annotations:
  - Genes
  - Diseases
  - Proteins

**Use cases:**
- Biomedical entity recognition
- Structured text understanding
- Multi-task NLP training

---

## 🎯 Project Goal

This repository aims to build a unified dataset for:

> 🧠 **Medical Text Simplification and Biomedical NLP Research**

The goal is to transform complex biomedical literature into:
- Simplified medical explanations
- Patient-friendly text
- Readable summaries

---

## 🧰 Potential Applications

- Medical text simplification models
- LLM fine-tuning for healthcare
- Clinical NLP pipelines
- Biomedical summarization systems
- Educational health AI tools

---

## ⚙️ Data Format (planned)

Data will be structured as:

```json
{
  "source": "PubMed Central",
  "title": "",
  "abstract": "",
  "full_text": "",
  "annotation_text": ""
}
