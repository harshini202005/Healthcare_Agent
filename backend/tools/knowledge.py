from backend.rag import retriever


def search(query: str, top_k: int = 5) -> dict:
    """
    Search the medical knowledge base using RAG.
    Returns relevant context chunks for the given query.
    """
    print(f"\n🔧 TOOL CALLED: search_knowledge_base")
    print(f"   Query: {query}")

    chunks = retriever.search(query, top_k=top_k)

    if not chunks:
        print("   ⚠️  No relevant chunks found")
        return {
            "found": False,
            "query": query,
            "context": "",
            "message": "No relevant information found in knowledge base.",
        }

    context = retriever.format_context(chunks)
    print(f"   ✅ Found {len(chunks)} relevant chunks")

    return {
        "found": True,
        "query": query,
        "chunks_count": len(chunks),
        "context": context,
    }
