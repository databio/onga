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
| GO | Gene Ontology basic subset | ~45,000 | OBO | pronto |
| SO | Sequence features, genomic annotations | ~2,400 | OBO | obonet |
| CL | Cell Ontology — cell types | ~19,000 | OBO | obonet |
| UBERON | Anatomy/tissues basic subset | ~26,000 | OBO | obonet |
| EFO | Experimental Factor Ontology | ~84,000 | OBO | obonet |
| CLO | Cell Line Ontology — cell lines in research | ~43,000 | OWL | pronto |

OBO files that pronto 2.7.x cannot parse (SO, CL, UBERON, EFO) are automatically loaded via `obonet` as a fallback parser.

## Installation

```bash
pip install -e .
```

## Usage

```python
from onga_embeddings import parse_onga, load_ontology

# Parse ONGA vocabulary
onga_terms = parse_onga("/path/to/file_content.yaml")
print(f"Loaded {len(onga_terms)} ONGA terms")

# Load external ontology
edam_terms = list(load_ontology("data/ontologies/edam.owl", "edam"))
print(f"Loaded {len(edam_terms)} EDAM terms")
```

## Workflow

```bash
# 1. Download ontologies
python scripts/download_ontologies.py --all

# 2. Build embeddings (skips already-built files)
python scripts/build_embeddings.py

# 3. Run comparison
python scripts/run_comparison.py

# 4. Generate HTML viewer
python scripts/generate_viewer.py
```

## Project Structure

```
onga-embeddings/
  onga_embeddings/
    __init__.py
    onga_parser.py        # Parse ONGA LinkML YAML
    ontology_loader.py    # Parse OWL/OBO via pronto + obonet fallback
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
```
