#!/usr/bin/env python3
"""
Enhance ONGA term definitions with more context and clarity.

Reads file_content.yaml, enhances definitions for key terms, writes back.
"""

from pathlib import Path
from ruamel.yaml import YAML

# Enhanced definitions for key terms
ENHANCED_DEFINITIONS = {
    # === ALIGNMENT CATEGORY ===
    "alignments": "Sequencing reads mapped to positions in a reference genome, typically in BAM/CRAM format with mapping quality scores and alignment coordinates.",
    "alignments with modifications": "Aligned reads preserving base modification information (e.g., methylation from bisulfite-seq or direct detection) encoded in BAM auxiliary fields.",
    "diploid personal genome alignments": "Reads aligned to a diploid personal genome reference including both parental haplotypes, enabling allele-specific analysis.",
    "filtered reads": "Sequencing reads passing quality control filters such as minimum quality score, adapter removal, or duplicate marking.",
    "haplotype-specific alignments": "Reads confidently assigned and aligned to a specific parental haplotype based on phased variant information.",
    "preprocessed alignments": "Alignments after preprocessing: duplicate marking, base quality score recalibration, or indel realignment.",
    "reads": "Raw or minimally processed sequencing reads in FASTQ format, including quality scores and read identifiers.",
    "redacted alignments": "Alignments with sensitive genomic positions masked or removed for privacy protection in controlled-access data sharing.",
    "rejected reads": "Reads that failed quality control filters and were excluded from downstream analysis.",
    "spike-in alignments": "Reads aligned to exogenous spike-in control sequences (e.g., ERCC) for normalization and quality assessment.",
    "transcriptome alignments": "Reads aligned to a transcriptome reference (cDNA sequences) rather than the genome.",
    "unfiltered alignments": "Raw alignments before quality filtering, duplicate removal, or other post-processing.",

    # === SIGNAL TRACK CATEGORY ===
    "signal": "Quantitative signal track showing per-base or per-bin values across the genome, typically in bigWig format.",
    "signal of all reads": "Signal computed from all aligned reads regardless of mapping quality or uniqueness.",
    "signal of unique reads": "Signal computed only from uniquely mapping reads (typically MAPQ >= 30), excluding multi-mappers.",
    "fold change over control": "Signal expressed as the ratio of experimental signal to input/control, highlighting enrichment over background.",
    "control normalized signal": "Signal normalized against a matched control experiment to remove background and technical artifacts.",
    "read-depth normalized signal": "Signal normalized by total sequencing depth to enable cross-sample comparisons.",
    "raw signal": "Unprocessed signal track before normalization or bias correction.",
    "signal p-value": "Statistical significance track showing -log10(p-value) of enrichment at each position.",
    "enrichment": "Quantitative enrichment score over background, measuring signal above expected noise level.",
    "base overlap signal": "Signal computed from base-level read overlap counts at each genomic position.",
    "wavelet-smoothed signal": "Signal smoothed using wavelet transform to reduce noise while preserving peak structure.",
    "summed densities signal": "Signal computed as the sum of per-base read densities across the region.",
    "percentage normalized signal": "Signal expressed as a percentage of total signal, useful for comparing relative enrichment.",

    # Strand-specific signals
    "minus strand signal": "Signal values computed from reads mapping to the minus (reverse/Crick) DNA strand.",
    "plus strand signal": "Signal values computed from reads mapping to the plus (forward/Watson) DNA strand.",
    "minus strand signal of all reads": "Minus strand signal from all aligned reads regardless of mapping quality.",
    "minus strand signal of unique reads": "Minus strand signal from uniquely mapping reads only (MAPQ >= threshold).",
    "plus strand signal of all reads": "Plus strand signal from all aligned reads regardless of mapping quality.",
    "plus strand signal of unique reads": "Plus strand signal from uniquely mapping reads only (MAPQ >= threshold).",

    # Predicted vs observed
    "predicted signal profile": "Signal profile computationally predicted by a model from sequence or chromatin features.",
    "observed signal profile": "Experimentally measured signal profile from sequencing data.",
    "predicted bias profile": "Computationally predicted sequencing bias profile based on sequence composition.",
    "observed bias profile": "Empirically measured sequencing bias profile from experimental data.",
    "bias-corrected predicted signal profile": "Model-predicted signal after correction for sequence-composition bias.",
    "normalized predicted signal profile": "Predicted signal profile normalized for sequencing depth or library size.",
    "normalized observed signal profile": "Observed signal profile normalized for sequencing depth or library size.",

    # === PEAK SET CATEGORY ===
    "peaks": "Discrete genomic regions of statistically significant enrichment from peak calling. The fundamental unit of ChIP-seq and ATAC-seq analysis.",
    "filtered peaks": "Peak calls after quality filtering, typically removing peaks in blacklist regions or with low signal.",
    "replicated peaks": "Peaks reproducibly called across biological or technical replicates.",
    "IDR thresholded peaks": "Peaks passing an Irreproducible Discovery Rate (IDR) threshold, indicating reproducible signal across replicates.",
    "IDR ranked peaks": "Peaks ranked by IDR score, with lower IDR indicating higher reproducibility across replicates.",
    "conservative IDR thresholded peaks": "Peaks using a conservative (stricter) IDR cutoff, yielding high-confidence but smaller peak set.",
    "optimal IDR thresholded peaks": "Peaks using the optimal IDR cutoff balancing sensitivity and reproducibility.",
    "representative IDR thresholded peaks": "A representative set of IDR-thresholded peaks selected for downstream analysis.",
    "pseudoreplicated IDR thresholded peaks": "IDR-thresholded peaks from pseudoreplicates (subsampled reads) when true replicates unavailable.",
    "pseudoreplicated peaks": "Peak calls from pseudoreplicates created by subsampling reads from a single experiment.",
    "peaks and background as input for IDR": "Combined peak and background signal data formatted as input for IDR analysis.",
    "bidirectional peaks": "Peaks from bidirectional transcription signal, characteristic of active enhancers and promoters.",
    "unidirectional peaks": "Peaks from unidirectional transcription signal, typically associated with gene bodies.",
    "divergent peaks": "Peaks from divergent transcription where initiation occurs in both directions from a central point.",
    "distal peaks": "Peaks located distal (>2-3kb) from transcription start sites, often representing enhancers.",
    "proximal peaks": "Peaks located proximal (<2-3kb) to transcription start sites, often representing promoters.",
    "valleys": "Local minima in signal tracks used in footprint detection or nucleosome positioning analysis.",

    # === CHROMATIN ACCESSIBILITY ===
    "DHS peaks": "Peak calls from DNase I hypersensitivity sequencing (DNase-seq), indicating open chromatin regions.",
    "consensus DNase hypersensitivity sites": "DNase I hypersensitivity sites consistently identified across multiple samples or cell types.",
    "representative DNase hypersensitivity sites": "A curated representative set of DNase hypersensitivity sites for reference.",
    "open chromatin regions": "Genomic regions of accessible chromatin from ATAC-seq, DNase-seq, or similar assays.",
    "footprints": "Short protected regions within open chromatin indicating transcription factor occupancy, identified as local signal minima within peaks.",
    "hotspots": "Broad regions of elevated DNase cleavage activity representing domains of chromatin accessibility.",
    "nuclease cleavage frequency": "Per-base frequency of DNase I or Tn5 transposase cleavage across the genome.",
    "FDR cut rate": "False discovery rate-controlled cut rate signal from DNase-seq analysis.",

    # === CONTACT MATRIX ===
    "contact matrix": "Genome-wide matrix of chromatin interaction frequencies from Hi-C or similar chromosome conformation capture experiments.",
    "loops": "Chromatin loop interactions (point-to-point contacts) from contact matrices, often connecting enhancers to promoters.",
    "contact domains": "Topologically associating domains (TADs) from contact matrix analysis, representing self-interacting chromatin regions.",
    "nested contact domains": "Hierarchically nested topological domains showing multi-scale chromatin organization.",
    "genome compartments": "Large-scale A (active) and B (inactive) chromatin compartments from PCA of Hi-C contact matrices.",
    "genome subcompartments": "Fine-grained chromatin compartments (A1, A2, B1, B2, B3, B4) within major A/B compartments.",
    "chromatin stripes": "Elongated features in contact matrices extending from loop anchors, indicating active loop extrusion.",
    "pairs": "Raw read pair data from Hi-C or proximity ligation before matrix construction.",
    "allele-specific contact matrix": "Chromatin contact matrix resolved to individual alleles using phased variants.",
    "haplotype-specific contact matrix": "Contact matrix computed separately for a specific parental haplotype.",

    # === DNA METHYLATION ===
    "methylation state at CpG": "DNA methylation status (methylated/unmethylated fraction) at CpG dinucleotides, the primary context for mammalian methylation.",
    "methylation state at CHG": "DNA methylation status at CHG sequence context (H = A, C, or T), common in plant genomes.",
    "methylation state at CHH": "DNA methylation status at CHH sequence context, representing asymmetric non-CpG methylation.",
    "smoothed methylation state at CpG": "CpG methylation values smoothed across neighboring sites to reduce noise.",
    "CpG sites coverage": "Sequencing read coverage at CpG positions, indicating measurement confidence.",
    "methylated reads": "Reads containing DNA methylation marks from bisulfite or direct detection methods.",

    # === RNA MODIFICATION ===
    "minus strand m6A methylation state": "N6-methyladenosine (m6A) modification on minus strand transcripts. m6A is the most abundant internal mRNA modification.",
    "plus strand m6A methylation state": "N6-methyladenosine (m6A) modification on plus strand transcripts.",
    "minus strand m5C methylation state": "5-methylcytosine (m5C) RNA modification on the minus strand.",
    "plus strand m5C methylation state": "5-methylcytosine (m5C) RNA modification on the plus strand.",
    "minus strand pseudouridine methylation state": "Pseudouridine (Ψ) modification on the minus strand. Pseudouridine is the most abundant RNA modification.",
    "plus strand pseudouridine methylation state": "Pseudouridine (Ψ) modification on the plus strand.",
    "minus strand inosine methylation state": "Inosine (A-to-I editing) modification on the minus strand.",
    "plus strand inosine methylation state": "Inosine (A-to-I editing) modification on the plus strand.",
    "minus strand Nm methylation state": "2′-O-methylation (Nm) modification on the minus strand.",
    "plus strand Nm methylation state": "2′-O-methylation (Nm) modification on the plus strand.",

    # === REGULATORY ELEMENTS ===
    "candidate Cis-Regulatory Elements": "Computationally predicted cis-regulatory elements (CREs) including enhancers, promoters, and insulators from chromatin accessibility and histone data.",
    "candidate enhancers": "Computationally predicted enhancer elements based on chromatin signatures (H3K4me1, H3K27ac, accessibility).",
    "candidate promoters": "Computationally predicted promoter elements based on chromatin signatures and TSS proximity.",
    "regulatory elements": "General annotation of regulatory elements: enhancers, promoters, silencers, and insulators.",
    "transcription start sites": "Experimentally determined transcription start sites (TSS) from CAGE, PRO-seq, or similar assays.",
    "predicted transcription start sites": "Computationally predicted TSS based on sequence or chromatin features.",
    "polyA sites": "Polyadenylation signal sites where pre-mRNA is cleaved and polyadenylated.",
    "curated binding sites": "Manually curated and validated transcription factor binding sites.",
    "enhancer prediction model": "Computational model trained to predict enhancer activity from sequence or chromatin.",
    "promoter prediction model": "Computational model trained to predict promoter activity from sequence.",
    "regulatory elements prediction model": "Computational model for predicting regulatory element activity and location.",

    # === QUANTIFICATION ===
    "gene quantifications": "Expression quantifications at gene level as read counts, TPM, or FPKM values.",
    "transcript quantifications": "Expression quantifications at transcript isoform level.",
    "exon quantifications": "Read counts or expression values quantified at individual exons.",
    "microRNA quantifications": "Expression quantifications of microRNAs (miRNAs).",
    "differential expression quantifications": "Statistical results from differential expression analysis comparing conditions.",
    "differential splicing quantifications": "Statistical results from differential splicing analysis comparing conditions.",
    "peptide quantifications": "Abundance measurements of peptides from mass spectrometry proteomics.",
    "protein expression quantifications": "Abundance measurements of proteins from proteomics data.",
    "gene stabilities": "Measurements of mRNA or gene expression stability over time.",
    "mRNA stabilities": "Measurements of mRNA half-life or decay rates.",

    # === COUNT MATRIX ===
    "sparse gene count matrix": "Sparse matrix of gene-level read counts across cells or samples, standard for single-cell RNA-seq.",
    "sparse peak count matrix": "Sparse matrix of peak accessibility counts across cells, used in single-cell ATAC-seq.",
    "sparse transcript count matrix": "Sparse matrix of transcript-level counts across cells or samples.",
    "sparse gene count matrix of all reads": "Sparse gene count matrix including all reads regardless of mapping quality.",
    "sparse gene count matrix of unique reads": "Sparse gene count matrix from uniquely mapping reads only.",
    "depth normalized signals matrix": "Matrix of read-depth normalized signals across features and samples.",
    "fold over change matrix": "Matrix of fold-change values relative to control across features.",
    "z scores matrix": "Matrix of z-score normalized values across features and samples.",
    "TF peaks matrix": "Matrix of transcription factor peak counts across samples.",

    # === DEEP LEARNING ===
    "models": "Trained computational or machine learning models saved for prediction or interpretation.",
    "bias models": "Trained models capturing sequencing bias patterns based on sequence composition.",
    "motif model": "Sequence motif model (e.g., convolutional filter weights) from deep learning or motif discovery.",
    "TF binding prediction model": "Deep learning model predicting transcription factor binding from DNA sequence.",
    "enhancer prediction model": "Model predicting enhancer activity from sequence or chromatin features.",
    "counts sequence contribution scores": "Per-nucleotide importance scores explaining sequence contribution to predicted counts (e.g., DeepLIFT, integrated gradients).",
    "profile sequence contribution scores": "Per-nucleotide importance scores explaining sequence contribution to predicted signal profiles.",
    "DNN-MPRA contribution scores": "Nucleotide contribution scores from a deep neural network trained on MPRA data.",
    "DNN-MPRA predicted signal": "Regulatory activity signal predicted by a DNN trained on MPRA data.",
    "model performance metrics": "Evaluation metrics (AUC, correlation, etc.) assessing predictive model performance.",
    "training set": "Data used to train a computational or machine learning model.",
    "training and test regions": "Genomic regions designated for model training and held-out evaluation.",

    # === VARIANT ===
    "variant calls": "Called genomic variants (SNPs, indels, structural variants) in VCF format.",
    "phased variant calls": "Variants with haplotype phase resolved, indicating which alleles co-occur on the same chromosome.",
    "eQTLs": "Expression quantitative trait loci: variants statistically associated with gene expression levels.",
    "dsQTLs": "DNase I sensitivity quantitative trait loci: variants associated with chromatin accessibility.",
    "fine-mapped variants": "Variants identified as likely causal through statistical fine-mapping within associated loci.",
    "allele-specific variants": "Variants showing allele-specific behavior in expression or chromatin accessibility.",
    "copy number variation": "Genomic regions with altered copy numbers (deletions, duplications) relative to reference.",
    "filtered SNPs": "Single nucleotide polymorphisms after quality filtering.",
    "filtered indels": "Insertion/deletion variants after quality filtering.",
    "curated SNVs": "Manually curated and validated single nucleotide variants.",

    # === REFERENCE ===
    "genome reference": "Reference genome sequence assembly used for alignment and annotation.",
    "genome index": "Precomputed index enabling rapid sequence alignment to a reference genome.",
    "transcriptome reference": "Reference transcript sequences for a species, used for RNA-seq alignment.",
    "transcriptome index": "Index for rapid alignment to transcriptome reference sequences.",
    "chromosome sizes": "File listing chromosome/contig names and lengths, required by many genomics tools.",
    "chromosomes reference": "Reference sequences for individual chromosomes.",
    "female genome reference": "Reference genome sequence derived from a female individual (includes both X chromosomes).",
    "male genome reference": "Reference genome sequence derived from a male individual (includes X and Y chromosomes).",
    "female genome index": "Alignment index built from a female reference genome.",
    "male genome index": "Alignment index built from a male reference genome.",
    "mitochondrial genome reference": "Reference sequence for the mitochondrial genome.",
    "mitochondrial genome index": "Alignment index for the mitochondrial genome.",

    # === SINGLE CELL ===
    "cell coordinates": "Low-dimensional coordinates (UMAP, t-SNE, PCA) for single-cell visualization.",
    "cell type annotations": "Cell type labels assigned to individual cells based on marker genes or reference mapping.",
    "clusters": "Cell cluster assignments from unsupervised clustering of single-cell data.",
    "archr project": "ArchR software project file with processed single-cell ATAC-seq data and analyses.",
    "cell topic participation": "Cell-level participation scores in latent topics from topic modeling.",

    # === STRUCTURE ===
    "3D structure": "Three-dimensional structural model of a genomic region or chromatin domain.",
    "contigs": "Assembled sequence contigs from genome assembly.",
    "personalized genome assembly": "Genome assembly incorporating an individual's sequence variation.",
    "predicted 3D structural ensembles": "Computationally predicted ensembles of 3D genomic structures.",

    # === HAPLOTYPE ===
    "maternal haplotype mapping": "Sequence reads or contigs assigned to the maternal haplotype.",
    "paternal haplotype mapping": "Sequence reads or contigs assigned to the paternal haplotype.",
    "phased mapping": "Sequence data with haplotype phase information resolved.",

    # === TECHNICAL ===
    "spike-ins": "Exogenous sequences of known concentration added for normalization (e.g., ERCC RNA spike-ins).",
    "sequence barcodes": "Short DNA sequences labeling samples (multiplexing) or individual cells (single-cell).",
    "sequence adapters": "Adapter sequences ligated to library fragments for sequencing platform compatibility.",
    "exclusion list regions": "Genomic blacklist regions excluded due to mapping artifacts or technical issues.",
    "mitochondrial exclusion list regions": "Mitochondrial regions excluded from nuclear genome analysis.",
    "capture targets": "Genomic regions targeted for enrichment in capture-based sequencing (exome, panels).",
    "raw data": "Unprocessed experimental data in original format before computational processing.",
    "raw imaging signal": "Unprocessed signal from imaging-based experiments.",
    "nanopore signal": "Raw ionic current signal from nanopore sequencing.",
    "fragments": "DNA or RNA fragment data prior to alignment.",
    "subreads": "Sub-read data from long-read sequencing platforms (PacBio).",
    "R2C2 subreads": "Rolling circle amplification sub-reads from R2C2 long-read sequencing.",
    "index reads": "Index read sequences for sample demultiplexing.",
    "idat green channel": "Green channel intensity data from Illumina IDAT microarray files.",
    "idat red channel": "Red channel intensity data from Illumina IDAT microarray files.",
    "intensity values": "Raw intensity measurements from microarray or imaging experiments.",
    "kmer weights": "Frequency or weight values for k-mer sequences.",
    "library fraction": "Proportion of sequencing library represented by a sample or subset.",
    "primer sequence": "Oligonucleotide primer sequences used in PCR or sequencing.",
    "negative control regions": "Genomic regions used as negative controls in experiments.",
    "positive control regions": "Genomic regions used as positive controls in experiments.",
    "inclusion list": "Allowlist of genomic regions or barcodes included in analysis.",
    "filtered regions": "Genomic regions removed from analysis after filtering.",
    "validation": "Data generated for experimental validation purposes.",

    # === SEQUENCE MOTIF ===
    "PWMs": "Position weight matrices representing sequence motif models, encoding nucleotide preferences at each position.",
    "sequence motifs": "Sequence patterns enriched in genomic regions of interest.",
    "sequence motifs instances": "Genomic locations where specific sequence motifs occur.",
    "sequence motifs report": "Summary report of motif discovery or enrichment analysis.",

    # === ANNOTATION ===
    "transcriptome annotations": "Comprehensive gene and transcript annotations for a genome.",
    "HMM predicted chromatin state": "Chromatin state annotations (e.g., ChromHMM) predicted by hidden Markov model from histone marks.",
    "splice junctions": "Splice site junctions identified from RNA-seq alignments.",
    "transcribed fragments": "Genomic regions identified as transcribed from RNA-seq data.",
    "miRNA annotations": "Annotation tracks for microRNA genes and precursors.",
    "repeat elements annotation": "Annotation of repetitive element locations and classes.",
    "restriction enzyme site locations": "Genomic positions of restriction enzyme recognition sites.",
    "sequence alignability": "Track indicating mappability of sequences to the reference genome.",
    "sequence uniqueness": "Track indicating uniqueness of k-mer sequences across the genome.",
    "functional conservation mapping": "Mapping of functionally conserved regions across species.",
    "functional conservation quantifications": "Quantification of functional conservation scores.",
}


def main():
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 100

    repo_root = Path(__file__).parent.parent
    input_path = repo_root / "src" / "file_content.yaml"

    print(f"Reading {input_path}")
    with open(input_path) as f:
        data = yaml.load(f)

    enhanced_count = 0
    if 'enums' in data and 'OutputType' in data['enums']:
        pv = data['enums']['OutputType']['permissible_values']
        for term_name in pv:
            if term_name in ENHANCED_DEFINITIONS:
                pv[term_name]['description'] = ENHANCED_DEFINITIONS[term_name]
                enhanced_count += 1

    print(f"Enhanced {enhanced_count} of {len(pv)} definitions")

    # Write back
    with open(input_path, 'w') as f:
        yaml.dump(data, f)

    print(f"Updated {input_path}")
    return 0


if __name__ == "__main__":
    exit(main())
