#!/usr/bin/env python3
"""Run the full ONGA comparison pipeline.

Usage:
    python scripts/run_comparison.py
    python scripts/run_comparison.py --onga-path /path/to/file_content.yaml
    python scripts/run_comparison.py --threshold 0.6 --internal-threshold 0.85
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from onga_embeddings.similarity_search import SimilaritySearcher
from onga_embeddings.report_generator import ReportGenerator


# Default paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_EMBEDDING_DIR = PROJECT_ROOT / "data" / "embeddings"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "reports"
DEFAULT_ONGA_PATH = Path(__file__).resolve().parents[1] / ".." / "src" / "file_content.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ONGA ontology comparison and generate reports"
    )
    parser.add_argument(
        "--onga-path",
        type=Path,
        default=DEFAULT_ONGA_PATH,
        help=f"Path to ONGA file_content.yaml (default: {DEFAULT_ONGA_PATH})"
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
    return parser.parse_args()


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

    if args.ontologies:
        for onto in args.ontologies:
            searcher.load_ontology_embeddings(onto)
        loaded = args.ontologies
    else:
        loaded = searcher.load_all_ontologies()

    print(f"  Loaded ONGA: {len(searcher.onga_metadata)} terms")
    for onto in loaded:
        count = len(searcher._ontology_metadata[onto])
        print(f"  Loaded {onto}: {count} terms")
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
    generator = ReportGenerator(args.output_dir)

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
    run_comparison(args)


if __name__ == "__main__":
    main()
