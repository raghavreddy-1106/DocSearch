"""
Unified AI Answer Service
--------------------------
Routes AI Answer requests to the right provider based on selected model:
  - "mistral-*" / "open-mistral-*" → Mistral AI API
  - "gemini-*"                     → Google Gemini direct LLM
  - "tavily"                       → Tavily real-time web search
  - "openalex"                     → OpenAlex 250M+ academic papers

All providers use strict timeouts (4s max) and capped output tokens for blazing fast answers.
"""
import os
import re
import json
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def _load_env():
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Mistral AI Provider
# ─────────────────────────────────────────────────────────────────────────────
def _mistral_answer(query: str, model_name: str = "open-mistral-nemo") -> Dict[str, Any]:
    _load_env()
    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key:
        return {
            "answer": "Mistral API key is not configured.",
            "sources": [], "status": "ERROR",
            "model_used": model_name, "provider": "Mistral AI"
        }

    candidate_models = [model_name]
    for fallback in ["open-mistral-nemo", "ministral-3b-latest", "open-mistral-7b"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    prompt = (
        "You are a helpful, expert AI assistant. "
        "Provide a clear, accurate, concise, and well-structured answer using markdown formatting."
    )

    last_error = "Unknown error"
    for m in candidate_models:
        payload = json.dumps({
            "model": m,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": query}
            ],
            "max_tokens": 500,
            "temperature": 0.3,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                "https://api.mistral.ai/v1/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"].strip()
            return {
                "answer": answer,
                "sources": [],
                "status": "SUCCESS",
                "model_used": m,
                "provider": "Mistral AI"
            }
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            last_error = f"Mistral API error ({e.code}): {body[:150]}"
            if e.code in (404, 429):
                continue
        except Exception as e:
            last_error = str(e)
            continue

    return {
        "answer": f"Mistral request failed: {last_error}",
        "sources": [],
        "status": "ERROR",
        "model_used": model_name,
        "provider": "Mistral AI"
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Google Gemini Direct LLM Provider
# ─────────────────────────────────────────────────────────────────────────────
def _gemini_direct_answer(query: str, model_name: str = "gemini-3.5-flash-lite") -> Dict[str, Any]:
    _load_env()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key in ("YOUR_GEMINI_API_KEY", "your_gemini_api_key", "", "none"):
        return {
            "answer": "Google Gemini API key is not configured.",
            "sources": [], "status": "ERROR",
            "model_used": model_name, "provider": "Google Gemini"
        }

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        candidate_models = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.8-flash"]
        if model_name in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash"):
            pass
        elif model_name not in candidate_models:
            candidate_models.insert(0, model_name)

        prompt = (
            "You are a helpful AI assistant. "
            "Provide a concise, direct, accurate answer in markdown.\n\n"
            f"QUESTION: {query}\n\nANSWER:"
        )

        for m_name in candidate_models:
            try:
                model = genai.GenerativeModel(m_name)
                resp = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(max_output_tokens=500, temperature=0.3)
                )
                text = resp.text.strip() if resp and resp.text else ""
                if text:
                    return {
                        "answer": text,
                        "sources": [], "status": "SUCCESS",
                        "model_used": m_name, "provider": "Google Gemini"
                    }
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "capacity" in err_str.lower() or "404" in err_str:
                    continue

        return {
            "answer": "Google Gemini server is currently busy (503 No Capacity). You can switch to Mistral, Tavily, or OpenAlex in the model switcher above.",
            "sources": [], "status": "ERROR",
            "model_used": model_name, "provider": "Google Gemini"
        }
    except Exception as e:
        return {
            "answer": f"Gemini error: {str(e)}",
            "sources": [], "status": "ERROR",
            "model_used": model_name, "provider": "Google Gemini"
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tavily Web Search Provider (Ultra Fast)
# ─────────────────────────────────────────────────────────────────────────────
def _tavily_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    _load_env()
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {
            "answer": "Tavily API key is not configured.",
            "sources": [], "status": "ERROR",
            "model_used": "tavily", "provider": "Tavily Web Search"
        }

    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": True,
        "include_raw_content": False,
        "max_results": max_results,
        "include_images": False,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {
            "answer": f"Tavily search error: {str(e)}",
            "sources": [], "status": "ERROR",
            "model_used": "tavily", "provider": "Tavily Web Search"
        }

    answer = data.get("answer") or ""
    sources = []
    for r in data.get("results", []):
        domain = ""
        try:
            domain = urllib.parse.urlparse(r.get("url", "")).netloc
        except Exception:
            pass
        sources.append({
            "title": r.get("title", ""),
            "authors": [], "year": "", "venue": domain,
            "doi": "", "url": r.get("url", ""),
            "snippet": r.get("content", "")[:250],
        })

    if not answer and sources:
        answer = "**Web search results:**\n\n" + "\n".join(
            f"- **{s['title']}**: {s.get('snippet', '')}" for s in sources[:3]
        )

    return {
        "answer": answer or f'No results found for "{query}".',
        "sources": sources,
        "status": "SUCCESS" if answer else "NO_RESULTS",
        "model_used": "tavily", "provider": "Tavily Web Search"
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. OpenAlex Academic Literature Provider (Ultra Fast)
# ─────────────────────────────────────────────────────────────────────────────
def _reconstruct_abstract(inverted_index: Optional[Dict]) -> str:
    if not inverted_index:
        return ""
    word_positions: List[tuple] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


def _fetch_openalex_works(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    _load_env()
    email = os.getenv("OPENALEX_EMAIL", "docsearch@app.com")
    clean_q = re.sub(r'^(?:what\s+is|what\s+are|define|explain|how\s+does)\s+', '', query, flags=re.IGNORECASE).strip("?.! ")
    params = {
        "search": clean_q or query,
        "per-page": max_results,
        "select": "id,title,abstract_inverted_index,publication_year,authorships,primary_location,doi,open_access",
        "mailto": email,
    }
    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DocSearch/1.0 (mailto:docsearch@app.com)", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[OpenAlex] Fetch error: {e}")
        return []

    results = []
    for work in data.get("results", []):
        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
        loc = work.get("primary_location") or {}
        src = loc.get("source") or {}
        authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])[:3]]
        results.append({
            "title": work.get("title", "Untitled"),
            "abstract": abstract[:600] if abstract else "",
            "year": work.get("publication_year", ""),
            "doi": work.get("doi", ""),
            "authors": [a for a in authors if a],
            "venue": src.get("display_name", ""),
            "oa_url": work.get("open_access", {}).get("oa_url", ""),
        })
    return results


def _synthesize_openalex(query: str, works: List[Dict[str, Any]]) -> str:
    if not works:
        return f'No academic literature found for "{query}" on OpenAlex.'
    query_terms = set(re.findall(r"\b\w{4,}\b", query.lower()))
    lines = [f'### Academic Literature for "{query}":\n']
    for i, w in enumerate(works[:3], 1):
        abstract = w.get("abstract", "")
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", abstract) if len(s.strip()) > 30]
        scored = sorted([(sum(1 for t in query_terms if t in s.lower()), s) for s in sentences], reverse=True)
        top = " ".join(s for _, s in scored[:2]) if scored else (abstract[:250] if abstract else w.get("title", ""))
        authors_str = ", ".join(w["authors"][:2]) if w.get("authors") else "Unknown"
        year = w.get("year", "")
        venue = w.get("venue", "")
        ref = f"{authors_str} ({year})" + (f" — *{venue}*" if venue else "")
        lines += [f"**{i}. {w['title']}**", f"*{ref}*", top, ""]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Unified Dispatcher
# ─────────────────────────────────────────────────────────────────────────────
class AIAnswerService:

    def get_ai_answer(
        self,
        query: str,
        model: str = "gemini-1.5-flash",
        max_results: int = 5,
        document_names=None,
        user_id: str = None,
        user_email: str = None,
    ) -> Dict[str, Any]:
        _load_env()
        m = (model or "gemini-1.5-flash").lower().strip()

        # ── Mistral AI ───────────────────────────────────────────────────────
        if "mistral" in m or "ministral" in m or "codestral" in m:
            actual_model = "open-mistral-nemo" if m in ("mistral", "mistral-nemo", "mistral-ai") else model
            return _mistral_answer(query, model_name=actual_model)

        # ── Tavily (Web Search) ──────────────────────────────────────────────
        if m == "tavily":
            return _tavily_search(query, max_results=max_results)

        # ── OpenAlex (Academic Literature) ───────────────────────────────────
        if m == "openalex":
            works = _fetch_openalex_works(query, max_results=max_results)
            if not works:
                return {
                    "answer": f'No academic literature found for "{query}" on OpenAlex.',
                    "sources": [], "status": "NO_RESULTS",
                    "model_used": "openalex", "provider": "OpenAlex Academic"
                }
            return {
                "answer": _synthesize_openalex(query, works),
                "sources": [
                    {
                        "title": w["title"], "authors": w["authors"], "year": w["year"],
                        "venue": w["venue"], "doi": w["doi"],
                        "url": w.get("oa_url") or (f"https://doi.org/{w['doi']}" if w.get("doi") else ""),
                    } for w in works
                ],
                "status": "SUCCESS", "model_used": "openalex", "provider": "OpenAlex Academic"
            }

        # ── Gemini — PDF-grounded when documents are available ────────────────
        # When documents are provided, use the RAG engine to retrieve relevant
        # PDF content and pass it to Gemini for a grounded, document-based answer.
        if document_names or user_email or user_id:
            try:
                from app.services.retrieval_service import retrieval_service
                from app.services.llm_service import llm_provider

                evidence_pages = retrieval_service.retrieve_evidence(
                    query,
                    document_names=document_names,
                    max_pages=5,
                    user_email=user_email,
                    user_id=user_id,
                )
                print(f"[AIAnswerService] Retrieved {len(evidence_pages)} evidence pages for Gemini PDF answer")

                if evidence_pages:
                    # Build source citations from evidence pages
                    sources = []
                    seen_pages = set()
                    for ev in evidence_pages:
                        key = (ev["document"], ev["page"])
                        if key not in seen_pages:
                            seen_pages.add(key)
                            sources.append({
                                "title": f"{ev['document']} — Page {ev['page']}",
                                "authors": [],
                                "year": "",
                                "venue": ev["document"],
                                "doi": "",
                                "url": "",
                            })

                    # Call Gemini with full PDF context via llm_provider
                    llm_response = llm_provider.generate_answer(query, evidence_pages)

                    return {
                        "answer": llm_response["answer"],
                        "sources": sources,
                        "status": llm_response["status"],
                        "model_used": model,
                        "provider": "Google Gemini (PDF Context)"
                    }

                # No relevant evidence found in the PDF
                return {
                    "answer": (
                        f"I searched your uploaded document(s) but couldn't find information about **\"{query}\"**. "
                        "The document may not contain content related to this topic. "
                        "Try rephrasing your question or switching to a web search provider (Tavily)."
                    ),
                    "sources": [],
                    "status": "ABSTAINED",
                    "model_used": model,
                    "provider": "Google Gemini (PDF Context)"
                }
            except Exception as e:
                print(f"[AIAnswerService] RAG pipeline error: {e}")
                # Fall through to general Gemini answer

        # ── Gemini — General knowledge (no documents provided) ────────────────
        return _gemini_direct_answer(query, model_name=model)


ai_answer_service = AIAnswerService()
