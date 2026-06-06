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
   **Correction (operation #12):** the claim that these three terms were "not
   present in the enum" was WRONG — this #9 filter pass only scanned **DataType**.
   `filtered indels` / `filtered SNPs` / `filtered transcribed fragments` are in
   **FeatureType**, and were decomposed onto `filter_status:filtered` in
   operation #12 below. The DataType count and the +2-bases tally for this #9 step
   are unaffected (those FeatureType terms were always out of #9's scope).

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

12. **Extended strand + filter_status facets to FeatureType** — The `strand`
    (StrandOrientation) and `filter_status` (FilterStatus) facets, previously
    applied only to compound **DataType** strings (operations #6/#7 and #9), were
    extended to the **FeatureType** enum, where the same orthogonal qualifiers
    were still baked into compound term strings. No new vocabularies or slots were
    created — only FeatureType compound terms decomposed and recorded losslessly.
    **Strand (14 terms):** decomposed `{plus,minus} strand methylation state at
    CpG`, `{plus,minus} strand transcription start sites`, and the ten
    `{plus,minus} strand {inosine,m5C,m6A,Nm,pseudouridine} methylation state`
    RNA-modification terms as `feature_type base + strand:{plus|minus}`. Bases
    `methylation state at CpG` and `transcription start sites` already existed; the
    **5** RNA-modification bases (`inosine methylation state`, `m5C methylation
    state`, `m6A methylation state`, `Nm methylation state`, `pseudouridine
    methylation state`) were minted (`rna_modification` subset, descriptions
    generalized from the strand-specific siblings). `smoothed methylation state at
    CpG` was left untouched — smoothing is a separate axis and that term will share
    the `methylation state at CpG` base later. **Filter (3 terms):** decomposed
    `filtered indels`, `filtered SNPs`, `filtered transcribed fragments` as
    `feature_type base + filter_status:filtered`; `transcribed fragments` already
    existed, and `indels` / `SNPs` were minted (`variant` subset, `meaning:
    edam:data_0918`, descriptions generalized). This **corrects operation #9's
    record**, which wrongly claimed those three terms were "not present in the
    enum" (the #9 pass only scanned DataType). **TSV column added:** a new
    `feature_type` column (immediately after `output_type`) now holds the atomic
    base for FeatureType decompositions; it is empty for the existing DataType
    rows, which keep their base in `output_type`. The round-trip is preserved in
    `mappings/facet_decomposition.tsv` (17 new rows): strand-row compound =
    `feature_type + strand`, filter-row compound = `feature_type + filter_status`.
    FeatureType **92 → 82** (−17 compound, +7 minted bases). DataType unchanged
    (174). Applied via `scripts/apply_feature_strand_filter.py` (ruamel
    round-trip). Developmental software — clean removals, no back-compat.

13. **Faceted out the thresholding cut** — Factored the retention-cut /
    thresholding qualifier baked into compound DataType strings into a new facet
    vocabulary **Thresholding** (`idr` / `mapping_quality` / `significance`,
    `src/thresholding.yaml`, absent = no threshold / unspecified) and a
    `thresholding` slot on **`TrackProvenance`** — a provenance facet, since
    thresholding is a processing OPERATION (a retention cut), not content
    (content-vs-provenance test, design principle #4). The vocab carries no
    `meaning:` CURIEs, following the processing-facet convention of
    ReadMultiplicity / FilterStatus / Normalization. **Decomposed 4 compound
    terms** (verified present in the live enums) — 2 in **DataType** and 2 in
    **FeatureType**:
    - DataType: `IDR thresholded peaks` → `peaks` + `thresholding:idr`, and
      `mapping quality thresholded contact matrix` → `contact matrix` +
      `thresholding:mapping_quality`. Both bases already existed.
    - FeatureType (`element_gene_linkage` subset): `thresholded element gene
      links` → `element gene links` + `thresholding:significance` (base
      existed), and `thresholded links` → `links` + `thresholding:significance`
      (base **minted** — generic regulatory-links base, description "Generic
      regulatory links associating genomic elements with target features.", no
      `meaning:` CURIE, following its sibling `element gene links`).
    **Minted: 1 FeatureType base (`links`).** The round-trip `compound term =
    output_type/feature_type + thresholding` is preserved in
    `mappings/facet_decomposition.tsv` (a new `thresholding` column was inserted
    immediately before `base_exists`, empty-backfilled for all prior rows; 4 new
    rows appended — 2 DataType, 2 FeatureType). DataType **174 → 172**;
    FeatureType **82 → 81** (−2 compound, +1 minted base).
    **Scope — cut only, deliberately narrow.** The reproducibility /
    selection-mode axis (`conservative/optimal/representative/pseudoreplicated
    IDR thresholded peaks`, `replicated peaks`, `pseudoreplicated peaks`,
    `representative/consensus DNase hypersensitivity sites`) was deliberately
    **NOT** faceted: no `ReproducibilitySelection` vocabulary was created and
    those 11+ terms stay atomic. Rationale: the selection-mode axis is borderline
    cross-cutting (it is concentrated in peak/DHS reproducibility outputs rather
    than spanning many output kinds the way idr/mapping-quality thresholds do),
    so the faceting payoff is low and it is deferred pending broader evidence.
    Those terms (plus `peaks and background as input for IDR`, `IDR ranked
    peaks`, `ranked gRNAs`) are guarded as PROTECTED in
    `scripts/apply_thresholding_decomposition.py` and confirmed intact after the
    run (11/11).
    **Correction (FeatureType terms were real, not hallucinated).** A first pass
    of this operation wrongly concluded that `thresholded element gene links` and
    `thresholded links` did not exist and refused to decompose them. That check
    scanned only the **DataType** enum; both terms are in fact live members of the
    **FeatureType** enum (`element_gene_linkage` subset), as is the base `element
    gene links`. They were re-verified against live `src/file_content.yaml` and
    decomposed onto `thresholding:significance` in this same operation (see the
    FeatureType bullet above), minting the generic `links` base. The
    `significance` permissible value in `src/thresholding.yaml` is therefore now
    in use. The DataType decomposition was applied via
    `scripts/apply_thresholding_decomposition.py`; the FeatureType decomposition
    via `scripts/apply_thresholding_featuretype.py` (both ruamel round-trip).
    Developmental software — clean removals, no back-compat.

14. **Faceted out derivation (observed vs. predicted)** — Factored the
    measured-vs-model qualifier baked into compound DataType / FeatureType
    strings into a new facet vocabulary **Derivation** (`observed` / `predicted`,
    `src/derivation.yaml`, absent = unspecified, NOT a default of observed) and a
    `derivation` slot on **`TrackProvenance`** — a provenance facet, since
    derivation records the epistemic ORIGIN of the values (how they were
    obtained: empirically measured vs. model-generated), a processing/derivation
    operation, not content (content-vs-provenance test, design principle #4). The
    vocab carries no `meaning:` CURIEs, following the processing-facet convention
    of ReadMultiplicity / FilterStatus / Normalization / Thresholding.
    **Decomposed 6 compound terms** (verified present in the live enums) — 5 in
    **DataType**, 1 in **FeatureType**:
    - DataType: `observed signal profile` / `predicted signal profile` →
      `signal profile` + `derivation:{observed|predicted}`; `observed bias
      profile` / `predicted bias profile` → `bias profile` +
      `derivation:{observed|predicted}`; `observed control profile` → `control
      profile` + `derivation:observed`.
    - FeatureType: `predicted transcription start sites` → `transcription start
      sites` (base ALREADY EXISTED) + `derivation:predicted`.
    **Minted 3 DataType bases** (all `signal_track` subset, descriptions
    generalized from the observed/predicted siblings with derivation language
    stripped): `signal profile` ("Signal profile across genomic positions."),
    `bias profile` ("Sequencing bias profile across genomic positions."), and
    `control profile` ("Control signal profile."). DataType **172 → 170** (−5
    compound, +3 minted bases); FeatureType **81 → 80** (−1 compound, no mint).
    **`control` is deliberately EXCLUDED from the vocabulary.** In the source
    terms "control" denotes unrelated things — an experimental role (control vs.
    treatment) or a normalization reference (control-normalized) — not the
    measured-vs-model axis. So Derivation is a clean two-value enum
    `{observed, predicted}`, and control-role terms (`control normalized signal`,
    `fold change over control`, `negative/positive control regions`) stay atomic
    and are NOT decomposed onto this facet. (`observed control profile` IS
    decomposed — there the "control" lives in the minted `control profile` base
    and "observed" is the derivation; that base is itself a control-role term.)
    **CHAINED TSV RECONCILIATION.** Removing the four `observed/predicted
    signal/bias profile` compound bases from the enum dangled nine existing TSV
    rows that used them as their `output_type` base. Each was re-pointed to the
    new stripped base (`signal profile` / `bias profile` / `control profile`) with
    its `derivation` column set accordingly, preserving its other facet columns —
    so e.g. `normalized observed signal profile` becomes `signal profile` +
    `normalization:depth_normalized` + `derivation:observed`, and `observed signal
    profile (plus strand)` becomes `signal profile` + `strand:plus` +
    `derivation:observed`: genuine multi-axis compounds. Re-pointed rows (9):
    `observed control profile (minus/plus strand)`, `observed signal profile
    (minus/plus strand)`, `predicted signal profile (minus/plus strand)`,
    `normalized observed signal profile`, `normalized predicted signal profile`,
    `normalized predicted bias profile`. The round-trip `compound term =
    output_type/feature_type + derivation (+ other facets)` is preserved in
    `mappings/facet_decomposition.tsv` (a new `derivation` column was inserted
    immediately before `base_exists`, empty-backfilled for all prior rows; 6 new
    plain-form rows appended — 5 DataType, 1 FeatureType). Round-trip closure was
    re-verified transitively: every one of the 80 TSV rows' bases resolves in the
    live enums (the `normalized … profile` rows chain through the re-pointed
    rows down to the minted bases). Applied via
    `scripts/apply_derivation_decomposition.py` (ruamel round-trip).
    **Deferred / out of scope (left atomic, guarded PROTECTED, confirmed intact
    after the run):** bias-correction (`bias-corrected predicted signal profile`),
    the entire `selected regions for predicted …` family (signal profile, bias
    profile, bias-corrected predicted signal profile, predicted signal and
    sequence contribution scores), the enhancer family (`predicted enhancers`,
    `predicted forebrain/heart/whole brain enhancers` — handled by a separate
    scope-ejection agent), assay-fused predicted signals (`DNN-MPRA predicted
    signal`, `HMM predicted chromatin state`), and `predicted 3D structural
    ensembles` (base doesn't exist). These carry `predicted` but are entangled
    with other unfactored axes (bias-correction, selection, assay fusion, scope),
    so faceting them is deferred. Developmental software — clean removals, no
    back-compat.

15. **Introduced ReferenceGenome schema + ReferenceBuildSex vocab; faceted out
    reference-build sex; ejected sample anatomy to UBERON.** Two distinct moves
    that both removed anatomy/sex-leaking content terms, but along different
    boundaries — one a lossless ONGA facet, the other a scope ejection.
    - **ReferenceGenome — a NEW 5th descriptor schema.** Added
      `src/reference_genome.yaml`, a class `ReferenceGenome` parallel to
      TrackFormat / TrackInterpretation / TrackProvenance / TrackGeometry, for
      the reference assembly a track is defined against (FGA-issue adjacent:
      every genomic annotation is relative to a reference). Slots (minimal):
      `assembly` (string identifier, e.g. GRCh38/mm10) and `build_sex` (range
      `ReferenceBuildSex`). **Class-naming choice:** the four existing schemas use
      a `Track*` prefix, but this one describes the REFERENCE, not the track, so
      it is named `ReferenceGenome` (NOT `TrackReference`); the others were not
      renamed. Imports `reference_build_sex`; both `reference_genome` and
      `reference_build_sex` added to `src/onga.yaml` imports.
    - **ReferenceBuildSex — a NEW Layer-1 facet vocabulary.** Added
      `src/reference_build_sex.yaml`, enum `ReferenceBuildSex` with `male`
      (`PATO:0000384`, assembly with X and Y) / `female` (`PATO:0000383`,
      assembly with X only); absent = unspecified / sex-neutral combined
      assembly. This records the sex of the reference BUILD (which sex
      chromosomes the assembly contains), NOT the sample's sex.
    - **Sex faceting (DataType, lossless facet).** Removed the 4 compound
      DataType terms `male/female genome reference` and `male/female genome
      index` (verified live in DataType), decomposing each onto its
      already-existing atomic base (`genome reference` / `genome index`,
      verified — NO mint) + `build_sex:{male|female}`. A new
      `reference_build_sex` column was inserted immediately before `base_exists`
      in `mappings/facet_decomposition.tsv` (empty-backfilled for all prior
      rows); 4 new rows appended. DataType **170 → 166** (−4, no mint).
    - **Anatomy ejection (FeatureType, scope delegation — NOT a facet).** Removed
      the 3 compound FeatureType terms `predicted forebrain enhancers`,
      `predicted heart enhancers`, `predicted whole brain enhancers` (verified
      live in FeatureType), collapsing each onto the already-existing content
      base `predicted enhancers` (verified — NO mint; it retains its baked
      `predicted`, the enhancer-family derivation being deferred). The tissue
      (forebrain / heart / brain) is a BIOSPECIMEN property, genuinely out of
      ONGA's content scope, so it is **delegated to UBERON**
      (`UBERON:0001890` / `UBERON:0000948` / `UBERON:0000955`) and recorded in a
      NEW boundary map `mappings/scope_delegations.tsv` (header
      `encode_term, content_enum, content_base, delegated_axis, delegated_value,
      external_curie, note`), aligned to the future `organism_part` slot of the
      biospecimen module (FAIRtracks `sample.sample_type.organism_part`, UBERON
      range). This is a SCOPE EJECTION, NOT a facet — it lives in
      `scope_delegations.tsv`, not `facet_decomposition.tsv`. FeatureType
      **80 → 77** (−3, no mint).
    Applied via `scripts/apply_reference_sex_and_anatomy.py` (ruamel
    round-trip, no mints). Round-trip closure re-verified: the 7 compounds are
    gone, the 3 bases (`genome reference`, `genome index`, `predicted enhancers`)
    intact, all 84 facet-map rows resolve in the live enums (sex rows resolve
    directly), and the 3 scope-delegation content bases resolve. Developmental
    software — clean removals, no back-compat.

16. **Merged synonym `enhancer-gene links` → `element gene links`.** The two
    were near-duplicate original ENCODE seed terms naming the same concept
    (enhancers are the common case of "regulatory elements"); `enhancer-gene
    links` (regulatory_element subset) carried a leftover "Moved to
    element_gene_linkage" editorial note shipped as its definition — evidence of
    an abandoned consolidation. Merged onto the canonical `element gene links`
    (element_gene_linkage subset — already the base the `thresholding` facet
    points to): added `aliases: [enhancer-gene links]` to the canonical term,
    enriched its description ("regulatory elements (commonly enhancers)"), and
    removed the standalone term. The ENCODE round-trip is preserved — a synonym
    row (`enhancer-gene links → element gene links`, no facets, base_exists=yes)
    is recorded in `mappings/facet_decomposition.tsv`. FeatureType **77 → 76**
    (−1, no mint). Applied via `scripts/apply_gene_links_merge.py`.

17. **Faceted out haplotype resolution — the second intrinsic-CONTENT facet.**
    Factored the allele/haplotype phasing qualifier baked into compound
    DataType / FeatureType strings into a new facet vocabulary
    **HaplotypeResolution** (`allele_specific` / `haplotype_specific` / `phased`,
    `src/haplotype_resolution.yaml`, absent = haplotype-collapsed / not
    phase-resolved) and a `haplotype_resolution` slot on **`TrackInterpretation`**
    — homed alongside `strand`, NOT on TrackProvenance. **Content-facet
    rationale (design principle #4):** haplotype resolution answers *what the
    values represent* (allele-resolved vs. haplotype-partitioned vs.
    phase-resolved), an intrinsic property of the content, not an operation
    applied to the data — exactly like `strand`. It is therefore the second
    intrinsic-content facet after strand and belongs in interpretation. The
    vocabulary carries no `meaning:` CURIEs (no clean ontology term for the
    resolution sense), following the facet convention.
    **Decomposed 7 compound terms** (verified present in the live enums) — 5 in
    **DataType**, 2 in **FeatureType**:
    - DataType: `haplotype-specific alignments` → `alignments` +
      `haplotype_resolution:haplotype_specific` (base existed);
      `haplotype-specific contact matrix` → `contact matrix` +
      `haplotype_specific` (base existed); `allele-specific contact matrix` →
      `contact matrix` + `haplotype_resolution:allele_specific` (base existed);
      `haplotype-specific nuclease cleavage frequency` → `nuclease cleavage
      frequency` + `haplotype_specific` (base existed); `haplotype-specific
      nuclease cleavage corrected frequency` → `nuclease cleavage corrected
      frequency` + `haplotype_specific` (base **minted**).
    - FeatureType: `phased variant calls` → `variant calls` (base existed, has
      `meaning: edam:data_0918`) + `haplotype_resolution:phased`; `phased
      mapping` → `mapping` + `phased` (base **minted**).
    **Minted 2 bases (no meaning):**
    - `nuclease cleavage corrected frequency` (DataType, `in_subset:
      [chromatin_accessibility]` — verified to match its sibling `nuclease
      cleavage frequency`; description "Bias-corrected per-base nuclease cleavage
      frequency." retains the deferred `corrected` bias-correction axis baked
      in).
    - `mapping` (FeatureType, `in_subset: [haplotype]` — verified the `haplotype`
      subset exists; description "Sequence reads or contigs assigned to a
      haplotype."; the residual of `phased mapping`).
    **Deferred parental-origin axis (maternal/paternal) — WHY.** The
    parental-origin axis (which parent a haplotype came from) is a SEPARATE axis
    and is deliberately NOT a value of HaplotypeResolution. The terms `maternal
    variant calls`, `paternal variant calls`, `maternal haplotype mapping`,
    `paternal haplotype mapping` are left ATOMIC (guarded PROTECTED, confirmed
    intact) pending a future parental-origin facet; collapsing maternal/paternal
    into `haplotype_specific` would lose the parent label, so the axis is held.
    **Kept atomic — 2 terms (different axes), guarded PROTECTED, confirmed
    intact:** `diploid personal genome alignments` (DataType) — `diploid` is the
    REFERENCE PLOIDY, a property of the reference, not a resolution value;
    `allele-specific variants` (FeatureType) — here "allele-specific" denotes
    the ALLELIC-IMBALANCE behavior (a different sense of the phrase), not
    allele-resolved content, so it is NOT decomposed onto
    `haplotype_resolution:allele_specific`.
    The round-trip `compound term = output_type/feature_type +
    haplotype_resolution (+ other facets)` is preserved in
    `mappings/facet_decomposition.tsv` (a new `haplotype_resolution` column was
    inserted immediately before `base_exists`, empty-backfilled for all prior
    rows; 7 new rows appended — 5 DataType, 2 FeatureType). DataType **166 → 162**
    (−5 compound, +1 minted base); FeatureType **76 → 75** (−2 compound, +1
    minted base). PROTECTED confirmed 6/6 (1 DataType + 5 FeatureType). Applied
    via `scripts/apply_haplotype_resolution_decomposition.py` (ruamel round-trip,
    TSV read by header name). Developmental software — clean removals, no
    back-compat.
    **NOTE on count target.** The driving plan named a gate of
    `DataType=161 / total=236`, but that is arithmetically off by one: 166 − 5
    removals + 1 required mint (`nuclease cleavage corrected frequency`, whose
    base did not exist — skipping it would dangle the TSV row and fail the
    round-trip check) = **162**, not 161. The true post-operation counts are
    DataType **162** / FeatureType **75** / Total **237**, and the round-trip
    check passes against these.

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

5. **Sample and assay properties are out of scope for the content
   vocabularies.** DataType / FeatureType describe *what a file's content is*;
   properties of the biological sample or of the assay/method that produced it
   are a different axis and do not belong baked into content terms.
   - **Sample anatomy / tissue → biospecimen module / UBERON.** `forebrain`,
     `heart`, `brain` (in the `predicted <tissue> enhancers` terms) are
     biospecimen properties. They are EJECTED from the content enums and
     delegated to UBERON via `mappings/scope_delegations.tsv`, aligned to the
     future `organism_part` biospecimen slot (FAIRtracks
     `sample.sample_type.organism_part`).
   - **Sample sex → PATO (biospecimen), not the content enums.** The sex of the
     biological sample is a biospecimen property delegated to PATO. Note
     (verified upstream): FAIRtracks has NO sex field, so sample sex cannot be
     imported from the FGA-WG; it is outsourced to PATO.
   - **Assay / method names → a future axis.** Assay-fused content terms (e.g.
     `DNN-MPRA predicted signal`, `HMM predicted chromatin state`) carry a
     method/assay name that is left for a future axis, not baked into content.
   - **CRUCIAL DISTINCTION — reference-build sex is NOT sample sex.** The sex in
     the *ejected* `male/female genome reference|index` terms is a property of
     the REFERENCE ASSEMBLY (which sex chromosomes it contains), not of the
     sample. It is therefore a genuine ONGA content-adjacent axis and is handled
     by a proper, lossless FACET on the NEW `ReferenceGenome` descriptor schema
     (`build_sex` → `ReferenceBuildSex`, PATO `male`/`female`), recorded in
     `facet_decomposition.tsv` — distinct from sample sex (delegated to PATO via
     biospecimen) and from sample anatomy (delegated to UBERON via
     `scope_delegations.tsv`). One leaks the *reference*, the other leaks the
     *sample*; only the latter is a scope ejection.

6. **A facet earns its place by cross-cutting orthogonality, not by
   vocabulary size.** The test for whether an axis is worth faceting is
   whether it **slices across MANY distinct base types**: if one orthogonal
   axis recurs across `N` independent bases with `k` values each, faceting
   collapses an `N×k` cartesian explosion of compound terms into `N` bases +
   `k` facet values (`N+k`). That payoff is what justifies a facet —
   *regardless of how small the facet vocabulary is*. A 2-value axis is an
   excellent facet when it cross-cuts broadly: `FilterStatus`
   (`filtered`/`unfiltered`) has only 2 values yet spans reads, alignments,
   peaks, variants, quantifications, and count matrices, so it earns its
   slot. Conversely, an axis with a large vocabulary that is concentrated in a
   single base family does NOT earn a facet and stays atomic.

   **This SUPERSEDES the earlier vocabulary-size heuristic** ("a facet isn't
   worth it if its vocabulary is smaller than the number of terms it
   decomposes"), which was WRONG: it would have rejected `FilterStatus` and
   other strong cross-cutting binary facets. Vocabulary size is irrelevant;
   cross-cutting breadth is the criterion. (This is why the reproducibility /
   selection-mode axis in operation #13 was deferred — not because its
   vocabulary was large, but because it is concentrated in the peak/DHS
   reproducibility family and does not cross-cut.)

### Atomic by principle (deliberately un-faceted)

Axes and terms left atomic *by decision* under principle #6 (they fail the
cross-cutting test, or are an identity rather than a base carrying a
qualifier). This backlog is **closed by decision**, not open. Each term below
was verified live in `src/file_content.yaml` (enum noted per row).

| Axis / terms | Enum | Reason kept atomic |
|---|---|---|
| **Reproducibility-selection** — `conservative/optimal/representative/pseudoreplicated IDR thresholded peaks`, `replicated peaks`, `pseudoreplicated peaks`, `representative DNase hypersensitivity sites`, `consensus DNase hypersensitivity sites` | DataType | Deferred this session; only cross-cuts ~2 base families (peaks, DHS), below the payoff bar. |
| **IDR input / ranking** — `peaks and background as input for IDR`, `IDR ranked peaks`, `ranked gRNAs` | DataType | A role/input and a scoring output, not a threshold cut (ranked ≠ thresholded). |
| **Bias-correction** — `bias-corrected predicted signal profile` | DataType | Only touches the signal/bias-profile family (~1–2 bases); doesn't cross-cut; deferred for a future `bias_correction` facet. See note below. |
| **Redaction** — `redacted alignments`, `redacted transcriptome alignments` | DataType | 2 terms, single (alignment) base family; kept atomic. |
| **Smoothing** — `wavelet-smoothed signal`, `summed densities signal` (DataType); `smoothed methylation state at CpG` (FeatureType) | DataType, FeatureType | A transform, not scaling; deferred. |
| **Selected-regions wrapper** — `selected regions for predicted signal profile` + its 5 siblings (`… for bias-corrected predicted signal profile`, `… for predicted bias profile`, `… for count sequence contribution scores`, `… for predicted signal and sequence contribution scores`, `… for profile sequence contribution scores`) | DataType | A role/geometry wrapper, not an orthogonal content axis; deferred. |
| **Assay/method-fused predicted** — `DNN-MPRA predicted signal`, `HMM predicted chromatin state` | DataType | The model/assay name is part of identity, not an orthogonal facet; kept atomic (the assay-name axis is itself deferred — see principle #5). |
| **Reference ploidy** — `diploid personal genome alignments` | DataType | `diploid` qualifies the REFERENCE (its ploidy), not the haplotype resolution of the content; not a value of `HaplotypeResolution` (operation #17). Kept atomic. |
| **Parental origin + allelic-imbalance sense** — `allele-specific variants`; `maternal variant calls`, `paternal variant calls`, `maternal haplotype mapping`, `paternal haplotype mapping` | FeatureType | `allele-specific variants` is the ALLELIC-IMBALANCE behavior (a different sense of "allele-specific"), not allele-resolved content. The maternal/paternal terms carry a parental-origin axis (which parent a haplotype came from) that is SEPARATE from `HaplotypeResolution` and DEFERRED to a future parental-origin facet — collapsing them into `haplotype_specific` would lose the parent label (operation #17). |

**Bias-correction note.** After operation #14, `bias profile` is now an atomic
base, and the standalone `observed bias profile` / `predicted bias profile`
terms named in earlier planning **no longer exist** — they were decomposed onto
`bias profile` + `derivation:{observed|predicted}` (so there is also no
`observed/predicted bias profile` term to keep atomic). What remains deferred is
the compound `bias-corrected predicted signal profile`, held for a future
`bias_correction` facet.

## Current state

- **DataType:** 162 terms (53 with EDAM `meaning:`)
- **FeatureType:** 75 terms (20 with EDAM `meaning:`)
- **Categories:** 22 subsets
- **Total:** 237 terms, 73 EDAM-mapped
- **Descriptor schemas:** 5 — TrackFormat, TrackInterpretation, TrackProvenance,
  TrackGeometry, ReferenceGenome (Layer 2)

## Tooling note

An embedding-comparison tool (`embeddings/`) compares ONGA terms against EDAM,
OBI, GO, SO, CL, UBERON, and EFO to surface merge candidates (149 internal
similar pairs), coverage gaps (23 terms), and mapping suggestions. Its findings
drive the term-cleanup decisions recorded below — but the analysis itself does
not change the vocabulary; only the operations logged here do.

## Cleanup decisions

_(in progress — term cleanup operations will be appended here as we curate via
the Develop dashboard)_
