"""Generate comparison reports from similarity search results."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .similarity_search import (
    InternalSimilarityPair,
    SimilarityResult,
    TermSimilarityResults,
)


class ReportGenerator:
    """Generate reports from similarity search results."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_mapping_report(
        self,
        results: list[TermSimilarityResults],
        format: str = "both"
    ) -> dict[str, Path]:
        """Generate mapping report showing best matches per ONGA term.

        Args:
            results: Similarity results from find_all_similar_terms()
            format: "json", "markdown", or "both"

        Returns:
            Dict mapping format to output file path
        """
        outputs = {}

        # Build structured data
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "total_terms": len(results),
            "terms_with_matches": sum(1 for r in results if r.best_overall_match()),
            "terms": []
        }

        for term_result in results:
            term_entry = {
                "onga_term": term_result.term_name,
                "onga_category": term_result.category,
                "onga_subset": term_result.subset,
                "onga_definition": term_result.definition,
                "existing_edam_mapping": term_result.existing_mapping,
                "max_similarity": term_result.max_similarity(),
                "suggested_mappings": []
            }

            # Get best match per ontology
            for onto_name, matches in term_result.matches_by_ontology.items():
                for match in matches[:3]:  # Top 3 per ontology
                    match_type = self._classify_match(
                        match.similarity,
                        term_result.existing_mapping,
                        match.match_id
                    )
                    term_entry["suggested_mappings"].append({
                        "ontology": onto_name,
                        "term_id": match.match_id,
                        "term_name": match.match_term,
                        "similarity": round(match.similarity, 4),
                        "match_type": match_type,
                        "definition": match.match_definition[:200] if match.match_definition else ""
                    })

            # Sort suggestions by similarity
            term_entry["suggested_mappings"].sort(
                key=lambda x: x["similarity"], reverse=True
            )
            report_data["terms"].append(term_entry)

        # Sort terms by max similarity (ascending = worst matches first for review)
        report_data["terms"].sort(key=lambda x: x["max_similarity"])

        # Write JSON
        if format in ("json", "both"):
            json_path = self.output_dir / "mapping_report.json"
            with open(json_path, "w") as f:
                json.dump(report_data, f, indent=2)
            outputs["json"] = json_path

        # Write Markdown
        if format in ("markdown", "both"):
            md_path = self.output_dir / "mapping_report.md"
            self._write_mapping_markdown(report_data, md_path)
            outputs["markdown"] = md_path

        return outputs

    def _classify_match(
        self,
        similarity: float,
        existing_mapping: Optional[str],
        match_id: str
    ) -> str:
        """Classify a match as confirmed, strong, moderate, or weak."""
        # Check if this confirms an existing mapping
        if existing_mapping and match_id in existing_mapping:
            return "confirmed"
        if similarity >= 0.85:
            return "strong"
        if similarity >= 0.70:
            return "moderate"
        return "weak"

    def _write_mapping_markdown(self, data: dict, path: Path) -> None:
        """Write mapping report as Markdown."""
        lines = [
            "# ONGA Ontology Mapping Report",
            "",
            f"Generated: {data['generated_at']}",
            "",
            f"- **Total ONGA terms**: {data['total_terms']}",
            f"- **Terms with matches**: {data['terms_with_matches']}",
            "",
            "## Terms by Category",
            ""
        ]

        # Group by category and subset
        by_category: dict[str, list] = {}
        for term in data["terms"]:
            cat = term["onga_category"] or "Uncategorized"
            by_category.setdefault(cat, []).append(term)

        for category, terms in sorted(by_category.items()):
            lines.append(f"### {category}")
            lines.append("")

            # Group by subset within category
            by_subset: dict[str, list] = {}
            for term in terms:
                subset = term["onga_subset"] or "other"
                by_subset.setdefault(subset, []).append(term)

            for subset, subset_terms in sorted(by_subset.items()):
                lines.append(f"#### {subset}")
                lines.append("")
                lines.append("| Term | Max Sim | Best Match | Ontology | Type |")
                lines.append("|------|---------|------------|----------|------|")

                for term in subset_terms:
                    if term["suggested_mappings"]:
                        best = term["suggested_mappings"][0]
                        lines.append(
                            f"| {term['onga_term']} | "
                            f"{term['max_similarity']:.2f} | "
                            f"{best['term_name'][:30]} | "
                            f"{best['ontology']} | "
                            f"{best['match_type']} |"
                        )
                    else:
                        lines.append(
                            f"| {term['onga_term']} | - | No matches | - | - |"
                        )
                lines.append("")

        with open(path, "w") as f:
            f.write("\n".join(lines))

    def generate_internal_similarity_report(
        self,
        pairs: list[InternalSimilarityPair],
        format: str = "both"
    ) -> dict[str, Path]:
        """Generate report of ONGA terms similar to each other.

        Args:
            pairs: Similar term pairs from find_internal_similarity()
            format: "json", "markdown", or "both"

        Returns:
            Dict mapping format to output file path
        """
        outputs = {}

        # Build structured data
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "total_pairs": len(pairs),
            "cross_category_pairs": sum(1 for p in pairs if p.crosses_categories),
            "pairs": [
                {
                    "term1": p.term1_name,
                    "term1_category": p.term1_category,
                    "term1_subset": p.term1_subset,
                    "term2": p.term2_name,
                    "term2_category": p.term2_category,
                    "term2_subset": p.term2_subset,
                    "similarity": round(p.similarity, 4),
                    "crosses_categories": p.crosses_categories,
                    "recommendation": p.recommendation()
                }
                for p in pairs
            ]
        }

        # Write JSON
        if format in ("json", "both"):
            json_path = self.output_dir / "internal_similarity.json"
            with open(json_path, "w") as f:
                json.dump(report_data, f, indent=2)
            outputs["json"] = json_path

        # Write Markdown
        if format in ("markdown", "both"):
            md_path = self.output_dir / "internal_similarity.md"
            self._write_internal_similarity_markdown(report_data, md_path)
            outputs["markdown"] = md_path

        return outputs

    def _write_internal_similarity_markdown(self, data: dict, path: Path) -> None:
        """Write internal similarity report as Markdown."""
        lines = [
            "# ONGA Internal Similarity Report",
            "",
            f"Generated: {data['generated_at']}",
            "",
            "This report identifies ONGA terms that are semantically similar to each other,",
            "which may indicate opportunities for merging, hierarchical relationships, or",
            "terminology consolidation.",
            "",
            f"- **Total similar pairs**: {data['total_pairs']}",
            f"- **Cross-category pairs**: {data['cross_category_pairs']}",
            "",
            "## Potentially Redundant Terms",
            "",
            "| Term 1 | Term 2 | Similarity | Categories | Recommendation |",
            "|--------|--------|------------|------------|----------------|"
        ]

        for pair in data["pairs"]:
            cat_info = f"{pair['term1_category']}/{pair['term2_category']}"
            if pair["crosses_categories"]:
                cat_info = f"**{cat_info}**"
            lines.append(
                f"| {pair['term1']} | {pair['term2']} | "
                f"{pair['similarity']:.2f} | {cat_info} | "
                f"{pair['recommendation']} |"
            )

        lines.extend([
            "",
            "## Cross-Category Matches",
            "",
            "These pairs have similar terms in different categories (DataType vs FeatureType),",
            "which may indicate inconsistencies in categorization:",
            ""
        ])

        cross_cat = [p for p in data["pairs"] if p["crosses_categories"]]
        if cross_cat:
            for pair in cross_cat:
                lines.append(
                    f"- **{pair['term1']}** ({pair['term1_category']}) "
                    f"<-> **{pair['term2']}** ({pair['term2_category']}): "
                    f"{pair['similarity']:.2f}"
                )
        else:
            lines.append("*No cross-category matches found.*")

        with open(path, "w") as f:
            f.write("\n".join(lines))

    def generate_gap_analysis_report(
        self,
        gap_terms: list[TermSimilarityResults],
        all_terms: list[TermSimilarityResults],
        format: str = "both"
    ) -> dict[str, Path]:
        """Generate gap analysis report for terms without good matches.

        Args:
            gap_terms: Terms with low similarity scores
            all_terms: All terms for statistics
            format: "json", "markdown", or "both"

        Returns:
            Dict mapping format to output file path
        """
        outputs = {}

        # Group by subset
        by_subset: dict[str, list[TermSimilarityResults]] = {}
        for term in gap_terms:
            subset = term.subset or "other"
            by_subset.setdefault(subset, []).append(term)

        # Build structured data
        report_data = {
            "generated_at": datetime.now().isoformat(),
            "total_onga_terms": len(all_terms),
            "gap_terms_count": len(gap_terms),
            "gap_percentage": round(len(gap_terms) / len(all_terms) * 100, 1) if all_terms else 0,
            "by_subset": {}
        }

        for subset, terms in sorted(by_subset.items()):
            max_sims = [t.max_similarity() for t in terms]
            report_data["by_subset"][subset] = {
                "count": len(terms),
                "max_similarity_in_group": round(max(max_sims), 4) if max_sims else 0,
                "avg_similarity": round(sum(max_sims) / len(max_sims), 4) if max_sims else 0,
                "terms": [
                    {
                        "name": t.term_name,
                        "category": t.category,
                        "definition": t.definition,
                        "max_similarity": round(t.max_similarity(), 4),
                        "best_match": (
                            {
                                "term": t.best_overall_match().match_term,
                                "ontology": t.best_overall_match().match_ontology,
                                "similarity": round(t.best_overall_match().similarity, 4)
                            }
                            if t.best_overall_match() else None
                        )
                    }
                    for t in sorted(terms, key=lambda x: x.max_similarity())
                ]
            }

        # Write JSON
        if format in ("json", "both"):
            json_path = self.output_dir / "gap_analysis.json"
            with open(json_path, "w") as f:
                json.dump(report_data, f, indent=2)
            outputs["json"] = json_path

        # Write Markdown
        if format in ("markdown", "both"):
            md_path = self.output_dir / "gap_analysis.md"
            self._write_gap_analysis_markdown(report_data, md_path)
            outputs["markdown"] = md_path

        return outputs

    def _write_gap_analysis_markdown(self, data: dict, path: Path) -> None:
        """Write gap analysis report as Markdown."""
        lines = [
            "# ONGA Gap Analysis Report",
            "",
            f"Generated: {data['generated_at']}",
            "",
            "This report identifies ONGA terms that have no strong matches in any of the",
            "target ontologies. These represent concepts that may be:",
            "- Novel to ONGA (domain-specific terminology)",
            "- Poorly defined (need better descriptions)",
            "- Too specific (need generalization)",
            "",
            "## Summary",
            "",
            f"- **Total ONGA terms**: {data['total_onga_terms']}",
            f"- **Gap terms**: {data['gap_terms_count']} ({data['gap_percentage']}%)",
            "",
            "## Gap Terms by Category",
            ""
        ]

        for subset, subset_data in sorted(data["by_subset"].items()):
            lines.extend([
                f"### {subset} ({subset_data['count']} terms, max sim: {subset_data['max_similarity_in_group']:.2f})",
                ""
            ])

            for term in subset_data["terms"]:
                lines.append(f"- **{term['name']}** (max sim: {term['max_similarity']:.2f})")
                if term["definition"]:
                    lines.append(f"  - Definition: {term['definition'][:100]}...")
                if term["best_match"]:
                    best = term["best_match"]
                    lines.append(
                        f"  - Best match: {best['term']} ({best['ontology']}, {best['similarity']:.2f})"
                    )
            lines.append("")

        with open(path, "w") as f:
            f.write("\n".join(lines))

    def generate_all_reports(
        self,
        similarity_results: list[TermSimilarityResults],
        internal_pairs: list[InternalSimilarityPair],
        gap_threshold: float = 0.5
    ) -> dict[str, dict[str, Path]]:
        """Generate all three report types.

        Returns:
            Dict mapping report type to format->path dict
        """
        gap_terms = [r for r in similarity_results if r.max_similarity() < gap_threshold]

        return {
            "mapping": self.generate_mapping_report(similarity_results),
            "internal_similarity": self.generate_internal_similarity_report(internal_pairs),
            "gap_analysis": self.generate_gap_analysis_report(gap_terms, similarity_results)
        }
