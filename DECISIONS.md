# ONGA Decision History

How the ONGA vocabulary was derived from the ENCODE `output_type` term list.
Each entry is **one operation** applied to the term set, in order — read top to
bottom to trace how we got from the raw ENCODE list to the current ontology.

Keep entries short: one or two sentences (what we did + why). Append new
decisions at the bottom as curation proceeds. Record term-level cleanup
operations (merges, deletions, recategorizations) here too, so the path from
ENCODE to "final" stays fully traceable.

## Starting point

**ENCODE `output_type` vocabulary** — ~310 terms from the ENCODE file schema
(<https://www.encodeproject.org/profiles/file/>), the authoritative seed list
for file content types. We took these verbatim as the initial term set.

## Operations

1. **Seeded from ENCODE** — Imported all ~310 ENCODE `output_type` terms as the
   starting vocabulary, with no terms dropped or renamed, so the derivation
   begins from a known, citable baseline.

2. **Categorized into 22 subsets** — Grouped the terms into 22 thematic
   categories (LinkML `subsets`: alignment, signal_track, peak_set,
   chromatin_accessibility, contact_matrix, etc.) to give the flat ENCODE list
   a navigable top-level structure.

3. **Mapped to EDAM** — Added `meaning:` cross-references to EDAM terms for the
   ~84 terms with a direct or close EDAM match (SSSOM mappings in
   `mappings/edam.sssom.tsv`), anchoring ONGA to an established ontology where
   possible.

4. **Split into two vocabularies** — Separated the single `output_type` enum into
   two complementary vocabularies: **DataType** (218 terms — *how* data was
   computationally produced, e.g. "peaks" from a peak caller) and **FeatureType**
   (92 terms — *what* biology it represents, e.g. "TF binding sites"), linked by
   `see_also`. The same DataType can carry different FeatureTypes depending on
   the experiment, which a single flat list could not express.

5. **Enhanced definitions** — Rewrote 203 of the 310 term definitions to be more
   informative (e.g. explaining what IDR is, clarifying plus/minus strand
   meaning, expanding compositional terms), since many ENCODE terms shipped with
   terse or absent descriptions.

6. **Faceted out strand and read_set** — Factored two orthogonal asserted axes
   baked into compound DataType strings into their own facet vocabularies and
   `TrackInterpretation` slots: **StrandOrientation** (plus/minus/unstranded/
   bidirectional, `src/strand_orientation.yaml`, `strand` slot) and **ReadSet**
   (all reads/unique reads, `src/read_set.yaml`, `read_set` slot). Strand and
   read_set are orthogonal qualifiers, not distinct interpretations, so they
   belong on TrackInterpretation as facets (per the descriptor-schemas ADR and
   FGA-WG issue #2). The lossless ENCODE↔ONGA round-trip is preserved in
   `mappings/facet_decomposition.tsv` (32 compound terms decomposed; 10 have
   `base_exists=no`, flagging atomic output_type terms the removal step must
   add). This step is **additive only**: the compound DataType terms are NOT yet
   removed — that is a separate reviewed step driven by this map. Other
   qualifiers (normalized/observed/predicted/raw/selected regions/unfiltered)
   remain baked into the base as deferred axes.

7. **Applied the strand/read_set decomposition** — Executed the removal step
   deferred by operation #6, driven by `mappings/facet_decomposition.tsv`:
   removed the 32 compound DataType terms (every `encode_term` in the map) and
   added the 6 distinct atomic base `output_type`s flagged `base_exists=no`
   (`end position signal`, `normalized end position signal`, `normalized
   signal`, `observed control profile`, `unfiltered sparse gene count matrix`,
   `unfiltered sparse splice junction count matrix`), with descriptions
   generalized from their compound siblings and subsets matched to those
   siblings (signal_track / count_matrix). DataType 218 → 192. The removed
   compound terms remain losslessly recoverable via the map plus the new
   `TrackInterpretation` facet slots, with ENCODE round-trip
   `compound term = output_type + strand + read_set`. This completes operation
   #6, which was additive-only. (Net is +6 distinct bases, not the +10 rows in
   the map: 10 rows carry `base_exists=no` but they name only 6 distinct
   atomic output_types, so the final count is 192 rather than 196.)

8. **Renamed ReadSet → ReadMultiplicity** — Renamed the `ReadSet` facet
   vocabulary to `ReadMultiplicity` (`src/read_set.yaml` →
   `src/read_multiplicity.yaml`; enum, id, `TrackInterpretation` slot `read_set`
   → `read_multiplicity`, and the TSV/site references). Values (`all reads` /
   `unique reads`) and descriptions are unchanged. Rationale: this axis is the
   read **mapping-multiplicity** axis (all mapped reads vs uniquely-mapping reads
   only) and is read-specific; the clearer name distinguishes it from the QC
   filtering axis introduced next. Developmental software — renamed cleanly, no
   aliases or back-compat.

9. **Faceted out filter_status** — Factored the QC filtering qualifier baked
   into compound DataType strings into a new facet vocabulary **FilterStatus**
   (`filtered` / `unfiltered`, `src/filter_status.yaml`) and a `filter_status`
   slot on `TrackInterpretation`. Unlike read-multiplicity, filtering is not
   read-specific — it spans reads, alignments, peaks, variants, quantifications,
   and count matrices — hence `FilterStatus`, not `ReadFilter`. Decomposed the
   **10** compound filter terms present in the enum (`filtered reads`,
   `unfiltered alignments`, `redacted unfiltered alignments` [`redacted` left
   baked in as a deferred axis], `filtered peaks`, `filtered peptide
   quantification`, `unfiltered peptide quantification`, `filtered/unfiltered
   modified peptide quantification`, `unfiltered sparse gene count matrix`,
   `unfiltered sparse splice junction count matrix`) and minted the **2** atomic
   bases flagged `base_exists=no` (`modified peptide quantification`,
   `sparse splice junction count matrix`), with descriptions generalized from
   their compound siblings and subsets matched (quantification / count_matrix).
   DataType **192 → 184**. This is a chained decomposition: the two `unfiltered
   sparse … count matrix` terms were themselves bases minted in operation #7, and
   now decompose further onto the filter axis (facets compose). The round-trip
   `compound term = output_type + filter_status` is preserved in
   `mappings/facet_decomposition.tsv` (filter rows). `rejected reads` and
   `filtered regions` are deliberately **kept whole as atomic leaves**: they name
   the *discarded / excluded complement set* (the reads thrown out; regions
   removed from analysis — a sibling of `exclusion list regions`), an identity
   rather than `reads`/`regions` carrying a filter status, so no facet applies.
   (Three terms named in the working plan — `filtered indels`, `filtered SNPs`,
   `filtered transcribed fragments` — were **not** present in the enum and were
   therefore not decomposed; the matching `indels` / `SNPs` / `transcribed
   fragments` bases were not minted. Net is +2 distinct bases, not +4: with no
   `filtered indels`/`SNPs` compound source there is nothing to decompose onto
   them, so the count is 184, not the plan's projected 183.)

10. **Introduced TrackProvenance schema** — Added a 4th descriptor schema,
    `TrackProvenance` (`src/track_provenance.yaml`), separating *what was done to
    the data* (processing/derivation operations) from *what the data is*
    (`TrackInterpretation`). Relocated the `read_multiplicity` and
    `filter_status` slots out of `TrackInterpretation` into `TrackProvenance`;
    the facet vocabularies `ReadMultiplicity` and `FilterStatus` were unchanged
    (only the two *slots* re-homed). `TrackInterpretation` now keeps exactly
    three slots — `output_type`, `feature_type`, `strand`. Rationale: the
    "murky" axes that resisted placement (read selection, filtering,
    normalization, observed/predicted, bias-correction) were murky because they
    describe **processing provenance, not content** — `output_type` names a
    result KIND (a noun, "peaks") while these name OPERATIONS applied to the
    data; provenance is their natural home. `strand` is intrinsic content and
    stays in interpretation. No vocabulary terms, DataType/FeatureType enums,
    geometry, or biospecimen were touched — a pure schema reorganization.
    `TrackProvenance` is the planned home for normalization-scaling, derivation
    (observed/predicted), and bias-correction when those axes are faceted out of
    the compound DataType base (deferred — not added now). Developmental
    software — clean cut-and-move, no back-compat shims.

11. **Faceted out normalization-scaling** — Factored the scaling-normalization
    qualifier baked into compound DataType strings into a new facet vocabulary
    **Normalization** (`raw` / `depth_normalized` / `percentage_normalized`,
    `src/normalization.yaml`, absent = unspecified, NOT raw) and a
    `normalization` slot on **`TrackProvenance`** — the first normalization facet
    on the provenance schema (beyond the relocated read_multiplicity /
    filter_status). Decomposed **11** compound scaling terms (`raw signal`,
    `normalized signal`, `read-depth normalized signal`, `raw normalized
    signal`, `percentage normalized signal`, `normalized end position signal`,
    `normalized observed signal profile`, `normalized predicted signal
    profile`, `normalized predicted bias profile`, `normalized bias-corrected
    predicted signal profile`, `depth normalized signals matrix`) and minted the
    **1** atomic base flagged `base_exists=no` (`signals matrix`, count_matrix
    subset, description generalized from its `depth normalized` sibling). The
    round-trip `compound term = output_type + normalization` is preserved in
    `mappings/facet_decomposition.tsv` (normalization column). **MERGE:** three
    synonyms — `normalized signal`, `read-depth normalized signal`, and `raw
    normalized signal` (raw signal after library-size normalization = depth-
    normalized) — all collapse onto `signal` + `depth_normalized`, a deliberate
    non-1:1 ENCODE→ONGA collapse the curator approved; the map records all three
    rows so ENCODE→ONGA stays well-defined while ONGA→ENCODE is intentionally
    ambiguous for these. **Kept as distinct output_types** (they change what the
    values *mean*, not the scaling): the statistic transforms `signal p-value`,
    `fold change over control`, `control normalized signal`, `enrichment`,
    `z scores matrix`, `fold over change matrix`. **Deferred:** the smoothing
    terms `wavelet-smoothed signal` and `summed densities signal` (2 terms, a
    distinct transform, not scaling). DataType **184 → 174**. This is the first
    normalization facet on the provenance schema; bias-correction and derivation
    (observed/predicted/control) remain deferred there. Developmental software —
    clean removals, no back-compat.

## Design principles

Rules established in design discussion that govern the faceting operations above:

1. **Facets are conditional on the base type.** A facet has a domain of
   applicability — it is not a universal column added to every term. A term to
   which no facet meaningfully applies stays an **atomic leaf**. This is why
   `rejected reads` and `filtered regions` are kept whole: they name the
   discarded / excluded complement set (an identity), not a base type carrying a
   filter status, so the `filter_status` facet does not apply to them.

2. **Facets vs. tags.** Mutually-exclusive value groups (e.g. `all reads` |
   `unique reads`; `filtered` | `unfiltered`) are modeled as **separate
   single-valued facet slots**, not as one multivalued tag/flag bag. Separate
   slots enforce within-axis exclusivity for free and self-document the axis. A
   multivalued tag/flag slot (SAM-FLAG style) is reserved for clusters of
   genuinely independent booleans.

3. **The formal frame is faceted classification.** Each facet is one controlled,
   single-valued axis (strand, read_multiplicity, filter_status, …) drawing on a
   closed Layer-1 vocabulary — not flat tagging.

4. **Content vs. provenance.** A descriptor belongs in `TrackInterpretation` if
   it answers *what the data is* (content: `output_type` names a result kind;
   `feature_type` names the biology; `strand` is intrinsic content) and in
   `TrackProvenance` if it answers *what was done to it* (processing/derivation
   operations applied: read selection, QC filtering, and the planned
   normalization, observed/predicted derivation, and bias-correction). This is
   the test that disambiguated the "murky" axes: they name operations, not
   content, so they are provenance, not interpretation.

## Current state

- **DataType:** 174 terms (58 with EDAM `meaning:`)
- **FeatureType:** 92 terms (21 with EDAM `meaning:`)
- **Categories:** 22 subsets
- **Total:** 266 terms, 84 EDAM-mapped

## Tooling note

An embedding-comparison tool (`embeddings/`) compares ONGA terms against EDAM,
OBI, GO, SO, CL, UBERON, and EFO to surface merge candidates (149 internal
similar pairs), coverage gaps (23 terms), and mapping suggestions. Its findings
drive the term-cleanup decisions recorded below — but the analysis itself does
not change the vocabulary; only the operations logged here do.

## Cleanup decisions

_(in progress — term cleanup operations will be appended here as we curate via
the Develop dashboard)_
