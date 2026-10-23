from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="DocSearch Document Intelligence API",
    description="Evidence-first document intelligence platform backend",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "ok", "service": "docsearch-api"}


@app.get("/api/v1/health/rag")
def rag_health_check(check_live: bool = False):
    from app.services.ollama_service import ollama_service
    from app.services.document_store import doc_store

    ollama_health = ollama_service.health()
    doc_count = len(doc_store.documents)
    chunk_count = len(doc_store.chunks)

    return {
        "storage": "json_file",
        "retrieval": "active",
        "embedding": "ollama" if ollama_health.get("embed_model_available") else "unavailable",
        "vector_index": "numpy_disk",
        "llm_provider": "ollama_local",
        "ollama_running": ollama_health.get("running", False),
        "chat_model": ollama_health.get("chat_model", ""),
        "chat_model_available": ollama_health.get("chat_model_available", False),
        "embed_model": ollama_health.get("embed_model", ""),
        "embed_model_available": ollama_health.get("embed_model_available", False),
        "ollama_base_url": ollama_health.get("base_url", "http://localhost:11434"),
        "generation": "active" if ollama_health.get("chat_model_available") else "inactive",
        "model_name": ollama_health.get("chat_model", ""),
        "llm_configured": ollama_health.get("chat_model_available", False),
        "message": (
            "Ollama running with chat and embed models available"
            if ollama_health.get("running") and ollama_health.get("chat_model_available")
            else ollama_health.get("error") or "Ollama not available"
        ),
        "document_index": {"documents": doc_count, "chunks": chunk_count},
        "ollama_error": ollama_health.get("error"),
        "hint": ollama_health.get("hint") if not ollama_health.get("running") else None,
    }

@app.get("/api/v1/analytics/dashboard")
def get_dashboard_metrics(
    authorization: str = None,
    x_user_email: str = None,
    x_user_id: str = None,
):
    from app.api.endpoints.auth import get_current_user_from_request
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = (current_user["email"] if current_user else None) or x_user_email
    u_id = (current_user["id"] if current_user else None) or x_user_id

    from app.services.document_store import doc_store
    docs = doc_store.list_documents(user_email=u_email, user_id=u_id)
    total_pages = sum(d.get("pages", d.get("page_count", 0)) for d in docs)
    return {
        "documents": len(docs),
        "indexed_pages": total_pages,
        "queries_today": 0,
        "verified_percentage": 100.0
    }

from app.api.endpoints import query
from app.api.endpoints import upload
from app.api.endpoints import history
from app.api.endpoints import ai_answer
from app.api.endpoints import auth

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(query.router, prefix="/api/v1/query", tags=["Query"])
app.include_router(upload.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(history.router, prefix="/api/v1/history", tags=["History & Analytics"])
app.include_router(ai_answer.router, prefix="/api/v1/ai-answer", tags=["AI Answer (OpenAlex)"])


