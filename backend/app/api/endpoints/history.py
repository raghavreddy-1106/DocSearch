"""
history.py — API endpoints for user-isolated search history, document history,
insights analytics, review queue management, and evaluation metrics.
All history and insights are scoped to the individual user.
"""
from fastapi import APIRouter, Query, Header, HTTPException
from typing import Optional
from app.services.history_store import history_store
from app.services.document_store import doc_store
from app.api.endpoints.auth import get_current_user_from_request

router = APIRouter()


# ── Search History ─────────────────────────────────────────────────────────────

@router.get("/search")
def get_search_history(
    document: Optional[str] = Query(None, description="Filter by document name"),
    user_email: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """Return search history, newest first. Scoped to the current user."""
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = user_id or (current_user["id"] if current_user else None) or x_user_id

    return {
        "history": history_store.get_search_history(
            user_email=u_email,
            user_id=u_id,
            document_name=document,
            limit=limit
        ),
        "filtered_by": document,
        "user_email": u_email,
    }


@router.delete("/search")
def clear_search_history(
    document: Optional[str] = Query(None, description="Clear only for this document"),
    user_email: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """Clear search history for the authenticated user."""
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = user_id or (current_user["id"] if current_user else None) or x_user_id

    history_store.clear_search_history(
        user_email=u_email,
        user_id=u_id,
        document_name=document
    )
    return {"message": "Search history cleared for current user", "document": document, "user_email": u_email}


# ── Document History ───────────────────────────────────────────────────────────

@router.get("/documents")
def get_document_history():
    """Return upload history for all documents."""
    return {"history": history_store.get_document_history()}


# ── Insights (Live Analytics) ──────────────────────────────────────────────────

@router.get("/insights")
def get_insights(
    document: Optional[str] = Query(None, description="Filter insights by document"),
    user_email: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """
    Live search analytics computed from real search history for current user.
    Returns: top queries, success rate, abstention rate, per-document counts.
    """
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = user_id or (current_user["id"] if current_user else None) or x_user_id

    stats = history_store.get_search_stats(
        user_email=u_email,
        user_id=u_id,
        document_name=document
    )
    docs = doc_store.list_documents(user_email=u_email, user_id=u_id)

    return {
        "search_stats": stats,
        "documents": [
            {
                "filename": d["filename"],
                "pages": d.get("page_count", d.get("pages", 0)),
                "chunks": d.get("chunks", 0),
                "search_count": stats["searches_per_document"].get(d["filename"], 0),
            }
            for d in docs
        ],
        "filtered_by": document,
        "user_email": u_email,
    }


# ── Review Queue ───────────────────────────────────────────────────────────────

@router.get("/review-queue")
def get_review_queue(status: str = Query("pending")):
    """Return review queue items. status: pending | resolved | dismissed"""
    items = history_store.get_review_queue(status=status)
    pending_count = len(history_store.get_review_queue(status="pending"))
    resolved_count = len(history_store.get_review_queue(status="resolved"))
    return {
        "items": items,
        "status_filter": status,
        "counts": {"pending": pending_count, "resolved": resolved_count},
    }


@router.patch("/review-queue/{item_id}")
def update_review_item(item_id: int, action: str = Query(..., description="resolve | dismiss")):
    """Resolve or dismiss a review queue item."""
    valid_actions = {"resolve": "resolved", "dismiss": "dismissed"}
    if action not in valid_actions:
        raise HTTPException(400, detail="action must be 'resolve' or 'dismiss'")
    success = history_store.update_review_item(item_id, valid_actions[action])
    return {"success": success, "item_id": item_id, "new_status": valid_actions[action]}


# ── Evaluation Metrics ─────────────────────────────────────────────────────────

@router.get("/evaluation")
def get_evaluation_metrics(
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """
    Real evaluation metrics computed from user search history.
    """
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = (current_user["email"] if current_user else None) or x_user_email
    u_id = (current_user["id"] if current_user else None) or x_user_id

    stats = history_store.get_search_stats(user_email=u_email, user_id=u_id)
    history = history_store.get_search_history(user_email=u_email, user_id=u_id, limit=500)

    total = stats["total_searches"]

    if total == 0:
        return {
            "has_data": False,
            "message": "No searches recorded yet for this account. Run some searches to see real evaluation metrics.",
            "metrics": {}
        }

    # Compute true operational metrics
    successful = [h for h in history if h.get("status") == "SUCCESS"]
    abstained = [h for h in history if h.get("status") == "ABSTAINED"]

    query_success_rate = round((len(successful) / total) * 100, 1) if total else 0
    abstention_rate = round((len(abstained) / total) * 100, 1) if total else 0

    # evidence_coverage: only count searches where actual evidence chunks were retrieved (not just status==SUCCESS)
    with_evidence = sum(1 for h in history if h.get("evidence_count", 0) > 0)
    evidence_rate = round((with_evidence / total) * 100, 1) if total else 0
    zero_result_rate = round((len(abstained) / total) * 100, 1) if total else 0

    # Latency percentiles: filter out legacy offline timeouts (>60s) for active inference tracking
    raw_latencies = [h["latency_ms"] / 1000.0 for h in history if h.get("latency_ms") is not None]
    local_latencies = sorted([l for l in raw_latencies if l < 60.0]) or sorted(raw_latencies)

    avg_latency = round(sum(local_latencies) / len(local_latencies), 2) if local_latencies else 0.0
    median_latency = round(local_latencies[len(local_latencies) // 2], 2) if local_latencies else 0.0
    p95_idx = min(int(len(local_latencies) * 0.95), len(local_latencies) - 1) if local_latencies else 0
    p95_latency = round(local_latencies[p95_idx], 2) if local_latencies else 0.0

    # Average relevant unique pages returned per query (capped between 1 and 8 relevant passages)
    relevant_pages_counts = []
    for h in successful:
        p_count = h.get("result_pages", 0)
        ev_count = h.get("evidence_count", 0)
        if 0 < p_count <= 10:
            relevant_pages_counts.append(p_count)
        elif ev_count > 0:
            relevant_pages_counts.append(min(ev_count, 6))
        else:
            relevant_pages_counts.append(1)

    avg_result_pages = round(
        sum(relevant_pages_counts) / len(relevant_pages_counts), 1
    ) if relevant_pages_counts else 0.0

    doc_counts = stats["searches_per_document"]
    top_doc = max(doc_counts, key=doc_counts.get) if doc_counts else None

    return {
        "has_data": True,
        "total_searches": total,
        "metrics": {
            "query_success_rate": query_success_rate,
            "abstention_rate": abstention_rate,
            "evidence_coverage_rate": evidence_rate,
            "zero_result_rate": zero_result_rate,
            "avg_latency_seconds": avg_latency,
            "median_latency_seconds": median_latency,
            "p95_latency_seconds": p95_latency,
            "avg_result_pages": avg_result_pages,
        },
        "benchmarks": {
            "sample_size": total,
            # evaluation_coverage: 100% because ALL searches are logged (not sampled)
            "evaluation_coverage": 100.0,
            # verified_citation_rate and numeric_grounding_rate require human-reviewed
            # ground-truth comparisons — not computable from HTTP status logs alone.
            "verified_citation_rate": None,
            "numeric_grounding_rate": None,
            "note": (
                "Citation and grounding rates require human-reviewed expected-answer "
                "pairs. Run the benchmark suite to obtain these metrics."
            ),
        },
        "top_queries": stats["top_queries"][:10],
        "zero_result_queries": stats["zero_result_queries"],
        "most_searched_document": top_doc,
        "searches_per_document": doc_counts,
    }
