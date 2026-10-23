import time
import asyncio
from fastapi import APIRouter, Header, Depends
from fastapi.concurrency import run_in_threadpool
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from app.services.rag_engine import rag_engine
from app.services.search_service import search_service
from app.services.document_store import doc_store
from app.services.history_store import history_store

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    documentNames: Optional[List[str]] = None
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None


class EvidenceModel(BaseModel):
    document: str
    page: int
    text: str
    status: str
    score: Optional[float] = None


class SearchPageResult(BaseModel):
    document: str
    page: int
    match_count: int
    snippets: List[str]


class SearchResults(BaseModel):
    query: str
    mode: str
    total_pages: int
    total_matches: int
    results: List[SearchPageResult]
    related_results: Optional[List[SearchPageResult]] = []


class SourceModel(BaseModel):
    title: str
    authors: List[str] = []
    year: Optional[Any] = None
    venue: Optional[str] = ""
    doi: Optional[str] = ""
    url: Optional[str] = ""


class QueryResponse(BaseModel):
    answer: str
    status: str
    confidence: str
    evidence: List[EvidenceModel]
    citations: Optional[List[Dict[str, Any]]] = []
    sources: Optional[List[SourceModel]] = []
    search_results: Optional[SearchResults] = None
    diagnostics: Optional[Dict[str, Any]] = None


class DirectSearchRequest(BaseModel):
    query: str
    documentNames: Optional[List[str]] = None
    sort_by: Optional[str] = "page"
    user_id: Optional[str] = None
    user_email: Optional[str] = None


@router.post("/", response_model=QueryResponse)
async def ask_question(
    request: QueryRequest,
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """
    Submit any query. Records the search in history automatically tied to current user.
    Returns: AI answer + all matching pages from real indexed documents.
    Runs RAG engine in a thread pool to avoid blocking the event loop.
    """
    from app.api.endpoints.auth import get_current_user_from_request
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = request.user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = request.user_id or (current_user["id"] if current_user else None) or x_user_id

    t0 = time.time()

    # Run the blocking RAG engine in a thread pool for maximum speed
    roles = [current_user.get("role", "User")] if current_user else ["User"]
    response_data = await run_in_threadpool(
        rag_engine.generate_answer,
        request.query,
        request.documentNames,
        roles,
        u_email,
        u_id,
    )

    latency_ms = round((time.time() - t0) * 1000, 1)

    evidence = [EvidenceModel(**ev) for ev in response_data.get("evidence", [])]
    sr_raw = response_data.get("search_results")
    search_results = None
    if sr_raw:
        search_results = SearchResults(
            query=sr_raw.get("query", request.query),
            mode=sr_raw.get("mode", "none"),
            total_pages=sr_raw.get("total_pages", 0),
            total_matches=sr_raw.get("total_matches", 0),
            results=[SearchPageResult(**r) for r in sr_raw.get("results", [])],
            related_results=[SearchPageResult(**r) for r in sr_raw.get("related_results", [])]
        )

    # ── Record in user history ──
    history_store.record_search(
        query=request.query,
        document_names=request.documentNames,
        status=response_data["status"],
        result_pages=sr_raw.get("total_pages", 0) if sr_raw else 0,
        result_matches=sr_raw.get("total_matches", 0) if sr_raw else 0,
        evidence_count=len(evidence),
        confidence=response_data.get("confidence", "HIGH"),
        latency_ms=latency_ms,
        user_id=u_id,
        user_email=u_email,
    )

    if response_data["status"] == "ABSTAINED":
        history_store.add_review_flag(
            flag_type="ABSTENTION",
            priority="MEDIUM",
            title=f'No evidence found for query: "{request.query}"',
            description=(
                f'The query "{request.query}" returned no supporting evidence '
                f'from the selected document(s). The AI abstained from answering.'
            ),
            document_names=request.documentNames,
            query=request.query,
        )

    sources = [SourceModel(**s) for s in response_data.get("sources", [])]

    return QueryResponse(
        answer=response_data["answer"],
        status=response_data["status"],
        confidence=response_data["confidence"],
        evidence=evidence,
        citations=response_data.get("citations", []),
        sources=sources,
        search_results=search_results,
        diagnostics={**(response_data.get("diagnostics") or {}), "latency_ms": latency_ms}
    )


@router.post("/search", response_model=SearchResults)
async def search_documents(
    request: DirectSearchRequest,
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """
    Pure document search — all matching pages, never limited to top-K.
    Also records in user history.
    """
    from app.api.endpoints.auth import get_current_user_from_request
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = request.user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = request.user_id or (current_user["id"] if current_user else None) or x_user_id

    t0 = time.time()
    result = await run_in_threadpool(
        search_service.search_exact,
        request.query,
        request.documentNames,
        request.sort_by or "page",
        u_email,
        u_id,
    )
    latency_ms = round((time.time() - t0) * 1000, 1)

    history_store.record_search(
        query=request.query,
        document_names=request.documentNames,
        status="SUCCESS" if result["total_pages"] > 0 else "ABSTAINED",
        result_pages=result["total_pages"],
        result_matches=result["total_matches"],
        evidence_count=0,
        latency_ms=latency_ms,
        user_id=u_id,
        user_email=u_email,
    )

    return SearchResults(
        query=result["query"],
        mode=result["mode"],
        total_pages=result["total_pages"],
        total_matches=result["total_matches"],
        results=[SearchPageResult(**r) for r in result["results"]],
        related_results=[SearchPageResult(**r) for r in result.get("related_results", [])]
    )


@router.get("/documents")
def list_indexed_documents(
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """List indexed documents owned by current user."""
    from app.api.endpoints.auth import get_current_user_from_request
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = (current_user["email"] if current_user else None) or x_user_email
    u_id = (current_user["id"] if current_user else None) or x_user_id
    if not u_email and not u_id:
        return []
    return doc_store.list_documents(user_email=u_email, user_id=u_id)


@router.get("/quick-search")
def quick_search(
    q: str,
    limit: int = 6,
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """
    Ultra-fast live search suggestions for the top search bar.
    Scoped strictly to the authenticated user's documents.
    """
    from app.api.endpoints.auth import get_current_user_from_request
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = (current_user["email"] if current_user else None) or x_user_email
    u_id = (current_user["id"] if current_user else None) or x_user_id

    query_str = (q or "").strip()
    if not query_str or len(query_str) < 2:
        return {"query": query_str, "documents": [], "pages": [], "recent": history_store.get_search_history(user_email=u_email, limit=4)}

    # Document name matches for this user only
    all_docs = doc_store.list_documents(user_email=u_email, user_id=u_id)
    if not all_docs:
        return {"query": query_str, "total_matches": 0, "total_pages": 0, "documents": [], "pages": [], "mode": "exact"}

    matched_docs = [
        d for d in all_docs
        if query_str.lower() in d["filename"].lower()
    ][:3]

    # Exact page matches for this user
    user_doc_names = [d["filename"] for d in all_docs]
    search_res = search_service.search_exact(query_str, document_names=user_doc_names, user_email=u_email, user_id=u_id)
    top_pages = search_res.get("results", [])[:limit]

    return {
        "query": query_str,
        "total_matches": search_res.get("total_matches", 0),
        "total_pages": search_res.get("total_pages", 0),
        "documents": matched_docs,
        "pages": top_pages,
        "mode": search_res.get("mode", "exact")
    }

