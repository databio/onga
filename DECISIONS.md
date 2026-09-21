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

18. **Separated ONGA set-denoting terms from SO element types — minted
    `onga:has_element_type`.** ONGA `DataType` / `FeatureType` terms name a **SET**
    of genomic elements (a file, a track, a set of rows); a Sequence Ontology
    class names an **individual element type**. The newly added SO mapping layer
    asserted the opposite, and it corrupted the generated OWL. **Two bugs, one
    root cause (confusing "maps to" with "is"):** (a) **SO IRI hijack** — 15
    permissible values carried `meaning: SO:*`, and `meaning:` makes the value's
    IRI *be* that CURIE, so `gen-owl` relabelled, redefined and re-parented live
    SO classes (`SO:0001747 rdfs:subClassOf onga:FeatureType`, plus a vacuous
    self-referential `skos:exactMatch`) and put raw SO IRIs inside the
    `owl:unionOf` list defining `onga:FeatureType`; anyone importing
    `onga.owl.ttl` alongside SO got SO mutated. (b) **24 permissible values
    silently deleted** — 48 values carried a `meaning:` but only 24 distinct
    CURIEs were used, so `meaning:`-as-identity collapsed each colliding group
    into one OWL node: `edam:data_0928` (9 values), `edam:data_0918` (9),
    `edam:data_3002` (6), `edam:data_3917` (3), `edam:data_1353` (2).
    **Removed all 48 `meaning:` keys** (15 SO + 33 EDAM); the 28 EDAM CURIEs not
    already recorded elsewhere were MOVED into `exact_mappings` (identity was
    what `meaning:` asserted), so no EDAM cross-reference was lost — ONGA↔EDAM is
    a legitimate set-to-set relation and stays in
    `exact_mappings`/`close_mappings`/`broad_mappings`, just never in `meaning:`.
    Also moved the 2 `meaning: so:*` keys in `src/strand_orientation.yaml`
    (`plus`/`minus`) to `exact_mappings` — the same hijack, in a facet vocabulary.
    **Minted `onga:has_element_type`**: *relates an ONGA content term, which
    denotes a SET of genomic elements, to the Sequence Ontology class that its
    individual members instantiate.* Homed as the `element_type` slot on
    **`TrackInterpretation`** (range `uriorcurie`, multivalued) — a CONTENT facet
    under design principle #4, deliberately separate from `feature_type`, which
    names the ONGA **set** term.
    **Predicate policy in `mappings/so.sssom.tsv`** (81 rows before → **84**
    after, the growth being `regulatory elements` expanding from 1 ancestor row
    to 4 element rows): **74** `onga:has_element_type` membership rows, **8**
    `skos:relatedMatch` rows (members are *not* instances), **2** whitelisted
    set-to-set `skos:exactMatch`/`closeMatch` rows. `skos:exactMatch` /
    `closeMatch` / `broadMatch` against SO are **banned**, with exactly two
    exceptions where the SO class is itself set-denoting: `SO:0001505
    reference_genome` and `SO:0001506 variant_genome`, both defined as "A
    collection of sequences". `build_so_sssom.py` fails the build on any other
    SKOS match, and `check_roundtrip.py` re-checks it. The exact/close/broad
    grade moved to the declared SSSOM extension column **`element_type_fit`**
    (`exact` | `approximate` | `broad` | `not_applicable`) — a curation grade, not
    a different relation; the 81 existing rows converted mechanically
    (`exactMatch→exact`, `closeMatch→approximate`, `broadMatch→broad`), so no
    curation judgment was re-opened.
    **Annotations on permissible values:** `element_type` (pipe-joined SO CURIEs,
    a STRING — a YAML list stringifies as `"['SO:0000165', 'SO:0000167']"` in
    `gen-owl` output) and `element_type_fit`. **87** values annotated: **71**
    carry an `element_type` (24 DataType + 47 FeatureType), **16** carry
    `not_applicable` (curated-none, distinct from not-yet-curated).
    **DataType admissibility rule.** A DataType term may carry
    `onga:has_element_type` only if the file's rows are typed objects that
    instantiate an SO class. DataType names *how* data was produced; most
    DataTypes (signal, quantifications, matrices, models) have rows that are
    *values*, not features. Triage of the 27 DataType rows: **Group A** —
    18 sequence-object sets (reads, subreads, barcodes, primers, gRNAs, the
    reference sequence sets) kept as membership; **Group B** — 6 located-region
    sets with biological names (`peaks`, `DHS peaks`, `consensus`/`representative
    DNase hypersensitivity sites`, `DHS regions reference`, `hotspots`) kept as
    membership **and flagged**: that a clean SO element type holds is a
    DIAGNOSTIC that the term is FeatureType-shaped (see "Cleanup decisions" —
    deliberately deferred, not an oversight); **Group C** — `nuclease cleavage
    frequency` demoted (rows are per-base numbers, not nuclease-sensitive sites);
    **Group D** — `sequence adapters` has no SO element type at all (SO has no
    adapter term; new-term request SO-REQ-010 filed). `genome reference` sits in
    Group A but takes the set-to-set exception. `peaks` was **re-graded** from
    `skos:relatedMatch` to membership at `approximate` fit: peak rows *are*
    experimental result regions, and the original objection (that `SO:0001697
    ChIP_seq_region` is assay-bound) was a different point.
    **Mixed sets.** `regulatory elements`, whose definition enumerates
    "enhancers, promoters, silencers, and insulators", now carries four SO
    classes (`SO:0000165`, `SO:0000167`, `SO:0000625`, `SO:0000627`) instead of
    one `closeMatch` to the `SO:0005836 regulatory_region` ancestor; the OWL
    emits `owl:allValuesFrom [ owl:unionOf (...) ]`. Precedent for the "not one
    kind" shape: `TrackGeometry.DataTypes` already ships a `multiple` value, and
    `TrackGeometry.has_edges` already models the pair/edge row shape that
    `element gene links` and `links` have.
    **OWL.** `make gen-owl` now runs `gen-owl-core` + `gen-owl-so`; the latter is
    `scripts/gen_so_axioms.py`, which reads the SSSOM file and emits
    `project/owl/onga-so-element-types.owl.ttl` as
    `onga:X rdfs:subClassOf [ owl:onProperty onga:has_element_type ;
    owl:allValuesFrom SO:Y ]`, asserting an honest, importable statement and
    **never emitting a triple whose subject is an SO IRI** (enforced by an
    assertion in the generator). SO IRIs appearing as subjects in the core OWL:
    **17 → 0**. The `owl:unionOf` lists now hold **162** and **75** distinct ONGA
    IRIs with no `SO_` or `edam:` members — the 24 collapsed values are back.
    Applied via `scripts/build_so_sssom.py` (4 curated tables, validated against
    `so.obo`) and `scripts/apply_element_type.py` (ruamel round-trip, importing
    those tables so the TSV and the schema cannot drift). `make test` gained
    checks 6–10 as the regression guard. **No term was added, removed, renamed or
    re-homed:** DataType **162**, FeatureType **75**, total **237**, unchanged.
    Developmental software — clean removals, no back-compat.


19. **Merged the FGA-WG schemas into ONGA as Layers 3 and 4.** Brought the
    record and investigation classes of the FGA-WG schema
    (`~/…/intervals/repos/fga-qg`, branch `sveinugu-link-ml-schema`) into ONGA
    as full, first-class classes under the `onga` id and prefix, making ONGA
    the whole schema — vocabularies, descriptors, records, and investigation
    context — rather than just an ontology. The fga-qg repo was not touched;
    it remains the WG's artifact and ONGA becomes the reference
    implementation. **Disposition: 19 adopt / 2 merge / 1 supersede** over the
    22-item fga-qg inventory:
    - **Adopted (19 new `src/*.yaml` modules):** term, util, checksum,
      access_url, access_method, input_source, quality_assessment, file,
      genomic_annotation_file (Layer 3); experiment, analysis, study, sample,
      donor, contact, deposit, document, file_collection, top_level (Layer 4).
    - **Merged (2):** TrackGeometry (ONGA's copy was already canonical —
      verified body-identical); GenomeAssembly folded into the existing
      `ReferenceGenome` descriptor (seqcol digest slots, accessions, aliases;
      the fga `aliases: range curie` bug fixed to string; the GenomeAssembly
      class name disappears; ONGA's placeholder free-string `assembly` slot
      deleted).
    - **Superseded (1):** fga's `OutputType` enum (~270 flat ENCODE values) —
      DataType (162) + FeatureType (75) + the 8 facet vocabularies replace it,
      with `mappings/facet_decomposition.tsv` as the enforced lossless
      crosswalk; `File.data_content` deleted accordingly (content lives in
      `track_interpretation`). The generated `schema_summary.tsv` is an
      artifact, not a definition — not migrated.
    **Layer architecture:** Layer 3 (Record — a record about ONE file:
    GenomicAnnotationFile, File, and File's DRS-shaped components; the layer a
    repository adopts; external alignment GA4GH DRS/refget/PROV-O) and Layer 4
    (Investigation — the research/publishing context: Experiment through
    TopLevel; external alignment ENA/SRA, BioStudies, BioSamples,
    Phenopackets, DCAT, DataCite, schema.org). Verified against the actual
    import graph: the split required zero restructuring.
    **GenomicAnnotationFile** keeps `is_a: File`; slot `genome_assembly` →
    **`reference_genome`** (range ReferenceGenome, inlined, REQUIRED — the one
    non-negotiable: a coordinate-system-less annotation is not a genomic
    annotation); `track_geometry` demoted to optional+recommended; gains
    optional+recommended `track_format` / `track_interpretation` /
    `track_provenance` — the class now composes all five descriptors.
    `sequence_features` (open Term list) dropped: superseded by the closed
    FeatureType vocabulary via `track_interpretation.feature_type` +
    `element_type`.
    **Renames (no aliases — developmental software):** enum `DataTypes` →
    **`ValueType`** (track_geometry); enum `AccessMethods` →
    **`AccessProtocol`** + slot `access_method` → **`access_protocol`** (kills
    the one-letter class/enum near-clashes, and adopts the fga annotation
    branch's range bug fix); slot `sex` → **`donor_sex`** (firewalled in its
    description from `ReferenceGenome.build_sex` per principle #5).
    **Dropped:** `data_content`, `sequence_features`, `assembly`, and the
    `^.{1,60}$` patterns on `*_label` slots (UI hints masquerading as validity
    conditions; Contact's email pattern kept). The `biospecimen.yaml` stub
    (empty planned enums) deleted — **Sample/Donor realize it** via
    ontology-delegated Term slots (UBERON/CL/CLO/PATO), exactly the principle
    #5 posture; `organism_tissue` is the `organism_part` landing slot
    anticipated by `mappings/scope_delegations.tsv`.
    **Required-slot policy** (from the BEDbase adoption finding that heavy
    `required:` makes a schema unadoptable): `required: true` survives ONLY on
    identifier slots and on slots without which the instance is meaningless
    (`Checksum.checksum_type`, `AccessURL.url`,
    `InputSource.qualified_relation`, `GenomicAnnotationFile.reference_genome`,
    `TopLevel.document`, and the key/value pair of AssessmentValue and
    OntologyVersions' three slots); everything else fga required is demoted to
    `recommended: true` (or plain optional for administrative fields).
    Conditional rules are KEPT (Sample's classification rules, InputSource's
    XOR, TrackGeometry's rules) — conditional requirement is targeted and
    cheap.
    **Annotation pattern (lineage as annotation, not delegation):** every
    ported class carries `source: https://w3id.org/fga-wg/schema/<original>`;
    classes copied from an external standard additionally carry
    `conforms_to` + `see_also` + `close_mappings`/`exact_mappings`, reusing
    the fga `add-external-standard-annotations` branch content verbatim where
    it existed (AccessMethod/AccessURL/Checksum/File → DRS 1.4.0; the refget
    block on ReferenceGenome) and extending the same pattern to InputSource
    (PROV-O), Analysis (prov:Activity), Study/Contact (schema.org),
    Document/FileCollection (DCAT), Deposit (DataCite), Donor (Phenopackets),
    Sample (BioSamples), Experiment (ENA/ISA). No `meaning:` keys came in
    (verified), and `scripts/check_roundtrip.py` now bans `meaning:` across
    ALL of `src/` (whitelisting only the grandfathered format.yaml /
    reference_build_sex.yaml single-use facet CURIEs).
    **Validation:** `make test` unchanged invariants (DataType=162
    FeatureType=75 total=237; Set/element OK) plus new `test-examples`:
    `examples/encff323lcs_deposit.yaml` (a full TopLevel deposit
    reconstructing ENCFF323LCS — H3K9me3 ChIP-seq replicated peaks, bigBed,
    GRCh38 — from fga-qg's own per-file examples, doubling as the executable
    fga→ONGA migration demonstration), `examples/genomic_annotation_standalone.yaml`
    (the Layer-3-only adoption path), and an expected-failure counterexample
    missing `reference_genome`. `make gen-owl` / `gen-jsonld` exit 0; SO IRIs
    as subjects in core OWL: still 0. Lint: adopted fga's
    `src/linkml_lint_config.yaml` (recommended minus standard_naming);
    `make validate` is clean.
    **Site:** a generic, LinkML-driven schema browser (`/schema`,
    `/schema/class/<Name>`, `/schema/enum/<Name>`; built by
    `buildSchemaBrowser()` in `site/scripts/build-data.js`, approach ported
    from nsheff's schema-registry-site `import_linkml.py`) now owns Layers 2–4
    plus the structural enums — adding a class to `src/` produces a page with
    zero new hand-written Astro. The hand-curated Layer-1 vocabulary pages
    STAY (they are curation surfaces and the product of operations #1–#18);
    rule going forward: vocabularies are hand-curated pages, classes are
    generated pages. The renamed small enums get generic pages, not
    hand-written ones.
    **Registry:** ONGA now serves the GA4GH Schema Registry API shape
    statically under `site/public/api/` (`scripts/gen_registry.py`, `make
    gen-registry`): service-info, namespaces (single namespace `databio`),
    `schemas/databio/onga/versions/<v>/` with the full `gen-json-schema`
    bundle + per-class components, and `versions/latest/` as a full copy.
    Compliance (suite in `repos/schema-registry/compliance`, run via `make
    test-registry` against a locally served tree): **22/25 — all required
    checks pass**; the 3 failures are recommended-level and inherent to a
    static tree (CORS headers are the host's job, no /openapi endpoint,
    query-parameter filtering impossible statically). **Version policy:**
    `version:` in `src/onga.yaml` is the single source of truth; the current
    version is regenerated in place on every build (mutable current) and
    `latest/` mirrors it; cutting a version is a DECISIONS-logged bump that
    leaves the superseded directory as committed static history and flips its
    row to `superseded`; once a version has been shared externally, any change
    to its generated JSON Schema requires a bump — until then 0.1.0 absorbs
    everything, this merge included.
    **Note for Nathan (no action taken):** the 4 issues previously filed on
    the FGA-WG repo argue for shrink-and-reference; this merge went the other
    way (full classes with lineage annotations). Consider reframing them as
    "annotate lineage instead of restructuring," or withdrawing them.

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

7. **ONGA denotes sets; SO denotes elements.** An ONGA `DataType` or
   `FeatureType` term names a **set** of genomic elements — a file, a track, a
   set of rows. A Sequence Ontology class names an **individual element type**.
   These are different kinds of thing, and ONGA never asserts identity,
   equivalence, or hierarchy between them. When every member of an ONGA set
   instantiates one SO class, ONGA records that with `onga:has_element_type` — a
   membership relation, not a mapping. When members are of several kinds,
   `element_type` carries several SO classes. When the rows are not features at
   all (values, matrices, models, edges), there is no element type and
   `element_type_fit` is `not_applicable`. ONGA is a **user** of SO: SO supplies
   the element vocabulary, ONGA supplies the set vocabulary and the descriptor
   schemas around it. The one exception is an SO class that is itself
   set-denoting (`SO:0001505 reference_genome`, `SO:0001506 variant_genome`),
   where a plain SKOS match is correct.

   This is a **different boundary from principle #5**. Principle #5 ejects axes
   that are not ONGA's subject matter at all (sample anatomy → UBERON).
   Principle #7 is a *level* distinction within ONGA's own subject matter: ONGA
   and SO describe the same biology at different granularities, and the
   connection between them is membership.

   Practical corollary: **never use `meaning:` for a cross-reference.**
   `meaning:` sets the permissible value's IRI, so an SO CURIE there hijacks the
   SO class and a repeated EDAM CURIE collapses distinct ONGA terms into a single
   OWL node. Cross-references belong in
   `exact_mappings`/`close_mappings`/`broad_mappings` (set-to-set, e.g. EDAM), in
   `related_mappings` (non-membership, SO), or in the `element_type` annotation
   (membership, SO).

8. **Layer dependency discipline.** Imports and inlined class ranges point only
   downward or sideways — Layer 4 (Investigation) → Layer 3 (Record) → Layer 2
   (Descriptor) → Layer 1 (Vocabulary). A lower layer refers *up* only by
   CURIE / uriorcurie value, never by class range (e.g. `File` points at its
   containing FileCollection via the curie slot `filecollection_refs`, not a
   FileCollection range). This keeps every adoption boundary real: a repository
   can speak Layers 1–3 and ignore Layer 4 entirely, and the vocabularies stay
   usable stand-alone. Established with operation #19 (the FGA-WG merge), where
   it held over the incoming import graph with zero restructuring.


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

- **DataType:** 162 terms (58 EDAM-mapped, 26 with an `element_type` annotation)
- **FeatureType:** 75 terms (29 EDAM-mapped, 61 with an `element_type` annotation)
- **Categories:** 22 subsets
- **Total:** 237 terms, 87 EDAM-mapped, 87 element-type-annotated (71 with an SO
  class, 16 `not_applicable`)
- **`meaning:` keys in the content enums:** 0 (banned — principle #7)
- **SO element-type rows:** 74 (`onga:has_element_type`, in `mappings/so.sssom.tsv`)
- **SO relatedMatch rows:** 8 (members are *not* instances)
- **SO set-to-set rows:** 2 (whitelisted: `SO:0001505`, `SO:0001506`)
- **Descriptor schemas:** 5 — TrackFormat, TrackInterpretation, TrackProvenance,
  TrackGeometry, ReferenceGenome (Layer 2)
- **Record classes (Layer 3):** GenomicAnnotationFile, File, Checksum,
  AccessMethod, AccessURL, InputSource, QualityAssessment/AssessmentValue, and
  the helpers Term and Any (+ the AccessProtocol enum in Layer 1)
- **Investigation classes (Layer 4):** Experiment, Study, Analysis, Sample,
  Donor, Contact, Deposit, Document/OntologyVersions, FileCollection, TopLevel
  (+ the BiospecimenClassification enum in Layer 1)
- **Registry API:** GA4GH Schema Registry static tree under `site/public/api/`
  (`databio/onga`, current version from `src/onga.yaml` `version:`);
  compliance 22/25, all required checks passing

## Tooling note

An embedding-comparison tool (`embeddings/`) compares ONGA terms against EDAM,
OBI, GO, SO, CL, UBERON, and EFO to surface merge candidates (149 internal
similar pairs), coverage gaps (23 terms), and mapping suggestions. Its findings
drive the term-cleanup decisions recorded below — but the analysis itself does
not change the vocabulary; only the operations logged here do.

## Cleanup decisions

_(in progress — term cleanup operations will be appended here as we curate via
the Develop dashboard)_

- **Group B re-homing candidates (open, deferred from operation #18).** Six
  **DataType** terms carry a clean SO element type: `peaks`, `DHS peaks`,
  `consensus DNase hypersensitivity sites`, `representative DNase
  hypersensitivity sites`, `DHS regions reference`, `hotspots`. Under the
  DataType admissibility rule that is legitimate — their rows really are located
  regions — but *that it holds at all* is a diagnostic: a DataType names **how**
  data was produced, and a term whose rows have a biological element type is
  **FeatureType-shaped**. They were deliberately **not** re-homed in operation
  #18, which moved cross-references only and changed no term's enum. A future
  operation should decide whether they belong in FeatureType. **This is a
  deferred decision, not an oversight** — do not treat it as one.
- **`meaning:` in the non-content vocabularies (open).** `src/format.yaml` (9
  `edam:format_*`) and `src/reference_build_sex.yaml` (2 `PATO:*`) still use
  `meaning:`. These are facet values, not set-denoting content terms, and each
  CURIE is used exactly once, so neither the level-shift objection nor the
  collapse bug applies. They are left alone; the SO ones in
  `src/strand_orientation.yaml` were moved to `exact_mappings` in operation #18
  because those *did* hijack live SO classes in the generated OWL.
