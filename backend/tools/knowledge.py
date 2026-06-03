import logging
from backend.rag import retriever

logger = logging.getLogger(__name__)


def search(query: str, top_k: int = 5) -> dict:
    """Search the medical knowledge base using RAG."""
    logger.info(f"search_knowledge_base: {query!r}")
    chunks = retriever.search(query, top_k=top_k)

    if not chunks:
        logger.warning("No relevant chunks found for query")
        return {
            "found": False,
            "query": query,
            "context": "",
            "message": "No relevant information found in knowledge base.",
        }

    context = retriever.format_context(chunks)
    logger.info(f"Found {len(chunks)} relevant chunks")
    return {
        "found": True,
        "query": query,
        "chunks_count": len(chunks),
        "context": context,
    }
