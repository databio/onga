# ONGA Ontology Mapping Report

Generated: 2026-06-05T20:58:47.131637

- **Total ONGA terms**: 242
- **Terms with matches**: 224

## Terms by Category

### DataType

#### alignment

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| redacted alignments | 0.52 | File name extension | edam | weak |
| redacted transcriptome alignments | 0.56 | unedited_region | so | weak |
| diploid personal genome alignments | 0.58 | Genome alignment | edam | weak |
| rejected reads | 0.60 | Sequence contamination filteri | edam | weak |
| preprocessed alignments | 0.61 | trimmed sequence data | obi | weak |
| alignments with modifications | 0.63 | Bisulfite mapping | edam | weak |
| haplotype-specific alignments | 0.66 | Haplotype mapping | edam | weak |
| reads | 0.70 | proportion mapped reads | obi | weak |
| spike-in alignments | 0.72 | spike in | efo | moderate |
| alignments | 0.73 | alignment counting algorithm | obi | moderate |
| transcriptome alignments | 0.77 | alignment counting algorithm | obi | moderate |
| gene alignments | 0.79 | alignment counting algorithm | obi | moderate |

#### annotation

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| sequence uniqueness | 0.62 | K-mer countgraph | edam | weak |
| HMM predicted chromatin state | 0.65 | Hidden Markov model | edam | weak |
| read annotations | 0.65 | Annotation | edam | weak |
| semi-automated genome annotation | 0.66 | sequence annotation algorithm | obi | weak |
| sequence alignability | 0.71 | alignment counting algorithm | obi | moderate |

#### chromatin_accessibility

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| hotspots1 reference | 0.54 | mutational_hotspot | so | weak |
| hotspots2 reference | 0.54 | mutational_hotspot | so | weak |
| nuclease cleavage frequency | 0.63 | nuclease_hypersensitive_site | so | weak |
| haplotype-specific nuclease cleavage corrected frequency | 0.63 | nuclease_hypersensitive_site | so | weak |
| haplotype-specific nuclease cleavage frequency | 0.66 | nuclease_hypersensitive_site | so | weak |
| FDR cut rate | 0.66 | q-value | efo | weak |
| hotspots | 0.70 | DNase I hypersensitive sites s | obi | moderate |
| DHS regions reference | 0.73 | DNase I hypersensitive sites s | obi | moderate |
| consensus DNase hypersensitivity sites | 0.77 | DNase I hypersensitive sites s | obi | moderate |
| DHS peaks | 0.84 | scDNase-seq | efo | moderate |

#### contact_matrix

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| allele-specific contact matrix | 0.56 | chromosome conformation captur | obi | weak |
| haplotype-specific contact matrix | 0.57 | haplotype | so | weak |
| variants contact matrix | 0.58 | Distance matrix | edam | weak |
| pairs | 0.74 | multi-contact Hi-C assay | obi | moderate |
| contact matrix | 0.80 | Hi-C assay | obi | moderate |

#### count_matrix

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| TF peaks matrix | 0.55 | Peak calling | edam | weak |
| fold over change matrix | 0.55 | differential expression analys | obi | weak |
| signals matrix | 0.58 | analysis of matrices | efo | weak |
| z scores matrix | 0.59 | Z-value | edam | weak |
| sparse splice junction count matrix | 0.63 | Count matrix | edam | weak |
| sparse transcript count matrix | 0.65 | Count matrix | edam | weak |
| sparse peak count matrix | 0.69 | scATAC-seq (cell index) | efo | weak |
| sparse gene count matrix | 0.72 | RNA-seq read count analysis | edam | moderate |

#### crispr_screen

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| perturbation signal | - | No matches | - | - |
| reporter code counts | 0.56 | Perturb-Seq | efo | weak |
| guide quantifications | 0.59 | RNA-Seq quantification | edam | weak |
| safe-targeting gRNAs | 0.59 | SITE-Seq | efo | weak |
| ranked gRNAs | 0.62 | in vitro CRISPR screen assay | obi | weak |
| element barcode mapping | 0.64 | 10x feature barcode (CRISPR sc | efo | weak |
| non-targeting gRNAs | 0.65 | sgRNA | so | weak |
| sparse gRNA count matrix | 0.66 | Count matrix | edam | weak |
| guide locations | 0.67 | guide_RNA_region | so | weak |
| gRNAs | 0.78 | in vitro CRISPR screen assay | obi | moderate |

#### deep_learning

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| DNN-MPRA contribution scores | - | No matches | - | - |
| selected regions for bias-corrected predicted signal profile | - | No matches | - | - |
| selected regions for predicted bias profile | - | No matches | - | - |
| selected regions for predicted signal and sequence contribution scores | - | No matches | - | - |
| selected regions for profile sequence contribution scores | - | No matches | - | - |
| training and test regions | - | No matches | - | - |
| DNN-MPRA predicted signal | 0.51 | Gene regulatory network predic | edam | weak |
| bias models | 0.51 | Sequence signature data | edam | weak |
| selected regions for predicted signal profile | 0.52 | Exonic splicing enhancer predi | edam | weak |
| selected regions for count sequence contribution scores | 0.54 | alignment counting algorithm | obi | weak |
| model performance metrics | 0.57 | validation | obi | weak |
| motif model | 0.58 | Sequence motif discovery | edam | weak |
| profile sequence contribution scores | 0.60 | Sequence profile | edam | weak |
| counts sequence contribution scores | 0.61 | sequence data feature count ta | obi | weak |
| models | 0.68 | supervised machine learning | obi | weak |
| TF binding prediction model | 0.74 | Transcription factor binding s | edam | moderate |
| promoter prediction model | 0.76 | Promoter prediction | edam | moderate |
| training set | 0.76 | supervised machine learning | obi | moderate |

#### peak_set

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| IDR ranked peaks | - | No matches | - | - |
| unidirectional peaks | 0.53 | transcription_unit | so | weak |
| pseudoreplicated IDR thresholded peaks | 0.53 | Peak calling | edam | weak |
| optimal IDR thresholded peaks | 0.54 | peak matching | obi | weak |
| conservative IDR thresholded peaks | 0.55 | Peak calling | edam | weak |
| valleys | 0.57 | Nucleosome position prediction | edam | weak |
| pseudoreplicated peaks | 0.58 | Peak calling | edam | weak |
| representative IDR thresholded peaks | 0.58 | peak matching | obi | weak |
| divergent peaks | 0.60 | encodes_alternate_transcriptio | so | weak |
| distal peaks | 0.60 | distal_promoter_element | so | weak |
| peaks and background as input for IDR | 0.62 | background corrected data set | obi | weak |
| bidirectional peaks | 0.63 | Transcription factors and regu | edam | weak |
| proximal peaks | 0.63 | promoter_flanking_region | so | weak |
| replicated peaks | 0.67 | biological replicate | efo | weak |
| peaks | 0.70 | ChIP_seq_region | so | moderate |
| representative DNase hypersensitivity sites | 0.71 | DNase I hypersensitive sites s | obi | moderate |

#### quantification

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| genic features quantifications | - | No matches | - | - |
| merged transcription segment quantifications | 0.50 | serial analysis of gene expres | obi | weak |
| element quantifications | 0.53 | RESA | efo | weak |
| genic regions quantifications | 0.53 | miniARS-seq | efo | weak |
| gene stabilities | 0.53 | RNA stability design | obi | weak |
| transcription segment quantifications | 0.54 | serial analysis of gene expres | obi | weak |
| scaled RNA stability | 0.55 | RNA stability design | efo | weak |
| transcribed region quantifications | 0.60 | transcription_unit | so | weak |
| UV enriched segment quantifications | 0.60 | bromouride labeling and sequen | obi | weak |
| microRNA quantifications | 0.61 | microRNA profiling assay | obi | weak |
| novel peptides | 0.63 | Peptide identification | edam | weak |
| exon quantifications | 0.64 | RNA-seq read count analysis | edam | weak |
| transcript quantifications | 0.66 | transcriptome measurement | efo | weak |
| mRNA stabilities | 0.66 | mRNA stabilization | go | weak |
| gene quantifications | 0.67 | RNA-Seq quantification | edam | weak |
| modified peptide quantification | 0.69 | peptidyl-glutamine modificatio | go | weak |
| protein expression quantifications | 0.71 | Expression data | edam | moderate |
| differential splicing quantifications | 0.74 | differential expression analys | obi | moderate |
| peptide quantifications | 0.76 | label-free quantification | efo | moderate |
| differential expression quantifications | 0.89 | differential expression analys | obi | strong |

#### reference

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| phastcons score reference | - | No matches | - | - |
| chromosome sizes | 0.61 | reference_genome | so | weak |
| mitochondrial genome index | 0.61 | mitochondrial_sequence | so | weak |
| elements reference | 0.65 | reference_genome | so | weak |
| motif clusters reference | 0.66 | Sequence motif comparison | edam | weak |
| miRNA reference | 0.66 | ref_miRNA | so | weak |
| repeats reference | 0.68 | Sequence features (repeats) fo | edam | weak |
| rRNA reference | 0.68 | rRNA_primary_transcript | so | weak |
| chromosomes reference | 0.68 | reference_genome | so | weak |
| snRNA reference | 0.69 | snRNA | so | weak |
| genome index | 0.72 | reference genome-transcriptome | obi | moderate |
| mitochondrial genome reference | 0.73 | mitochondrial_sequence | so | moderate |
| tRNA reference | 0.73 | tRNA_primary_transcript | so | moderate |
| genome reference | 0.75 | reference_genome | so | moderate |
| transcriptome index | 0.77 | reference genome-transcriptome | obi | moderate |
| transcriptome reference | 0.78 | reference genome-transcriptome | obi | moderate |
| reference | 0.84 | Data reference | edam | moderate |

#### regulatory_element

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| enhancer prediction model | 0.62 | Exonic splicing enhancer predi | edam | weak |
| regulatory elements prediction model | 0.69 | Transcriptional regulatory ele | edam | weak |

#### signal_track

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| control profile | - | No matches | - | - |
| wavelet-smoothed signal | 0.51 | lowess global transformation | obi | weak |
| fold change over control | 0.52 | array control biosequence | efo | weak |
| signal profile | 0.53 | Sequence tag profile | edam | weak |
| enrichment | 0.54 | Enrichment analysis | edam | weak |
| bias-corrected predicted signal profile | 0.55 | Sequence composition plot | edam | weak |
| bias profile | 0.57 | end bias | efo | weak |
| end position signal | 0.59 | nucleotide sequence offset | efo | weak |
| base overlap signal | 0.59 | proportion mapped reads | obi | weak |
| signal | 0.59 | BCL format | obi | weak |
| summed densities signal | 0.60 | proportion mapped reads | obi | weak |
| control normalized signal | 0.63 | background correction objectiv | obi | weak |
| signal p-value | 0.66 | P-value | edam | weak |

#### single_cell

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| cell topic participation | - | No matches | - | - |
| cell coordinates | 0.53 | one dimensional cartesian spat | obi | weak |
| archr project | 0.65 | pseudo-bulk aggregation of sin | efo | weak |
| clusters | 0.71 | k-means clustering | obi | moderate |

#### technical

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| exclusion list regions | - | No matches | - | - |
| nanopore signal | - | No matches | - | - |
| negative control regions | - | No matches | - | - |
| positive control regions | - | No matches | - | - |
| inclusion list | 0.56 | barcode target locus role | obi | weak |
| filtered regions | 0.57 | Data filtering | edam | weak |
| idat red channel | 0.58 | CEL data file format | efo | weak |
| validation | 0.60 | cross validation objective | obi | weak |
| idat green channel | 0.60 | CEL data file format | efo | weak |
| raw imaging signal | 0.61 | Raw image | edam | weak |
| mitochondrial exclusion list regions | 0.61 | mitochondrial_control_region | so | weak |
| R2C2 subreads | 0.64 | cDNA read size | efo | weak |
| fragments | 0.65 | sequence trimming | obi | weak |
| capture targets | 0.67 | Capture-C | efo | weak |
| intensity values | 0.68 | Raw microarray data | edam | weak |
| kmer weights | 0.68 | k-mer counting | edam | weak |
| library fraction | 0.69 | sample barcode | efo | weak |
| subreads | 0.71 | BAsE-Seq | efo | moderate |
| raw data | 0.73 | raw matrix generation | efo | moderate |
| sequence adapters | 0.75 | SOLiD sequencing assay | obi | moderate |
| sequence barcodes | 0.76 | cell hashing | efo | moderate |
| index reads | 0.77 | sequence library data demultip | obi | moderate |
| primer sequence | 0.79 | sequencing_primer | so | moderate |
| spike-ins | 0.81 | spike in | efo | moderate |

#### variant

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| fine-mapped variants | 0.61 | Genetic mapping | edam | weak |
| variant functional prediction | 0.74 | Variant effect prediction | edam | moderate |

### FeatureType

#### annotation

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| functional conservation quantifications | 0.52 | Sequence alignment analysis (c | edam | weak |
| transposable element TF ancestral origin percent by subfamily | 0.54 | transcriptional enhancer facto | efo | weak |
| functional conservation mapping | 0.56 | characterization of functional | efo | weak |
| transposable element TF ancestral origin percent by motif | 0.60 | foreign_transposable_element | so | weak |
| repeat elements annotation | 0.60 | transposable element identific | efo | weak |
| miRNA annotations | 0.61 | Gene ID (miRBase) | edam | weak |
| transcribed fragments | 0.70 | self-transcribing active regul | obi | moderate |
| splice junctions | 0.73 | splice_site | so | moderate |
| RNA-binding protein associated mRNAs | 0.77 | RNA-binding protein immunoprec | obi | moderate |
| transcriptome annotations | 0.77 | Genome annotation | edam | moderate |
| restriction enzyme site locations | 0.80 | Restriction site recognition | edam | moderate |

#### chromatin_accessibility

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| footprints | 0.63 | accessible_DNA_region | so | weak |
| open chromatin regions | 0.76 | Sono-Seq | efo | moderate |

#### contact_matrix

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| genome subcompartments | - | No matches | - | - |
| nested contact domains | 0.53 | topologically_associated_domai | so | weak |
| genome compartments | 0.56 | X-ChIP-seq | efo | weak |
| chromatin stripes | 0.67 | chromatin loop anchoring activ | go | weak |
| loops | 0.68 | promoter-enhancer loop anchori | go | weak |
| contact domains | 0.70 | topologically_associated_domai | so | moderate |

#### dna_methylation

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| smoothed methylation state at CpG | 0.61 | unmethylated CpG binding | go | weak |
| methylation state at CHG | 0.61 | DNA residue methylation | obi | weak |
| CpG sites coverage | 0.63 | average depth of sequence cove | obi | weak |
| methylation state at CHH | 0.66 | hemi-methylated DNA-binding | go | weak |
| methylated reads | 0.74 | MeDIP-seq assay | obi | moderate |
| methylation state at CpG | 0.75 | unmethylated CpG binding | go | moderate |

#### element_gene_linkage

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| element gene interactions signal | - | No matches | - | - |
| element gene interactions p-value | 0.51 | genetic interaction identifica | obi | weak |
| links | 0.52 | chromosomal_regulatory_element | so | weak |
| topic gene weights | 0.56 | Phylogenetic character weights | edam | weak |
| element gene links | 0.61 | Transcriptional regulatory ele | edam | weak |

#### haplotype

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| paternal haplotype mapping | 0.69 | Haplotype mapping | edam | weak |
| maternal haplotype mapping | 0.70 | Haplotype mapping | edam | moderate |
| phased mapping | 0.75 | Haplotype mapping | edam | moderate |

#### regulatory_element

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| enhancers reference | 0.56 | ENCODE | efo | weak |
| candidate enhancers | 0.57 | transcription cofactor activit | obi | weak |
| enhancer validation | 0.57 | Exonic splicing enhancer predi | edam | weak |
| curated binding sites | 0.60 | Transcription factor binding s | edam | weak |
| promoters reference | 0.61 | Promoter prediction | edam | weak |
| predicted enhancers | 0.63 | Exonic splicing enhancer predi | edam | weak |
| candidate promoters | 0.68 | Promoter prediction | edam | weak |
| regulatory elements | 0.68 | Transcriptional regulatory ele | edam | weak |
| TSS reference | 0.75 | transcription_start_cluster | so | moderate |
| candidate Cis-Regulatory Elements | 0.76 | cis-regulatory element predict | edam | moderate |
| transcription start sites | 0.78 | TSS Sequencing | efo | moderate |
| polyA sites | 0.83 | polyA_site | so | moderate |

#### replication_timing

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| relative replication signal | 0.60 | replication initiator 1 measur | efo | weak |
| replication timing profile | 0.81 | DNA replication timing by sequ | obi | moderate |

#### rna_modification

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| Nm methylation state | 0.72 | Nm-seq | efo | moderate |
| inosine methylation state | 0.73 | adenosine to inosine editing | go | moderate |
| pseudouridine methylation state | 0.75 | pseudouridine synthesis | go | moderate |
| m5C methylation state | 0.78 | 5_methylcytosine | so | moderate |
| m6A methylation state | 0.79 | m6A-LAIC-seq | efo | moderate |

#### sequence_motif

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| sequence motifs | 0.64 | Sequence motif | edam | weak |
| PWMs | 0.65 | Position weight matrix | edam | weak |
| sequence motifs instances | 0.69 | Sequence sites, features and m | edam | weak |
| sequence motifs report | 0.73 | Sequence motif discovery | edam | moderate |

#### single_cell

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| cell type annotations | 0.63 | Cell type identifier | edam | weak |
| cell type data | 0.73 | inferred cell type | efo | moderate |

#### structure

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| predicted 3D structural ensembles | 0.63 | Protein super-secondary struct | edam | weak |
| 3D structure | 0.63 | 3D cell structure determinatio | obi | weak |
| personalized genome assembly | 0.70 | Genome assembly | edam | moderate |
| contigs | 0.77 | sequence assembly algorithm | obi | moderate |

#### variant

| Term | Max Sim | Best Match | Ontology | Type |
|------|---------|------------|----------|------|
| allele-specific variants | 0.52 | allelic_frequency | so | weak |
| curated SNVs | 0.55 | SNV | so | weak |
| phased variant calls | 0.60 | haplotype | so | weak |
| variant effect quantifications | 0.62 | functional_effect_variant | so | weak |
| dsQTLs | 0.64 | DNase I hypersensitive sites s | obi | weak |
| maternal variant calls | 0.68 | Variant calling | edam | weak |
| variant reference | 0.69 | variant_genome | so | weak |
| reference variants | 0.69 | reference_genome | so | weak |
| paternal variant calls | 0.70 | Variant calling | edam | moderate |
| variant calls | 0.72 | Variant calling | edam | moderate |
| SNPs | 0.76 | SNP | so | moderate |
| eQTLs | 0.77 | Gene expression QTL analysis | edam | moderate |
| copy number variation | 0.82 | copy number variation | efo | moderate |
| indels | 0.83 | delins | so | moderate |
