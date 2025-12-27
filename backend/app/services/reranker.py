"""Re-ranking service using cross-encoder."""
from typing import Optional
from loguru import logger

try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    logger.warning("sentence-transformers not installed, re-ranking disabled")


class RerankerService:
    """
    Re-rank search results using a cross-encoder model.

    Cross-encoders are more accurate than bi-encoders for relevance
    scoring but slower, so we use them to re-rank top candidates.
    """

    # Model options (from fastest to most accurate):
    # - cross-encoder/ms-marco-MiniLM-L-2-v2 (fastest, decent)
    # - cross-encoder/ms-marco-MiniLM-L-6-v2 (balanced)
    # - cross-encoder/ms-marco-MiniLM-L-12-v2 (slower, better)
    # - BAAI/bge-reranker-base (good quality)
    # - BAAI/bge-reranker-large (best quality, slowest)

    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self, model_name: str = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model: Optional[CrossEncoder] = None
        self._model_loaded = False

    def _load_model(self):
        """Lazy load the model."""
        if not CROSS_ENCODER_AVAILABLE:
            return

        if not self._model_loaded:
            logger.info(f"Loading cross-encoder model: {self.model_name}")
            self._model = CrossEncoder(self.model_name)
            self._model_loaded = True
            logger.info("Cross-encoder model loaded")

    async def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """
        Re-rank results using cross-encoder.

        Args:
            query: Search query
            results: List of search results with 'text' field
            top_k: Number of results to return

        Returns:
            Re-ranked results sorted by relevance
        """
        if not results:
            return []

        if not CROSS_ENCODER_AVAILABLE or len(results) <= 1:
            return results[:top_k]

        self._load_model()

        if not self._model:
            return results[:top_k]

        try:
            # Create query-document pairs
            pairs = [(query, r.get("text", "")) for r in results]

            # Get relevance scores
            scores = self._model.predict(pairs)

            # Combine results with scores
            scored_results = list(zip(results, scores))

            # Sort by cross-encoder score (descending)
            scored_results.sort(key=lambda x: x[1], reverse=True)

            # Update scores and return top-k
            reranked = []
            for result, ce_score in scored_results[:top_k]:
                result = result.copy()
                result["rerank_score"] = float(ce_score)
                result["original_score"] = result.get("score", 0)
                result["score"] = float(ce_score)  # Use rerank score as primary
                reranked.append(result)

            logger.debug(f"Re-ranked {len(results)} results to {len(reranked)}")
            return reranked

        except Exception as e:
            logger.error(f"Re-ranking failed: {e}")
            return results[:top_k]

    async def score_pair(self, query: str, document: str) -> float:
        """Score a single query-document pair."""
        if not CROSS_ENCODER_AVAILABLE:
            return 0.0

        self._load_model()

        if not self._model:
            return 0.0

        try:
            score = self._model.predict([(query, document)])[0]
            return float(score)
        except Exception as e:
            logger.error(f"Scoring failed: {e}")
            return 0.0

    async def batch_score(
        self,
        query: str,
        documents: list[str],
    ) -> list[float]:
        """Score multiple documents against a query."""
        if not CROSS_ENCODER_AVAILABLE or not documents:
            return [0.0] * len(documents)

        self._load_model()

        if not self._model:
            return [0.0] * len(documents)

        try:
            pairs = [(query, doc) for doc in documents]
            scores = self._model.predict(pairs)
            return [float(s) for s in scores]
        except Exception as e:
            logger.error(f"Batch scoring failed: {e}")
            return [0.0] * len(documents)
