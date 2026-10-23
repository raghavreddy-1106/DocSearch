import re
from typing import List, Dict, Any, Optional
from app.services.document_store import doc_store
from app.services.hybrid_rag import hybrid_rag
from app.services.search_service import DEFINITION_TRIGGERS


class RAGEngine:
    """
    Authoritative search and answer engine for DocSearch.
    Directly backed by the Hybrid RAG engine (local Ollama inference,
    local embeddings, table-aware reranking, and dynamic evidence verification).
    """

    def __init__(self, document_store=doc_store):
        self.store = document_store

    def generate_answer(
        self,
        query: str,
        document_names: Optional[List[str]] = None,
        user_roles: Optional[List[str]] = None,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Unified search + grounded Q&A execution.
        Returns both search results and verified AI answer with full context.
        """
        clean_q = query.strip()
        if not clean_q:
            return {
                "answer": "Please enter a query.",
                "status": "EMPTY",
                "confidence": "N/A",
                "evidence": [],
                "citations": [],
                "sources": [],
                "search_results": None,
                "diagnostics": {},
            }

        rag_result = hybrid_rag.generate(
            query=clean_q,
            user_email=user_email,
            document_names=document_names,
            user_id=user_id,
            model=model,
        )

        # Build formatted sources for the frontend
        citations = rag_result.get("citations", [])
        evidence = rag_result.get("evidence", [])
        sources = [
            {
                "title": f"{c.get('document', 'Document')} — Page {c.get('page', 1)}",
                "authors": [],
                "year": None,
                "venue": c.get("document", ""),
                "doi": "",
                "url": "",
            }
            for c in citations
        ]

        return {
            "answer": rag_result.get("answer", ""),
            "status": rag_result.get("status", "SUCCESS"),
            "confidence": rag_result.get("confidence", "HIGH"),
            "evidence": evidence,
            "citations": citations,
            "sources": sources,
            "search_results": rag_result.get("search_results"),
            "diagnostics": {
                **(rag_result.get("retrieval_info") or {}),
                "model_used": rag_result.get("model_used"),
                "latency_s": rag_result.get("latency_s", 0),
            },
        }


rag_engine = RAGEngine(doc_store)
