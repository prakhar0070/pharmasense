"""
The vector_search_tool your agents will call.
Run build_rag.py once first to create rag_index.faiss + rag_metadata.pkl.
"""

import faiss
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer

INDEX_PATH = "rag_index.faiss"
METADATA_PATH = "rag_metadata.pkl"
MODEL_NAME = "all-MiniLM-L6-v2"

_model = None
_index = None
_metadata = None


def _load():
    global _model, _index, _metadata
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
        _index = faiss.read_index(INDEX_PATH)
        with open(METADATA_PATH, "rb") as f:
            _metadata = pickle.load(f)


def vector_search_tool(query: str, k: int = 5):
    """
    Returns the top-k most relevant chunks for a natural-language query,
    each with a citation (doc_id, title) so answers can be grounded.
    """
    _load()

    q_vec = _model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(q_vec)

    scores, indices = _index.search(q_vec, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        meta = _metadata[idx]
        results.append({
            "score": float(score),
            "doc_id": meta["doc_id"],
            "title": meta["title"],
            "doc_type": meta["doc_type"],
            "compound_id": meta["compound_id"],
            "trial_id": meta["trial_id"],
            "date": meta["date"],
            "passage": meta["chunk_text"],
        })
    return results


if __name__ == "__main__":
    # Quick manual test — try one of the example questions from the guide
    test_query = "What has our internal research said about JAK2 inhibitors and cardiotoxicity?"
    print(f"Query: {test_query}\n")
    for r in vector_search_tool(test_query, k=3):
        print(f"[{r['score']:.3f}] {r['title']}  (doc_id={r['doc_id']})")
        print(f"    {r['passage'][:150]}...")
        print()
