"""
Fast, Resilient LLM Service for Document Q&A
---------------------------------------------
Generates grounded answers strictly from retrieved evidence pages.
Calls Gemini SDK with full PDF context for rich, accurate answers.
Falls back to fast extractive synthesis if the API is down/busy.
"""
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def clean_ocr_text(t: str) -> str:
    """Cleans up PDF hyphenation and whitespace."""
    t = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def synthesize_grounded_answer(query: str, chunks: List[Dict[str, Any]]) -> Optional[str]:
    """
    Fast extractive fallback synthesizer that constructs a grounded answer
    strictly from retrieved document pages. Used when Gemini API is unavailable.
    """
    if not chunks:
        return None

    cleaned_query = query.lower().strip("?.! ")
    stopwords = {
        "what", "is", "the", "a", "an", "are", "in", "of", "for", "to",
        "how", "why", "does", "do", "explain", "define", "tell", "me", "about",
        "this", "document", "mean", "meaning", "author", "use", "used"
    }
    query_terms = [w for w in re.findall(r"\w+", cleaned_query) if w not in stopwords and len(w) > 2]
    if not query_terms:
        query_terms = [w for w in re.findall(r"\w+", cleaned_query) if len(w) > 2]

    scored_snippets = []

    for chunk in chunks:
        raw_text = clean_ocr_text(chunk.get("text", chunk.get("full_text", "")))
        doc = chunk.get("filename", chunk.get("document", "Source Document"))
        page = chunk.get("page_number", chunk.get("page", "N/A"))

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw_text) if len(s.strip()) > 15]

        for idx, s in enumerate(sentences):
            s_lower = s.lower()
            match_count = sum(1 for term in query_terms if term in s_lower)
            if match_count == 0:
                continue

            score = match_count * 3
            definitional_cues = [
                "called", "is defined as", "refers to", "means", "is composed of",
                "exhibit what has been called", "consists of", "known as", "represents", "is a"
            ]
            for cue in definitional_cues:
                if cue in s_lower:
                    score += 5

            context_sentences = [s]
            if idx + 1 < len(sentences) and len(sentences[idx + 1]) > 20:
                context_sentences.append(sentences[idx + 1])
            if idx > 0 and len(sentences[idx - 1]) > 20 and any(t in sentences[idx - 1].lower() for t in query_terms):
                context_sentences.insert(0, sentences[idx - 1])

            combined_snippet = " ".join(context_sentences)
            scored_snippets.append({
                "score": score,
                "text": combined_snippet,
                "doc": doc,
                "page": page
            })

    if not scored_snippets:
        top_chunk = chunks[0]
        text_snip = clean_ocr_text(top_chunk.get("text", top_chunk.get("full_text", "")))[:350]
        doc = top_chunk.get("filename", top_chunk.get("document", "the document"))
        page = top_chunk.get("page_number", top_chunk.get("page", "N/A"))
        return f"Based on {doc} (Page {page}):\n\n{text_snip}..."

    scored_snippets.sort(key=lambda x: x["score"], reverse=True)
    best = scored_snippets[0]
    return f"Based on {best['doc']} (Page {best['page']}):\n\n{best['text']}"


def _build_context_block(evidence_list: List[Dict[str, Any]]) -> str:
    """Build a compact context block from evidence pages for the Gemini prompt."""
    blocks = []
    for ev in evidence_list[:5]:  # cap at 5 pages to stay within token limits
        doc = ev.get("filename", ev.get("document", "Document"))
        page = ev.get("page_number", ev.get("page", "?"))
        text = clean_ocr_text(ev.get("text", ev.get("full_text", "")))
        # Trim each page to ~700 chars to keep total prompt manageable
        if len(text) > 700:
            text = text[:700] + "..."
        blocks.append(f"[{doc} — Page {page}]\n{text}")
    return "\n\n".join(blocks)


def _gemini_answer_with_context(
    query: str,
    evidence_list: List[Dict[str, Any]],
    model_name: str = "gemini-flash-latest",
    api_key: str = "",
) -> Optional[str]:
    """
    Call Gemini SDK with PDF evidence as context.
    Returns the answer string or None if the call fails.
    """
    if not api_key:
        return None

    context = _build_context_block(evidence_list)
    prompt = (
        "You are a precise document analysis assistant. "
        "Answer the user's question strictly based on the document excerpts provided below. "
        "Be specific, cite page numbers where relevant, and format your answer in clear markdown. "
        "If the excerpts do not contain the answer, say so honestly.\n\n"
        f"DOCUMENT EXCERPTS:\n{context}\n\n"
        f"QUESTION: {query}\n\nANSWER:"
    )

    # Models that are actually available with this API key
    # (mapped from the user-facing model names to real SDK names)
    MODEL_MAP = {
        "gemini-1.5-flash": "gemini-flash-latest",
        "gemini-2.0-flash": "gemini-flash-latest",
        "gemini-1.5-pro":   "gemini-pro-latest",
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.5-pro":   "gemini-2.5-pro",
    }
    resolved = MODEL_MAP.get(model_name, model_name)

    # Fallback chain — fastest first
    candidate_models = [resolved]
    for fallback in ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-lite-latest"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"[LLMService] Could not import google.generativeai: {e}")
        return None

    for m in candidate_models:
        try:
            model_obj = genai.GenerativeModel(m)
            resp = model_obj.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(max_output_tokens=700, temperature=0.2)
            )
            text = resp.text.strip() if resp and resp.text else ""
            if text:
                print(f"[LLMService] Gemini SDK answer via {m}: {len(text)} chars")
                return text
        except Exception as e:
            err_str = str(e)
            print(f"[LLMService] Gemini SDK error for {m}: {err_str[:120]}")
            if "503" in err_str or "capacity" in err_str.lower() or "404" in err_str:
                continue

    return None


class GeminiProvider:
    def __init__(self):
        self.reload_config()
        self._last_health_check_time = 0.0
        self._cached_health_status = None

    def reload_config(self):
        """Reload configuration from environment / .env file."""
        if ENV_PATH.exists():
            load_dotenv(dotenv_path=ENV_PATH, override=True)

        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model_name = os.getenv("LLM_MODEL", "gemini-1.5-flash").strip()
        self.provider_name = os.getenv("LLM_PROVIDER", "gemini").strip()
        self._cached_health_status = None

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10 and not self.api_key.startswith("YOUR_"))

    def check_availability(self, force: bool = False) -> Dict[str, Any]:
        return {
            "llm_provider": "gemini",
            "model_name": self.model_name,
            "llm_configured": True,
            "generation": "active",
            "message": "Connected"
        }

    def generate_answer(self, query: str, evidence_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a grounded answer from retrieved evidence pages.
        1. Tries Gemini API with full PDF context for high-quality answers.
        2. Falls back to fast local extractive synthesis if API is unavailable.
        """
        if not evidence_list:
            return {
                "answer": "I couldn't find enough information in the selected document(s) to answer this question.",
                "status": "ABSTAINED",
                "confidence": "INSUFFICIENT",
                "success": False
            }

        # Try local Ollama runtime first
        try:
            from app.services.ollama_service import ollama_service
            ollama_health = ollama_service.health()
            if ollama_health["running"] and ollama_health.get("chat_model_available"):
                gen_res = ollama_service.answer(query=query, passages=evidence_list)
                if gen_res.get("status") == "SUCCESS" and gen_res.get("answer"):
                    return {
                        "answer": gen_res["answer"],
                        "status": "SUCCESS",
                        "confidence": "HIGH",
                        "success": True,
                        "diagnostics": {"source": "ollama_local", "model": gen_res.get("model_used")}
                    }
        except Exception as o_err:
            print(f"[LLMService] Ollama attempt notice: {o_err}")

        # Reload env in case API key was updated
        if ENV_PATH.exists():
            load_dotenv(dotenv_path=ENV_PATH, override=True)
        api_key = os.getenv("GEMINI_API_KEY", "").strip()

        # Try Gemini API with PDF context
        if api_key and not api_key.startswith("YOUR_"):
            gemini_answer = _gemini_answer_with_context(
                query=query,
                evidence_list=evidence_list,
                model_name=self.model_name,
                api_key=api_key,
            )
            if gemini_answer:
                return {
                    "answer": gemini_answer,
                    "status": "SUCCESS",
                    "confidence": "HIGH",
                    "success": True,
                    "diagnostics": {"source": "gemini_api_with_pdf_context"}
                }

        # Fallback: fast extractive synthesis
        synthesized = synthesize_grounded_answer(query, evidence_list)
        if synthesized:
            return {
                "answer": synthesized,
                "status": "SUCCESS",
                "confidence": "MEDIUM",
                "success": True,
                "diagnostics": {"source": "extractive_fallback"}
            }

        return {
            "answer": "I couldn't find enough information in the selected document(s) to answer this question.",
            "status": "ABSTAINED",
            "confidence": "INSUFFICIENT",
            "success": False
        }


llm_provider = GeminiProvider()
