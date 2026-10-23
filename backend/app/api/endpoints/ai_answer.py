"""
Ollama-powered AI Answer endpoint
-----------------------------------
Replaces cloud-provider AI answers with a local Ollama RAG pipeline.
Exposes:
  GET  /api/v1/ai-answer/models          → list available local models
  POST /api/v1/ai-answer/models/switch   → switch active model
  POST /api/v1/ai-answer/                → generate grounded answer from PDF
  GET  /api/v1/ai-answer/health          → Ollama connection status
  POST /api/v1/ai-answer/index           → trigger (re)indexing of a document
"""
import os
import re
from pathlib import Path
from fastapi import APIRouter, Header
from pydantic import BaseModel
from typing import List, Optional, Any
from dotenv import load_dotenv
from app.services.ollama_service import ollama_service, get_ollama_config
from app.services.hybrid_rag import hybrid_rag

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"

router = APIRouter()


def _load_env():
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────

class AIAnswerRequest(BaseModel):
    query: str
    model: Optional[str] = None
    max_results: Optional[int] = 5
    document_names: Optional[List[str]] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None


class SourceModel(BaseModel):
    title: str
    authors: List[str] = []
    year: Optional[Any] = None
    venue: Optional[str] = ""
    doi: Optional[str] = ""
    url: Optional[str] = ""


class AIAnswerResponse(BaseModel):
    answer: str
    sources: List[SourceModel]
    status: str
    model_used: str
    query: str
    error: Optional[str] = None
    hint: Optional[str] = None


class ModelSwitchRequest(BaseModel):
    model_id: str


class IndexRequest(BaseModel):
    filename: str
    user_email: Optional[str] = None
    user_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health")
def ollama_health():
    """Return Ollama connection status and model availability."""
    health = ollama_service.health()
    cfg = get_ollama_config()
    return {
        "ollama_running": health["running"],
        "base_url": cfg["base_url"],
        "chat_model": cfg["chat_model"],
        "embed_model": cfg["embed_model"],
        "chat_model_available": health.get("chat_model_available", False),
        "embed_model_available": health.get("embed_model_available", False),
        "available_models": health.get("models", []),
        "error": health.get("error"),
        "hint": health.get("hint"),
        "setup_commands": [
            "ollama serve",
            f"ollama pull {cfg['chat_model']}",
            f"ollama pull {cfg['embed_model']}",
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# Models list (for model switcher UI)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/models")
def list_models():
    """Return models list for the model switcher UI."""
    _load_env()
    health = ollama_service.health()
    cfg = get_ollama_config()

    current_model = cfg["chat_model"]
    available_local = health.get("models", [])

    # Build model list: configured model + any others found in Ollama
    models = []
    seen = set()

    def add_model(model_id: str, name: str = None, description: str = None):
        if model_id in seen:
            return
        seen.add(model_id)
        is_available = any(
            m == model_id or m.startswith(model_id.split(":")[0])
            for m in available_local
        )
        models.append({
            "id": model_id,
            "name": name or model_id,
            "provider": "Ollama (Local)",
            "description": description or f"Local model via Ollama · {'Ready' if is_available else 'Pull required: ollama pull ' + model_id}",
            "icon": "🦙",
            "group": "ollama",
            "available": is_available,
        })

    # Always include the configured model
    add_model(
        current_model,
        name=current_model.replace(":", " ").title(),
        description=f"Configured chat model · Local Ollama inference · {'Ready ✓' if health.get('chat_model_available') else 'Run: ollama pull ' + current_model}"
    )

    # Add other discovered local models
    for m in available_local:
        if m not in seen:
            add_model(m)

    # Suggest common models if none are available
    if not available_local:
        for m, name, desc in [
            ("qwen2.5:3b", "Qwen 2.5 3B", "Recommended for 8GB RAM · Fast & accurate"),
            ("qwen2.5:7b", "Qwen 2.5 7B", "Best quality · Requires 8GB+ RAM"),
            ("llama3.2:3b", "Llama 3.2 3B", "Meta's compact model · Good for document Q&A"),
            ("phi3.5:mini", "Phi 3.5 Mini", "Microsoft compact model · Very fast"),
        ]:
            if m not in seen:
                add_model(m, name, desc)

    return {
        "current_model": current_model,
        "embed_model": cfg["embed_model"],
        "models": models,
        "ollama_running": health["running"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Switch model
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/models/switch")
def switch_model(req: ModelSwitchRequest):
    """Persist model selection to .env."""
    model_id = req.model_id.strip()
    if not model_id:
        return {"success": False, "error": "Empty model ID"}

    if ENV_PATH.exists():
        content = ENV_PATH.read_text(encoding="utf-8")
        if re.search(r"^OLLAMA_CHAT_MODEL=.*$", content, re.MULTILINE):
            content = re.sub(
                r"^OLLAMA_CHAT_MODEL=.*$",
                f"OLLAMA_CHAT_MODEL={model_id}",
                content, flags=re.MULTILINE
            )
        else:
            content += f"\nOLLAMA_CHAT_MODEL={model_id}\n"
        ENV_PATH.write_text(content, encoding="utf-8")

    _load_env()
    return {
        "success": True,
        "model_id": model_id,
        "message": f"Switched to {model_id}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# On-demand (re)indexing trigger
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/index")
def index_document(
    req: IndexRequest,
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """Trigger embedding generation for a document (if not already done)."""
    from app.api.endpoints.auth import get_current_user_from_request
    from app.services.document_store import doc_store
    from app.services.vector_store import vector_store
    from app.api.endpoints.upload import UPLOAD_DIR, extract_pages_from_file

    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = req.user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = req.user_id or (current_user["id"] if current_user else None) or x_user_id

    if not u_email:
        return {"success": False, "error": "Authentication required"}

    filename = req.filename
    if vector_store.is_indexed(u_email, filename):
        return {"success": True, "message": f"'{filename}' is already indexed.", "chunks_embedded": 0}

    # Get chunks from doc store
    chunks = [
        c for c in doc_store.chunks
        if c.get("filename") == filename
        and (c.get("user_email") or "").lower() == u_email.lower()
    ]

    if not chunks:
        return {"success": False, "error": f"No chunks found for '{filename}'. Upload the document first."}

    # Check Ollama
    health = ollama_service.health()
    if not health["running"]:
        return {"success": False, "error": "Ollama is not running", "hint": "Run: ollama serve"}
    if not health.get("embed_model_available"):
        cfg = get_ollama_config()
        return {"success": False, "error": f"Embedding model not available", "hint": f"Run: ollama pull {cfg['embed_model']}"}

    # Generate embeddings
    texts = [c.get("text", "") for c in chunks]
    embeddings = ollama_service.embed_batch(texts)

    vector_store.save_document_embeddings(
        user_email=u_email,
        filename=filename,
        chunks=chunks,
        embeddings=embeddings,
    )

    embedded_count = sum(1 for e in embeddings if e is not None)
    return {
        "success": True,
        "message": f"Indexed {embedded_count}/{len(chunks)} chunks for '{filename}'",
        "chunks_embedded": embedded_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main AI Answer endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/", response_model=AIAnswerResponse)
def get_ai_answer(
    req: AIAnswerRequest,
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """
    Generate a grounded answer from uploaded PDFs using Ollama.
    Uses hybrid RAG (semantic + keyword) retrieval, then Ollama generation.
    """
    from app.api.endpoints.auth import get_current_user_from_request
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = req.user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = req.user_id or (current_user["id"] if current_user else None) or x_user_id

    if not u_email:
        return AIAnswerResponse(
            answer="Authentication required. Please log in.",
            sources=[],
            status="AUTH_ERROR",
            model_used="none",
            query=req.query,
        )

    # Run hybrid RAG pipeline
    result = hybrid_rag.generate(
        query=req.query,
        user_email=u_email,
        document_names=req.document_names,
        user_id=u_id,
        model=req.model,
    )

    # Build sources from citations
    sources = []
    for cite in result.get("citations", []):
        sources.append(SourceModel(
            title=f"{cite.get('document', 'Document')} — Page {cite.get('page', '?')}",
            authors=[],
            year=None,
            venue=cite.get("document", ""),
            doi="",
            url="",
        ))

    cfg = get_ollama_config()
    model_used = result.get("model_used", cfg["chat_model"])

    return AIAnswerResponse(
        answer=result.get("answer", ""),
        sources=sources,
        status=result.get("status", "UNKNOWN"),
        model_used=model_used,
        query=req.query,
        error=result.get("error"),
        hint=result.get("hint"),
    )
