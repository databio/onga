#!/usr/bin/env python3
"""Run the full ONGA comparison pipeline.

Two modes:

* default - embedding-only mapping / internal-similarity / gap reports. Every
  report carries a ``provenance`` block, and every finding a stable ``id`` and
  the term subject ids (SIDs) it is about, resolved through
  ``curation/term_crosswalk.json`` next to ``--subjects``.
* ``--candidates`` - a blended lexical + embedding candidate TSV for one
  ontology, for manual curation into ``mappings/<ontology>.sssom.tsv``.

Usage:
    python scripts/run_comparison.py
    python scripts/run_comparison.py --subjects ../curation/subjects.json
    python scripts/run_comparison.py --threshold 0.6 --internal-threshold 0.85
    python scripts/run_comparison.py --ontology so --candidates
    python scripts/run_comparison.py --ontology edam --candidates --top-k 10
"""

import argparse
import csv
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from onga_embeddings.provenance import (
    DEFAULT_SUBJECTS,
    SubjectRegistry,
    build_provenance,
)
from onga_embeddings.similarity_search import SimilaritySearcher
from onga_embeddings.report_generator import ReportGenerator


CANDIDATE_COLUMNS = [
    "onga_term",
    "category",
    "subset",
    "existing_mapping",
    "rank",
    "match_kind",
    "match_id",
    "match_label",
    "matched_on",
    "score",
    "match_def",
]

#: Definitions are truncated in the TSV so the file stays readable in a spreadsheet.
DEF_TRUNCATE = 300


# Default paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_EMBEDDING_DIR = PROJECT_ROOT / "data" / "embeddings"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reports"
#: The crosswalk is generated next to subjects.json.
CROSSWALK_NAME = "term_crosswalk.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ONGA ontology comparison and generate reports"
    )
    parser.add_argument(
        "--subjects",
        type=Path,
        default=DEFAULT_SUBJECTS,
        help=f"Subject registry; {CROSSWALK_NAME} is read from the same directory "
             f"(default: {DEFAULT_SUBJECTS})"
    )
    parser.add_argument(
        "--embedding-dir",
        type=Path,
        default=DEFAULT_EMBEDDING_DIR,
        help=f"Directory containing .npz embedding files (default: {DEFAULT_EMBEDDING_DIR})"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for reports (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Minimum similarity threshold for ontology matches (default: 0.5)"
    )
    parser.add_argument(
        "--internal-threshold",
        type=float,
        default=0.8,
        help="Minimum similarity threshold for internal ONGA matches (default: 0.8)"
    )
    parser.add_argument(
        "--gap-threshold",
        type=float,
        default=0.5,
        help="Max similarity below which a term is considered a gap (default: 0.5)"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of top matches to retrieve per ontology (default: 5)"
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format for reports (default: both)"
    )
    parser.add_argument(
        "--ontologies",
        nargs="+",
        help="Specific ontologies to compare against (default: all available)"
    )
    parser.add_argument(
        "--candidates",
        action="store_true",
        help="Write a blended lexical + embedding candidate TSV instead of reports"
    )
    parser.add_argument(
        "--ontology",
        default="so",
        help="Ontology to build candidates for, with --candidates (default: so)"
    )
    parser.add_argument(
        "--candidates-out",
        type=Path,
        help="Candidate TSV path (default: <output-dir>/<ontology>_candidates.tsv)"
    )
    return parser.parse_args()


def _require_embeddings(args: argparse.Namespace, *names: str) -> None:
    """Exit with a helpful message when a needed .npz is missing."""
    if not args.embedding_dir.exists():
        print(f"ERROR: Embedding directory not found: {args.embedding_dir}")
        print("Run 'python scripts/build_embeddings.py' first to generate embeddings.")
        sys.exit(1)
    for name in names:
        path = args.embedding_dir / f"{name}.npz"
        if not path.exists():
            print(f"ERROR: Embeddings not found: {path}")
            print(
                "Run 'python scripts/build_embeddings.py' first to generate embeddings."
            )
            sys.exit(1)


def run_candidates(args: argparse.Namespace) -> None:
    """Write the blended lexical + embedding candidate TSV for one ontology."""
    _require_embeddings(args, "onga", args.ontology)

    out_path = args.candidates_out or (
        args.output_dir / f"{args.ontology}_candidates.tsv"
    )

    print("=" * 60)
    print(f"ONGA candidate search against {args.ontology.upper()}")
    print("=" * 60)

    searcher = SimilaritySearcher(args.embedding_dir)
    searcher.load_onga_embeddings()
    searcher.load_ontology_embeddings(args.ontology)
    index = searcher.lexical_index(args.ontology)

    print(f"  ONGA terms: {len(searcher.onga_metadata)}")
    print(f"  {args.ontology} terms: {len(index)}")

    candidates = searcher.find_candidates(args.ontology, top_k=args.top_k)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow(CANDIDATE_COLUMNS)
        for term_candidates in candidates:
            for candidate in term_candidates:
                row = candidate.to_dict()
                row["score"] = f"{candidate.score:.3f}"
                row["match_def"] = (row["match_def"] or "")[:DEF_TRUNCATE]
                writer.writerow([row[col] for col in CANDIDATE_COLUMNS])

    names = [meta.get("name", "") for meta in searcher.onga_metadata]
    n_whole = sum(1 for name in names if index.has_whole_name_match(name))
    n_head = sum(1 for name in names if index.has_any_match(name))
    n_rows = sum(len(c) for c in candidates)

    print()
    print(f"  wrote {n_rows} rows to {out_path}")
    print(f"  ONGA terms with exact {args.ontology} label/synonym match: {n_whole}")
    print(f"  ONGA terms with any head-noun {args.ontology} match:       {n_head}")


def attach_subjects(searcher: SimilaritySearcher, registry: SubjectRegistry) -> None:
    """Resolve each embedded ONGA label to its term id and SID, in place.

    Exits when the embeddings were built from a different schema, or when any
    label does not resolve to a live term.
    """
    if searcher.schema_fingerprint != registry.schema_fingerprint:
        print("ERROR: ONGA embeddings are stale.")
        print(f"  onga.npz schema_fingerprint:     {searcher.schema_fingerprint}")
        print(f"  subjects.json schema_fingerprint: {registry.schema_fingerprint}")
        print("Run 'make embeddings-build' first.")
        sys.exit(1)
    unresolved = []
    for meta in searcher.onga_metadata:
        try:
            record = registry.resolve(meta["name"], meta["category"])
        except KeyError as err:
            unresolved.append(str(err))
            continue
        meta["term_id"] = record["term_id"]
        meta["sid"] = record["sid"]
    if unresolved:
        print(f"ERROR: {len(unresolved)} ONGA labels do not resolve to a live term:")
        for msg in unresolved:
            print(f"  {msg}")
        sys.exit(1)


def ontology_provenance(searcher: SimilaritySearcher, loaded: list[str]) -> list[dict]:
    """Per-ontology provenance; exits on a model mismatch or missing source hash."""
    entries = []
    for onto in loaded:
        entry = searcher.ontology_provenance(onto)
        if not entry["sha256"]:
            print(f"ERROR: {onto}.npz records no source file hash.")
            print(f"Run 'python scripts/build_embeddings.py --ontology {onto}' first.")
            sys.exit(1)
        model = searcher.ontology_model_name(onto)
        if model != searcher.model_name:
            print(f"ERROR: {onto}.npz was embedded with {model}, onga.npz with {searcher.model_name}.")
            sys.exit(1)
        entries.append(entry)
    return entries


def run_comparison(args: argparse.Namespace) -> None:
    """Run the full comparison pipeline."""

    # Validate paths
    if not args.embedding_dir.exists():
        print(f"ERROR: Embedding directory not found: {args.embedding_dir}")
        print("Run 'python scripts/build_embeddings.py' first to generate embeddings.")
        sys.exit(1)

    onga_embedding = args.embedding_dir / "onga.npz"
    if not onga_embedding.exists():
        print(f"ERROR: ONGA embeddings not found: {onga_embedding}")
        print("Run 'python scripts/build_embeddings.py' first to generate embeddings.")
        sys.exit(1)

    print("=" * 60)
    print("ONGA Ontology Comparison Pipeline")
    print("=" * 60)
    print(f"Embedding directory: {args.embedding_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Similarity threshold: {args.threshold}")
    print(f"Internal threshold: {args.internal_threshold}")
    print(f"Gap threshold: {args.gap_threshold}")
    print()

    # Initialize searcher and load embeddings
    print("Loading embeddings...")
    searcher = SimilaritySearcher(args.embedding_dir)
    searcher.load_onga_embeddings()
    registry = SubjectRegistry(args.subjects, args.subjects.parent / CROSSWALK_NAME)
    attach_subjects(searcher, registry)

    if args.ontologies:
        for onto in args.ontologies:
            searcher.load_ontology_embeddings(onto)
        loaded = args.ontologies
    else:
        loaded = searcher.load_all_ontologies()

    ontologies = ontology_provenance(searcher, loaded)
    print(f"  Loaded ONGA: {len(searcher.onga_metadata)} terms")
    for entry in ontologies:
        print(f"  Loaded {entry['name']}: {entry['term_count']} terms")
    print()

    # Run similarity search against all ontologies
    print("Running similarity search against ontologies...")
    similarity_results = searcher.find_all_similar_terms(
        top_k=args.top_k,
        threshold=args.threshold
    )
    terms_with_matches = sum(1 for r in similarity_results if r.best_overall_match())
    print(f"  {terms_with_matches}/{len(similarity_results)} terms have matches above threshold")
    print()

    # Find internal similarity
    print("Finding internal ONGA similarities...")
    internal_pairs = searcher.find_internal_similarity(threshold=args.internal_threshold)
    cross_cat = sum(1 for p in internal_pairs if p.crosses_categories)
    print(f"  Found {len(internal_pairs)} similar pairs ({cross_cat} cross-category)")
    print()

    # Identify gap terms
    print("Identifying gap terms...")
    gap_terms = searcher.find_gap_terms(similarity_results, args.gap_threshold)
    print(f"  Found {len(gap_terms)} terms with max similarity < {args.gap_threshold}")
    print()

    # Generate reports
    print("Generating reports...")
    provenance = build_provenance(
        model_name=searcher.model_name,
        schema_fingerprint=registry.schema_fingerprint,
        subject_count=len(searcher.onga_metadata),
        ontologies=ontologies,
        params={
            "threshold": args.threshold,
            "internal_threshold": args.internal_threshold,
            "gap_threshold": args.gap_threshold,
            "top_k": args.top_k,
            "ontologies": sorted(loaded),
        },
    )
    generator = ReportGenerator(args.output_dir, provenance)

    mapping_paths = generator.generate_mapping_report(similarity_results, args.format)
    print(f"  Mapping report: {list(mapping_paths.values())}")

    internal_paths = generator.generate_internal_similarity_report(internal_pairs, args.format)
    print(f"  Internal similarity report: {list(internal_paths.values())}")

    gap_paths = generator.generate_gap_analysis_report(gap_terms, similarity_results, args.format)
    print(f"  Gap analysis report: {list(gap_paths.values())}")

    print()
    print("=" * 60)
    print("Pipeline complete!")
    print("=" * 60)

    # Print summary statistics
    print()
    print("Summary Statistics:")
    print(f"  Total ONGA terms: {len(similarity_results)}")
    print(f"  Terms with strong matches (>0.7): {sum(1 for r in similarity_results if r.max_similarity() >= 0.7)}")
    print(f"  Terms with moderate matches (0.5-0.7): {sum(1 for r in similarity_results if 0.5 <= r.max_similarity() < 0.7)}")
    print(f"  Gap terms (<{args.gap_threshold}): {len(gap_terms)}")
    print(f"  Internal similar pairs: {len(internal_pairs)}")
    print()
    print(f"Reports written to: {args.output_dir}")


def main() -> None:
    args = parse_args()
    if args.candidates:
        run_candidates(args)
    else:
        run_comparison(args)


if __name__ == "__main__":
    main()
