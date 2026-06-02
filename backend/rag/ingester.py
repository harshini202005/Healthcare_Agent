"""
Document ingestion pipeline: chunks markdown files and stores embeddings in Supabase pgvector.
Run once (or after document updates): python -m backend.rag.ingester
"""

import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "documents"
CHUNK_SIZE = 600   # characters per chunk
OVERLAP = 80       # character overlap between chunks


def _chunk_text(text: str, source: str) -> list[dict]:
    # Split on double newlines to respect paragraph boundaries
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_SIZE:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append({"source": source, "content": current})
            # If single paragraph exceeds chunk size, split by sentences
            if len(para) > CHUNK_SIZE:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= CHUNK_SIZE:
                        current = (current + " " + sent).strip()
                    else:
                        if current:
                            chunks.append({"source": source, "content": current})
                        current = sent
            else:
                current = para

    if current:
        chunks.append({"source": source, "content": current})

    return chunks


def ingest_documents():
    from backend.rag.embedder import embed
    from backend.database import get_db

    doc_files = list(DOCS_DIR.glob("*.md"))
    if not doc_files:
        print("No documents found in", DOCS_DIR)
        return

    all_chunks = []
    for doc_file in doc_files:
        source = doc_file.stem
        text = doc_file.read_text(encoding="utf-8")
        chunks = _chunk_text(text, source)
        all_chunks.extend(chunks)
        print(f"  {doc_file.name}: {len(chunks)} chunks")

    print(f"\nEmbedding {len(all_chunks)} chunks with Mistral...")

    # Embed in batches of 16 (Mistral limit is higher but being conservative)
    texts = [c["content"] for c in all_chunks]
    all_embeddings = []
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embeddings = embed(batch)
        all_embeddings.extend(embeddings)
        print(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)}")

    db = get_db()

    # Clear existing knowledge and re-insert fresh
    print("\nClearing old knowledge chunks...")
    db.client.table("knowledge_chunks").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()

    records = [
        {
            "source": all_chunks[i]["source"],
            "content": all_chunks[i]["content"],
            "embedding": all_embeddings[i],
            "metadata": {"file": all_chunks[i]["source"]},
        }
        for i in range(len(all_chunks))
    ]

    print(f"Inserting {len(records)} chunks...")
    insert_batch = 10
    for i in range(0, len(records), insert_batch):
        batch = records[i : i + insert_batch]
        db.client.table("knowledge_chunks").insert(batch).execute()

    print(f"\n✅ Ingested {len(records)} chunks from {len(doc_files)} documents")


if __name__ == "__main__":
    ingest_documents()
