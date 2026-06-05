# ENCODE `output_type` Use-Frequency

How often each ENCODE `output_type` term is actually used across files on the
ENCODE data portal. This informs which ONGA vocabulary terms to keep vs.
discard during ontology cleanup: terms with little or no real-world usage are
prime discard candidates.

## What's here

| File | Description |
|------|-------------|
| `fetch_frequencies.py` | Script that queries the ENCODE API and writes the tables below. |
| `raw_output_type_facet.json` | Raw API response from the facet query (provenance). |
| `output_type_frequencies.tsv` | Every ENCODE `output_type` we observed → `file_count`, sorted descending. |
| `seed_term_frequency.tsv` | The 310 ONGA seed terms reconciled against ENCODE: `term`, `in_encode` (yes/no), `file_count`, `dataset_count`. |

The 310 seed terms come from `../original-terms.md`.

## How to run

```bash
pip install requests            # optional; falls back to urllib if absent
python3 fetch_frequencies.py            # file counts only
python3 fetch_frequencies.py --datasets # also fetch per-term experiment counts (slower)
```

Data was captured **2026-06-04** against the live portal. Re-running updates
the numbers.

## API endpoint used

ENCODE's faceted search API returns ready-made counts:

```
https://www.encodeproject.org/search/?type=File&format=json&limit=0
```

The response's `facets` array contains an `output_type` facet with
`terms: [{key, doc_count}, ...]` — a frequency table in a single request.
Headers sent: `Accept: application/json` and a descriptive `User-Agent`.

**Caveat:** ENCODE caps each facet at ~200 terms. Our seed list has 310, so 110
seed terms fall outside the top-200 facet. For each of those the script issues
an individual exact-count query:

```
https://www.encodeproject.org/search/?type=File&output_type=<term>&limit=0
```

ENCODE returns HTTP 404 for a search with zero matches; the script treats that
as `file_count = 0`. Per-term dataset counts (with `--datasets`) use
`type=Experiment&files.output_type=<term>`.

## Findings (captured 2026-06-04)

- Total ENCODE File records indexed: **1,620,076**.
- Seed terms total: **310**.
- Seed terms with **ZERO** ENCODE file usage: **63** (prime discard candidates).
- ENCODE `output_type` values **not** in the seed list: **0** — the seed list
  covers every output_type that appears in the top-200 facet, so we have not
  missed any high-usage terms.

### Top 10 most-used `output_type` terms (by file count)

| file_count | output_type |
|-----------:|-------------|
| 548,648 | footprints |
| 162,022 | reads |
| 99,650 | signal p-value |
| 94,651 | alignments |
| 87,838 | peaks |
| 51,017 | fold change over control |
| 45,564 | unfiltered alignments |
| 35,272 | peaks and background as input for IDR |
| 30,774 | pseudoreplicated peaks |
| 29,326 | IDR thresholded peaks |

### Seed terms with zero ENCODE usage (63 — discard candidates)

3D structure; DNN-MPRA contribution scores; DNN-MPRA predicted signal;
allele-specific contact matrix; capture targets; cell topic participation;
consensus DNase hypersensitivity sites; diploid personal genome alignments;
element gene interactions p-value; enhancer-gene links; gene stabilities;
genic regions quantifications; haplotype-specific alignments; mRNA stabilities;
maternal haplotype mapping; maternal variant calls; miRNA annotations;
miRNA reference; minus strand transcription start sites;
mitochondrial exclusion list regions; motif clusters reference; motif model;
negative control regions; normalized bias-corrected predicted signal profile;
normalized observed signal profile; normalized predicted bias profile;
normalized predicted signal profile; novel peptides; observed bias profile;
paternal haplotype mapping; paternal variant calls; peptide quantifications;
phased mapping; phastcons score reference; plus strand transcription start sites;
positive control regions; predicted bias profile;
protein expression quantifications; raw data; raw minus strand signal;
raw normalized signal; raw plus strand signal; reference;
regulatory elements prediction model; repeat elements annotation;
repeats reference; representative IDR thresholded peaks; scaled RNA stability;
selected regions for bias-corrected predicted signal profile;
selected regions for count sequence contribution scores;
selected regions for predicted bias profile;
selected regions for predicted signal profile;
selected regions for predicted signal profile (minus strand);
selected regions for predicted signal profile (plus strand);
selected regions for profile sequence contribution scores; snRNA reference;
tRNA reference; topic gene weights; training set;
transposable element TF ancestral origin percent by motif;
transposable element TF ancestral origin percent by subfamily;
variant functional prediction; variant reference.

> Note: a zero file count means no *current* ENCODE File carries that
> `output_type`. Some of these may be newly-introduced schema terms not yet
> populated, or deprecated/renamed terms; treat the list as a starting point
> for review rather than an automatic delete list. The full per-term table is
> in `seed_term_frequency.tsv`.
