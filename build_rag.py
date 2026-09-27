

import sqlite3
import pandas as pd
import numpy as np
import faiss
import pickle
import os
from sentence_transformers import SentenceTransformer

DB_PATH = "pharmasense.db"
INDEX_PATH = "rag_index.faiss"
METADATA_PATH = "rag_metadata.pkl"

# A small, fast, fully local embedding model (no API key, runs on CPU)
MODEL_NAME = "all-MiniLM-L6-v2"

CHUNK_SIZE_WORDS = 120   # ~ roughly maps to the 300-500 token guidance for short documents
CHUNK_OVERLAP_WORDS = 20


def load_documents():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT doc_id, compound_id, trial_id, doc_type, title, author, date, full_text, tags FROM research_documents", conn)
    conn.close()
    return df


def chunk_text(text, chunk_size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    """Simple word-based chunking with overlap so context isn't cut off mid-thought."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def build_index():
    df = load_documents()
    print(f"Loaded {len(df)} research documents.")

    model = SentenceTransformer(MODEL_NAME)
    print(f"Loaded embedding model: {MODEL_NAME}")

    all_chunks = []       # text of each chunk
    all_metadata = []     # doc_id, title, doc_type, etc. per chunk, for citations

    for _, row in df.iterrows():
        chunks = chunk_text(str(row["full_text"]))
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadata.append({
                "doc_id": row["doc_id"],
                "chunk_index": i,
                "title": row["title"],
                "doc_type": row["doc_type"],
                "compound_id": row["compound_id"],
                "trial_id": row["trial_id"],
                "author": row["author"],
                "date": row["date"],
                "tags": row["tags"],
                "chunk_text": chunk,
            })

    print(f"Created {len(all_chunks)} chunks from {len(df)} documents.")

    print("Embedding all chunks (this runs locally, may take a minute)...")
    embeddings = model.encode(all_chunks, show_progress_bar=True, convert_to_numpy=True)
    embeddings = embeddings.astype("float32")

    # Normalize for cosine similarity via inner product
    faiss.normalize_L2(embeddings)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner product on normalized vectors = cosine similarity
    index.add(embeddings)

    faiss.write_index(index, INDEX_PATH)
    with open(METADATA_PATH, "wb") as f:
        pickle.dump(all_metadata, f)

    print(f"\nIndex saved to {INDEX_PATH}")
    print(f"Metadata saved to {METADATA_PATH}")
    print(f"Vector dimension: {dim}, total vectors: {index.ntotal}")


if __name__ == "__main__":
    build_index()
