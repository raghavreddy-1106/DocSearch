"""
history_store.py — Persistent search and document history for DocSearch.
Saves all searches and uploads to JSON files in the data/ directory.
Thread-safe with file locking via simple in-memory lock.
"""
import json
import os
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SEARCH_HISTORY_FILE = DATA_DIR / "search_history.json"
DOCUMENT_HISTORY_FILE = DATA_DIR / "document_history.json"
REVIEW_QUEUE_FILE = DATA_DIR / "review_queue.json"

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> List[Dict[str, Any]]:
    if path.exists():
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save(path: Path, data: List[Dict[str, Any]]):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


class HistoryStore:
    """
    Stores search queries and document upload events persistently.
    Each entry is tied to a document name for per-document analytics.
    """

    # ── Search History ────────────────────────────────────────────────────────

    def record_search(
        self,
        query: str,
        document_names: Optional[List[str]],
        status: str,
        result_pages: int,
        result_matches: int,
        evidence_count: int,
        confidence: str = "HIGH",
        latency_ms: Optional[float] = None,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
    ):
        """Record a search query with its results and user ownership."""
        with _lock:
            history = _load(SEARCH_HISTORY_FILE)
            entry = {
                "id": len(history) + 1,
                "timestamp": _now(),
                "user_id": user_id,
                "user_email": user_email,
                "query": query.strip(),
                "document_names": document_names or [],
                "status": status,          # SUCCESS | ABSTAINED
                "result_pages": result_pages,
                "result_matches": result_matches,
                "evidence_count": evidence_count,
                "confidence": confidence,
                "latency_ms": latency_ms,
            }
            history.append(entry)
            _save(SEARCH_HISTORY_FILE, history)

    def get_search_history(
        self,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
        document_name: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Get recent search history, scoped to user and optionally filtered by document."""
        with _lock:
            history = _load(SEARCH_HISTORY_FILE)
        if user_email or user_id:
            history = [
                h for h in history
                if (user_email and h.get("user_email") == user_email) or
                   (user_id and h.get("user_id") == user_id)
            ]
        if document_name:
            history = [
                h for h in history
                if document_name in h.get("document_names", [])
            ]
        return list(reversed(history))[:limit]

    def get_search_stats(
        self,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
        document_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute live analytics from real search history scoped to a user."""
        with _lock:
            history = _load(SEARCH_HISTORY_FILE)

        if user_email or user_id:
            history = [
                h for h in history
                if (user_email and h.get("user_email") == user_email) or
                   (user_id and h.get("user_id") == user_id)
            ]

        if document_name:
            history = [h for h in history if document_name in h.get("document_names", [])]

        if not history:
            return {
                "total_searches": 0,
                "success_rate": 0.0,
                "abstention_rate": 0.0,
                "avg_result_pages": 0.0,
                "top_queries": [],
                "searches_per_document": {},
                "recent_queries": [],
                "zero_result_queries": [],
            }

        total = len(history)
        successful = sum(1 for h in history if h.get("status") == "SUCCESS")
        abstained = sum(1 for h in history if h.get("status") == "ABSTAINED")

        # Term frequency
        query_freq: Dict[str, int] = {}
        for h in history:
            q = h.get("query", "").strip().lower()
            if q:
                query_freq[q] = query_freq.get(q, 0) + 1

        top_queries = sorted(query_freq.items(), key=lambda x: x[1], reverse=True)[:10]

        # Per-document counts
        doc_counts: Dict[str, int] = {}
        for h in history:
            for doc in h.get("document_names", ["All documents"]):
                doc_counts[doc] = doc_counts.get(doc, 0) + 1

        # Zero-result queries
        zero_result = [
            h["query"] for h in history
            if h.get("result_pages", 0) == 0 and h.get("status") == "ABSTAINED"
        ]
        zero_result_unique = list(dict.fromkeys(zero_result))[:10]

        # Recent queries (last 20)
        recent = [h.get("query", "") for h in reversed(history)][:20]

        avg_pages = sum(h.get("result_pages", 0) for h in history) / total if total else 0

        return {
            "total_searches": total,
            "success_rate": round((successful / total) * 100, 1) if total else 0,
            "abstention_rate": round((abstained / total) * 100, 1) if total else 0,
            "avg_result_pages": round(avg_pages, 1),
            "top_queries": [{"query": q, "count": c} for q, c in top_queries],
            "searches_per_document": doc_counts,
            "recent_queries": recent,
            "zero_result_queries": zero_result_unique,
        }

    # ── Document History ──────────────────────────────────────────────────────

    def record_upload(
        self,
        filename: str,
        pages: int,
        chunks: int,
        size_bytes: int = 0,
        status: str = "indexed",
    ):
        """Record a document upload event."""
        with _lock:
            history = _load(DOCUMENT_HISTORY_FILE)
            # Update existing record if same filename
            existing = next((h for h in history if h["filename"] == filename), None)
            if existing:
                existing.update({
                    "last_uploaded": _now(),
                    "pages": pages,
                    "chunks": chunks,
                    "size_bytes": size_bytes,
                    "status": status,
                    "upload_count": existing.get("upload_count", 1) + 1,
                })
            else:
                history.append({
                    "filename": filename,
                    "first_uploaded": _now(),
                    "last_uploaded": _now(),
                    "pages": pages,
                    "chunks": chunks,
                    "size_bytes": size_bytes,
                    "status": status,
                    "upload_count": 1,
                })
            _save(DOCUMENT_HISTORY_FILE, history)

    def get_document_history(self) -> List[Dict[str, Any]]:
        with _lock:
            return list(reversed(_load(DOCUMENT_HISTORY_FILE)))

    # ── Review Queue ──────────────────────────────────────────────────────────

    def add_review_flag(
        self,
        flag_type: str,
        priority: str,
        title: str,
        description: str,
        document_names: Optional[List[str]] = None,
        query: Optional[str] = None,
    ):
        """Add a flag to the review queue (e.g. abstention, low confidence)."""
        with _lock:
            queue = _load(REVIEW_QUEUE_FILE)
            queue.append({
                "id": len(queue) + 1,
                "timestamp": _now(),
                "flag_type": flag_type,      # ABSTENTION | LOW_CONFIDENCE | PROCESSING
                "priority": priority,         # HIGH | MEDIUM | LOW
                "title": title,
                "description": description,
                "document_names": document_names or [],
                "query": query,
                "status": "pending",          # pending | resolved | dismissed
            })
            _save(REVIEW_QUEUE_FILE, queue)

    def get_review_queue(self, status: str = "pending") -> List[Dict[str, Any]]:
        with _lock:
            queue = _load(REVIEW_QUEUE_FILE)
        filtered = [q for q in queue if q.get("status") == status]
        return list(reversed(filtered))

    def update_review_item(self, item_id: int, new_status: str) -> bool:
        with _lock:
            queue = _load(REVIEW_QUEUE_FILE)
            for item in queue:
                if item.get("id") == item_id:
                    item["status"] = new_status
                    item["resolved_at"] = _now()
                    _save(REVIEW_QUEUE_FILE, queue)
                    return True
        return False

    def clear_search_history(
        self,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
        document_name: Optional[str] = None,
    ):
        with _lock:
            history = _load(SEARCH_HISTORY_FILE)
            if user_email or user_id:
                if document_name:
                    history = [
                        h for h in history
                        if not (((user_email and h.get("user_email") == user_email) or
                                 (user_id and h.get("user_id") == user_id)) and
                                (document_name in h.get("document_names", [])))
                    ]
                else:
                    history = [
                        h for h in history
                        if not ((user_email and h.get("user_email") == user_email) or
                                (user_id and h.get("user_id") == user_id))
                    ]
            else:
                if document_name:
                    history = [h for h in history if document_name not in h.get("document_names", [])]
                else:
                    history = []
            _save(SEARCH_HISTORY_FILE, history)


history_store = HistoryStore()
