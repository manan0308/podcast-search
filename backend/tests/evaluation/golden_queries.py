"""
Golden Queries Evaluation Framework

Evaluates search quality using:
1. Predefined queries with expected relevant documents
2. Metrics: Precision@K, Recall@K, MRR, NDCG
3. Supports both semantic and hybrid search evaluation
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from loguru import logger


@dataclass
class GoldenQuery:
    """A test query with known relevant results."""

    query: str
    relevant_chunk_ids: list[str]  # Ground truth
    relevant_keywords: list[str] = field(default_factory=list)  # Alternative matching
    category: str = "general"  # e.g., "factual", "opinion", "speaker-specific"
    difficulty: str = "medium"  # easy, medium, hard


@dataclass
class EvaluationResult:
    """Results from evaluating a single query."""

    query: str
    precision_at_5: float
    precision_at_10: float
    recall_at_10: float
    mrr: float  # Mean Reciprocal Rank
    ndcg_at_10: float
    first_relevant_rank: Optional[int]
    retrieved_ids: list[str]
    relevant_found: list[str]


@dataclass
class EvaluationSummary:
    """Aggregate evaluation metrics."""

    total_queries: int
    mean_precision_at_5: float
    mean_precision_at_10: float
    mean_recall_at_10: float
    mean_mrr: float
    mean_ndcg: float
    queries_with_relevant: int
    per_category: dict[str, dict]


class SearchEvaluator:
    """Evaluates search quality using golden queries."""

    def __init__(self, golden_queries: list[GoldenQuery] = None):
        self.golden_queries = golden_queries or []

    def add_query(self, query: GoldenQuery):
        """Add a golden query for evaluation."""
        self.golden_queries.append(query)

    def load_from_file(self, path: Path):
        """Load golden queries from JSON file."""
        with open(path) as f:
            data = json.load(f)

        for item in data["queries"]:
            self.golden_queries.append(
                GoldenQuery(
                    query=item["query"],
                    relevant_chunk_ids=item.get("relevant_chunk_ids", []),
                    relevant_keywords=item.get("relevant_keywords", []),
                    category=item.get("category", "general"),
                    difficulty=item.get("difficulty", "medium"),
                )
            )

        logger.info(f"Loaded {len(self.golden_queries)} golden queries")

    def evaluate_results(
        self,
        query: GoldenQuery,
        retrieved_results: list[dict],
        k: int = 10,
    ) -> EvaluationResult:
        """
        Evaluate search results against golden query.

        Args:
            query: Golden query with ground truth
            retrieved_results: List of search results with chunk_id and text
            k: Cutoff for metrics
        """
        retrieved_ids = [
            str(r.get("chunk_id", r.get("id", ""))) for r in retrieved_results[:k]
        ]

        # Check relevance by ID or keyword match
        relevant_set = set(query.relevant_chunk_ids)
        relevant_found = []

        for i, result in enumerate(retrieved_results[:k]):
            result_id = str(result.get("chunk_id", result.get("id", "")))
            text = result.get("text", "").lower()

            # Match by ID
            if result_id in relevant_set:
                relevant_found.append(result_id)
                continue

            # Match by keyword presence (fallback)
            for keyword in query.relevant_keywords:
                if keyword.lower() in text:
                    relevant_found.append(f"keyword:{keyword}")
                    break

        # Calculate metrics
        relevant_found_unique = list(set(relevant_found))

        # Precision@K
        precision_5 = (
            len([r for r in relevant_found[:5]]) / 5 if len(retrieved_ids) >= 5 else 0
        )
        precision_10 = (
            len(relevant_found_unique) / min(k, len(retrieved_ids))
            if retrieved_ids
            else 0
        )

        # Recall@K
        total_relevant = len(relevant_set) or len(query.relevant_keywords)
        recall_10 = len(relevant_found_unique) / total_relevant if total_relevant else 0

        # MRR - first relevant position
        first_relevant_rank = None
        for i, result in enumerate(retrieved_results[:k], 1):
            result_id = str(result.get("chunk_id", result.get("id", "")))
            text = result.get("text", "").lower()

            is_relevant = result_id in relevant_set
            if not is_relevant:
                for keyword in query.relevant_keywords:
                    if keyword.lower() in text:
                        is_relevant = True
                        break

            if is_relevant:
                first_relevant_rank = i
                break

        mrr = 1.0 / first_relevant_rank if first_relevant_rank else 0.0

        # NDCG@K (simplified - binary relevance)
        dcg = 0.0
        idcg = 0.0

        for i in range(k):
            if i < len(retrieved_results):
                result = retrieved_results[i]
                result_id = str(result.get("chunk_id", result.get("id", "")))
                text = result.get("text", "").lower()

                is_relevant = result_id in relevant_set
                if not is_relevant:
                    for keyword in query.relevant_keywords:
                        if keyword.lower() in text:
                            is_relevant = True
                            break

                if is_relevant:
                    dcg += 1.0 / (i + 2)  # log2(i+2) simplified

            # Ideal DCG (all relevant at top)
            if i < total_relevant:
                idcg += 1.0 / (i + 2)

        ndcg = dcg / idcg if idcg > 0 else 0.0

        return EvaluationResult(
            query=query.query,
            precision_at_5=precision_5,
            precision_at_10=precision_10,
            recall_at_10=recall_10,
            mrr=mrr,
            ndcg_at_10=ndcg,
            first_relevant_rank=first_relevant_rank,
            retrieved_ids=retrieved_ids,
            relevant_found=relevant_found_unique,
        )

    def summarize(self, results: list[EvaluationResult]) -> EvaluationSummary:
        """Aggregate results across all queries."""
        if not results:
            return EvaluationSummary(
                total_queries=0,
                mean_precision_at_5=0,
                mean_precision_at_10=0,
                mean_recall_at_10=0,
                mean_mrr=0,
                mean_ndcg=0,
                queries_with_relevant=0,
                per_category={},
            )

        # Group by category
        by_category: dict[str, list[EvaluationResult]] = {}
        for r in results:
            cat = "general"  # Default category
            for q in self.golden_queries:
                if q.query == r.query:
                    cat = q.category
                    break
            by_category.setdefault(cat, []).append(r)

        def avg(values):
            return sum(values) / len(values) if values else 0

        per_category = {}
        for cat, cat_results in by_category.items():
            per_category[cat] = {
                "count": len(cat_results),
                "precision_at_10": avg([r.precision_at_10 for r in cat_results]),
                "mrr": avg([r.mrr for r in cat_results]),
            }

        return EvaluationSummary(
            total_queries=len(results),
            mean_precision_at_5=avg([r.precision_at_5 for r in results]),
            mean_precision_at_10=avg([r.precision_at_10 for r in results]),
            mean_recall_at_10=avg([r.recall_at_10 for r in results]),
            mean_mrr=avg([r.mrr for r in results]),
            mean_ndcg=avg([r.ndcg_at_10 for r in results]),
            queries_with_relevant=sum(1 for r in results if r.relevant_found),
            per_category=per_category,
        )

    def print_report(self, summary: EvaluationSummary):
        """Print evaluation report."""
        print("\n" + "=" * 60)
        print("SEARCH QUALITY EVALUATION REPORT")
        print("=" * 60)
        print(f"Total Queries: {summary.total_queries}")
        print(f"Queries with Relevant Results: {summary.queries_with_relevant}")
        print()
        print("AGGREGATE METRICS:")
        print(f"  Precision@5:  {summary.mean_precision_at_5:.3f}")
        print(f"  Precision@10: {summary.mean_precision_at_10:.3f}")
        print(f"  Recall@10:    {summary.mean_recall_at_10:.3f}")
        print(f"  MRR:          {summary.mean_mrr:.3f}")
        print(f"  NDCG@10:      {summary.mean_ndcg:.3f}")
        print()
        print("BY CATEGORY:")
        for cat, metrics in summary.per_category.items():
            print(
                f"  {cat}: {metrics['count']} queries, P@10={metrics['precision_at_10']:.3f}, MRR={metrics['mrr']:.3f}"
            )
        print("=" * 60)


# Sample golden queries for podcast search
SAMPLE_GOLDEN_QUERIES = [
    GoldenQuery(
        query="What does Nikhil Kamath think about investing?",
        relevant_chunk_ids=[],  # Fill with actual IDs after indexing
        relevant_keywords=["investing", "investment", "money", "wealth", "portfolio"],
        category="opinion",
        difficulty="easy",
    ),
    GoldenQuery(
        query="compound interest wealth building",
        relevant_chunk_ids=[],
        relevant_keywords=["compound", "interest", "wealth", "building", "grow"],
        category="factual",
        difficulty="medium",
    ),
    GoldenQuery(
        query="stock market advice for beginners",
        relevant_chunk_ids=[],
        relevant_keywords=["stock", "market", "beginner", "start", "advice"],
        category="factual",
        difficulty="medium",
    ),
]


async def run_evaluation_example():
    """Example of running evaluation against live search."""
    # This would integrate with actual search service
    print("To run evaluation:")
    print("1. Index some podcasts first")
    print("2. Create golden_queries.json with relevant chunk IDs")
    print("3. Run: python -m tests.evaluation.golden_queries")

    evaluator = SearchEvaluator(SAMPLE_GOLDEN_QUERIES)

    # Mock results for demo
    mock_results = [
        {
            "chunk_id": "test-1",
            "text": "Investing is about compound interest and patience",
        },
        {"chunk_id": "test-2", "text": "The stock market rewards long term thinking"},
    ]

    result = evaluator.evaluate_results(
        SAMPLE_GOLDEN_QUERIES[0],
        mock_results,
    )

    print(f"\nExample evaluation for: '{result.query}'")
    print(f"  Precision@10: {result.precision_at_10:.3f}")
    print(f"  MRR: {result.mrr:.3f}")
    print(f"  Relevant found: {result.relevant_found}")


if __name__ == "__main__":
    asyncio.run(run_evaluation_example())
