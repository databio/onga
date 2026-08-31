# ONGA Embeddings

Compare ONGA (Ontology for Genomic Annotations) terms against established genomics ontologies using semantic embeddings.

## Purpose

ONGA defines ~325 terms across DataType and FeatureType vocabularies. This tool:

1. Finds semantically similar terms within ONGA that could be merged
2. Identifies mappings to established ontologies
3. Discovers gaps where ONGA lacks coverage for common concepts

## Ontology Coverage

| Ontology | Type | Terms | Format | Parser |
|----------|------|-------|--------|--------|
| EDAM | Bioinformatics operations, data types, formats | ~3,500 | OWL | pronto |
| OBI | Biomedical investigations, assay types | ~4,500 | OWL | pronto |
| GO | Gene Ontology basic subset | ~45,000 | OBO | stdlib |
| SO | Sequence features, genomic annotations | ~2,400 | OBO | stdlib |
| CL | Cell Ontology — cell types | ~19,000 | OBO | stdlib |
| UBERON | Anatomy/tissues basic subset | ~26,000 | OBO | stdlib |
| EFO | Experimental Factor Ontology | ~84,000 | OBO | stdlib |
| CLO | Cell Line Ontology — cell lines in research | ~43,000 | OWL | pronto |

OBO files are read by `onga_embeddings.ontology_loader.parse_obo`, a stanza parser
that uses the standard library only — pronto 2.7.x cannot parse several of these
releases, and `obonet` is no longer needed. OWL files still need `pronto`, which is
imported lazily and lives in the optional `owl` extra, so nothing else in the
package breaks when it is absent.

## Matching

Every ontology is searched two ways, and the two are blended into one candidate list:

| Match kind | Where it comes from | What it means |
|------------|--------------------|---------------|
| `lexical` | `LexicalIndex.search` | The whole ONGA name (or its singular) is a label or synonym |
| `lexical-suffix` | `LexicalIndex.search` | Only the head noun matches, e.g. `candidate enhancers` → `enhancer` |
| `embedding` | `SimilaritySearcher` | Cosine similarity over PubMedBERT embeddings |

Lexical matching is not optional polish. Embeddings rank SO:0000165 `enhancer` at
cosine ~0.31 for the ONGA term `candidate enhancers` — far down the list — because
the leading derivation facet ("candidate", "predicted", "curated") dominates the
sentence embedding. The head-noun matcher finds it immediately. Against SO, 16 of
237 ONGA terms have an exact label/synonym match and 61 have a head-noun match.

`SimilaritySearcher.find_candidates(ontology)` returns the blended list: lexical
hits first, then the top embedding hits, de-duplicated by ontology term id, each
labelled with its match kind and cosine score.

## Installation

```bash
pip install -e .          # OBO ontologies (SO, GO, CL, UBERON, EFO)
pip install -e '.[owl]'   # adds pronto, needed only for OWL (EDAM, OBI, CLO)
```

## Usage

```python
from onga_embeddings import LexicalIndex, SimilaritySearcher, load_ontology, parse_onga

# Parse ONGA vocabulary
onga_terms = parse_onga("/path/to/file_content.yaml")
print(f"Loaded {len(onga_terms)} ONGA terms")

# Load external ontology (OBO needs no third-party parser)
so_terms = list(load_ontology("data/ontologies/so.obo", "so"))
print(f"Loaded {len(so_terms)} SO terms")

# Lexical search on its own
index = LexicalIndex(so_terms)
hit = index.search("candidate enhancers")[0]
print(hit.term.id, hit.match_kind)     # SO:0000165 lexical-suffix

# Blended lexical + embedding candidates (needs built .npz files)
searcher = SimilaritySearcher("data/embeddings")
for candidate in searcher.find_candidates_for_term("so", "candidate enhancers"):
    print(candidate.rank, candidate.match_kind, candidate.match_id, candidate.score)
```

## Workflow

```bash
# 1. Download ontologies
python scripts/download_ontologies.py --all

# 2. Build embeddings (skips already-built files)
python scripts/build_embeddings.py

# 3. Run comparison (embedding-only reports)
python scripts/run_comparison.py

# 4. Blended lexical + embedding candidate TSV for curation
python scripts/run_comparison.py --ontology so --candidates
python scripts/run_comparison.py --ontology edam --candidates

# 5. Generate HTML viewer
python scripts/generate_viewer.py
```

The candidate TSV lands at `outputs/reports/<ontology>_candidates.tsv` and feeds
manual curation into `mappings/<ontology>.sssom.tsv`.

## Project Structure

```
onga-embeddings/
  onga_embeddings/
    __init__.py
    onga_parser.py        # Parse ONGA LinkML YAML
    ontology_loader.py    # OBO via stdlib parse_obo; OWL via lazily-imported pronto
    lexical_match.py      # Normalisation, singularisation, head-noun LexicalIndex
    embedding_model.py    # sentence-transformers wrapper (lazy import)
    similarity_search.py  # Embedding search + blended candidate search
    report_generator.py   # JSON/Markdown reports
  data/
    ontologies/           # Downloaded OWL/OBO files
    embeddings/           # Cached embeddings (.npz)
  outputs/
    reports/              # Generated comparison reports
    viewer.html           # Interactive HTML viewer
  scripts/
    download_ontologies.py
    build_embeddings.py
    run_comparison.py
    generate_viewer.py
  tests/
    test_parsers.py
    test_lexical_match.py
    test_similarity_search.py
    test_report_generator.py
```
