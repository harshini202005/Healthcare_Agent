from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def search(query: str, top_k: int = 5, threshold: float = 0.6) -> List[Dict[str, Any]]:
    """
    Search knowledge base using vector similarity.
    Returns top_k chunks above similarity threshold.
    """
    try:
        from backend.rag.embedder import embed_one
        from backend.database import get_db

        query_embedding = embed_one(query)
        db = get_db()

        response = db.client.rpc(
            "match_knowledge_chunks",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": top_k,
            },
        ).execute()

        return response.data if response.data else []

    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        return []


def format_context(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    if not chunks:
        return ""

    parts = []
    for chunk in chunks:
        source = chunk.get("source", "unknown")
        content = chunk.get("content", "")
        similarity = chunk.get("similarity", 0)
        parts.append(f"[Source: {source} | Relevance: {similarity:.2f}]\n{content}")

    return "\n\n---\n\n".join(parts)
