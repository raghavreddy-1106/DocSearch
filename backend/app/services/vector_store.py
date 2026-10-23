"""
Vector Store — Local Semantic Embedding Index
----------------------------------------------
Stores document chunk embeddings on disk using numpy arrays.
Supports cosine similarity search scoped by user and document.

Storage layout:
  data/vectors/
    {user_email_hash}/
      {doc_name_hash}.npz   → embeddings + metadata

No external vector database required. Pure numpy, fast for < 100k chunks.
"""
import os
import re
import json
import math
import hashlib
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

VECTOR_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "vectors"


def _user_dir(user_email: str) -> Path:
    h = hashlib.md5((user_email or "anon").lower().encode()).hexdigest()[:12]
    d = VECTOR_DIR / h
    d.mkdir(parents=True, exist_ok=True)
    return d


def _doc_key(filename: str) -> str:
    return re.sub(r"[^\w\-.]", "_", filename)


def cosine_similarity(a: List[float], b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between vector a and each row of matrix b."""
    a_arr = np.array(a, dtype=np.float32)
    a_norm = np.linalg.norm(a_arr)
    if a_norm == 0:
        return np.zeros(len(b))
    b_norms = np.linalg.norm(b, axis=1)
    b_norms[b_norms == 0] = 1e-10
    return np.dot(b, a_arr) / (b_norms * a_norm)


class VectorStore:
    """
    Disk-backed per-user vector index.
    Each document's embeddings are stored in a separate .npz file.
    """

    def _index_path(self, user_email: str, filename: str) -> Path:
        d = _user_dir(user_email)
        return d / f"{_doc_key(filename)}.npz"

    def _meta_path(self, user_email: str, filename: str) -> Path:
        d = _user_dir(user_email)
        return d / f"{_doc_key(filename)}.meta.json"

    def save_document_embeddings(
        self,
        user_email: str,
        filename: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[Optional[List[float]]],
    ):
        """
        Save embeddings + metadata for a document's chunks.
        Only saves chunks that have valid embeddings.
        """
        valid_embeddings = []
        valid_meta = []

        for chunk, emb in zip(chunks, embeddings):
            if emb is not None and len(emb) > 0:
                valid_embeddings.append(emb)
                valid_meta.append({
                    "filename": chunk.get("filename", filename),
                    "page_number": chunk.get("page_number", 1),
                    "text": chunk.get("text", "")[:3000],  # Store full chunk text for retrieval
                    "chunk_id": chunk.get("chunk_id", ""),
                })

        if not valid_embeddings:
            print(f"[VectorStore] No valid embeddings to save for {filename}")
            return

        emb_matrix = np.array(valid_embeddings, dtype=np.float32)
        idx_path = self._index_path(user_email, filename)
        np.savez_compressed(str(idx_path), embeddings=emb_matrix)

        meta_path = self._meta_path(user_email, filename)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(valid_meta, f)

        print(f"[VectorStore] Saved {len(valid_embeddings)} embeddings for '{filename}' (user: {user_email})")

    def load_document_embeddings(
        self, user_email: str, filename: str
    ) -> Tuple[Optional[np.ndarray], Optional[List[Dict]]]:
        """Load embeddings matrix and metadata for a document."""
        idx_path = self._index_path(user_email, filename)
        meta_path = self._meta_path(user_email, filename)

        if not idx_path.exists() or not meta_path.exists():
            return None, None

        try:
            data = np.load(str(idx_path))
            emb_matrix = data["embeddings"]
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return emb_matrix, meta
        except Exception as e:
            print(f"[VectorStore] Load error for {filename}: {e}")
            return None, None

    def is_indexed(self, user_email: str, filename: str) -> bool:
        """Check whether a document has stored embeddings."""
        return (
            self._index_path(user_email, filename).exists()
            and self._meta_path(user_email, filename).exists()
        )

    def delete_document(self, user_email: str, filename: str):
        """Remove embeddings for a deleted document."""
        for path in [self._index_path(user_email, filename), self._meta_path(user_email, filename)]:
            if path.exists():
                path.unlink()
                print(f"[VectorStore] Deleted {path.name}")

    def semantic_search(
        self,
        query_embedding: List[float],
        user_email: str,
        document_names: Optional[List[str]] = None,
        top_k: int = 8,
        min_score: float = 0.20,
    ) -> List[Dict[str, Any]]:
        """
        Semantic similarity search across indexed documents.
        Returns top-k results with cosine similarity scores.
        """
        all_results = []

        user_dir = _user_dir(user_email)
        if not user_dir.exists():
            return []

        # Discover indexed documents
        for meta_file in user_dir.glob("*.meta.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue

            if not meta:
                continue

            # Filter by requested documents
            doc_filename = meta[0].get("filename", "") if meta else ""
            if document_names and doc_filename not in document_names:
                continue

            # Load embeddings
            stem = meta_file.name[:-10] if meta_file.name.endswith(".meta.json") else meta_file.stem
            emb_file = meta_file.parent / f"{stem}.npz"
            if not emb_file.exists():
                continue

            try:
                data = np.load(str(emb_file))
                emb_matrix = data["embeddings"]
            except Exception as e:
                print(f"[VectorStore] Load error {emb_file}: {e}")
                continue

            if len(emb_matrix) != len(meta):
                # Truncate to shorter length
                min_len = min(len(emb_matrix), len(meta))
                emb_matrix = emb_matrix[:min_len]
                meta = meta[:min_len]

            # Compute cosine similarities
            scores = cosine_similarity(query_embedding, emb_matrix)

            for i, (score, chunk_meta) in enumerate(zip(scores, meta)):
                if float(score) >= min_score:
                    all_results.append({
                        "document": chunk_meta.get("filename", ""),
                        "page": chunk_meta.get("page_number", 1),
                        "text": chunk_meta.get("text", ""),
                        "score": float(score),
                        "retrieval_type": "semantic",
                    })

        # Sort by score descending
        all_results.sort(key=lambda x: x["score"], reverse=True)

        # Deduplicate per (document, page) — keep highest-scoring chunk per page
        seen_pages: Dict[tuple, bool] = {}
        deduped_results = []
        for r in all_results:
            key = (r["document"], r["page"])
            if key not in seen_pages:
                seen_pages[key] = True
                deduped_results.append(r)

        return deduped_results[:top_k]


vector_store = VectorStore()
