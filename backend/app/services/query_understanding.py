"""
Document-Aware Query Understanding Service
-------------------------------------------
Interprets user queries dynamically before retrieval without hardcoded dictionaries.
1. Detects potential abbreviations/acronyms and entities in the user query.
2. Dynamically scans the active document's text and headings to discover candidate domain terms and abbreviations.
3. Uses the configured local Ollama LLM to resolve ambiguous terms based on actual document context.
4. Generates search variations (original, expanded, entity-focused) to maximize retrieval precision.
"""
import re
import json
import urllib.request
from typing import List, Dict, Any, Optional

from app.services.document_store import doc_store
from app.services.ollama_service import get_ollama_config


def extract_acronym_candidates_from_docs(
    acronym: str,
    user_email: str,
    document_names: Optional[List[str]] = None,
    max_candidates: int = 10,
) -> List[str]:
    """
    Dynamically scan the active document's chunks to discover phrases whose initials
    match the letters of an acronym, or parenthetical occurrences like 'Term (ACR)' or 'ACR (Term)'.
    No hardcoded mappings.
    """
    letters = [ch for ch in acronym if ch.isalpha()]
    if len(letters) < 2 or len(letters) > 6:
        return []

    # Pattern for words starting with each letter of the acronym: e.g. for PE -> \b(P[a-zA-Z]+)\s+(E[a-zA-Z]+)\b
    pattern_str = r"\b" + r"\s+".join([rf"({l}[a-zA-Z]+)" for l in letters]) + r"\b"
    initials_pat = re.compile(pattern_str, re.IGNORECASE)

    paren_pat1 = re.compile(rf"([A-Za-z\s]{{3,40}})\s*\({re.escape(acronym)}\)", re.IGNORECASE)
    paren_pat2 = re.compile(rf"{re.escape(acronym)}\s*\(([A-Za-z\s]{{3,40}})\)", re.IGNORECASE)

    candidates: Dict[str, int] = {}
    clean_email = (user_email or "").strip().lower()

    for chunk in doc_store.chunks:
        chunk_email = (chunk.get("user_email") or "").strip().lower()
        if clean_email and chunk_email != clean_email:
            continue
        if document_names and chunk.get("filename") not in document_names:
            continue

        text = chunk.get("text", "")

        # 1. Initials pattern match
        for m in initials_pat.finditer(text):
            phrase = m.group(0).strip()
            # Normalize casing
            phrase_norm = " ".join(w.capitalize() for w in phrase.split())
            candidates[phrase_norm] = candidates.get(phrase_norm, 0) + 1

        # 2. Parenthetical definitions
        for m in paren_pat1.finditer(text):
            p = m.group(1).strip()
            if 1 <= len(p.split()) <= 5:
                p_norm = " ".join(w.capitalize() for w in p.split())
                candidates[p_norm] = candidates.get(p_norm, 0) + 10

        for m in paren_pat2.finditer(text):
            p = m.group(1).strip()
            if 1 <= len(p.split()) <= 5:
                p_norm = " ".join(w.capitalize() for w in p.split())
                candidates[p_norm] = candidates.get(p_norm, 0) + 10

    sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return [c[0] for c in sorted_candidates[:max_candidates]]


def extract_document_top_concepts(
    user_email: str,
    document_names: Optional[List[str]] = None,
    max_terms: int = 30,
) -> List[str]:
    """
    Extract major multi-word capitalized headings and components from the document index.
    """
    concepts: Dict[str, int] = {}
    clean_email = (user_email or "").strip().lower()

    for chunk in doc_store.chunks:
        chunk_email = (chunk.get("user_email") or "").strip().lower()
        if clean_email and chunk_email != clean_email:
            continue
        if document_names and chunk.get("filename") not in document_names:
            continue

        text = chunk.get("text", "")
        # Match capitalized multi-word phrases (e.g. 'Program Elective', 'Foundation Core')
        for m in re.finditer(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}\b", text):
            phrase = m.group(0).strip()
            if 4 < len(phrase) < 40:
                concepts[phrase] = concepts.get(phrase, 0) + 1

    sorted_concepts = sorted(concepts.items(), key=lambda x: x[1], reverse=True)
    return [c[0] for c in sorted_concepts[:max_terms]]


class QueryPlan:
    def __init__(
        self,
        original_query: str,
        target_entity: str,
        information_type: str,
        resolved_entity: Optional[str] = None,
        expanded_query: Optional[str] = None,
        search_queries: Optional[List[str]] = None,
        detected_acronyms: Optional[List[str]] = None,
    ):
        self.original_query = original_query
        self.target_entity = target_entity
        self.information_type = information_type
        self.resolved_entity = resolved_entity
        self.expanded_query = expanded_query or original_query
        self.search_queries = search_queries or [original_query]
        self.detected_acronyms = detected_acronyms or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "target_entity": self.target_entity,
            "information_type": self.information_type,
            "resolved_entity": self.resolved_entity,
            "expanded_query": self.expanded_query,
            "search_queries": self.search_queries,
            "detected_acronyms": self.detected_acronyms,
        }


class QueryUnderstandingService:
    """
    Service for document-aware intent extraction and query enrichment.
    Results are cached per (query, document_names) to avoid redundant Ollama calls.
    """

    def __init__(self):
        self._cache: dict = {}
        self._cache_max_size = 200

    def _cache_key(self, query: str, document_names) -> str:
        import hashlib
        doc_str = ','.join(sorted(document_names or []))
        return hashlib.md5(f"{query.strip().lower()}|{doc_str}".encode()).hexdigest()

    def analyze_query(
        self,
        query: str,
        user_email: str,
        document_names: Optional[List[str]] = None,
        timeout: int = 15,
    ) -> QueryPlan:
        q_clean = query.strip()
        if not q_clean:
            return QueryPlan(query, "", "general")

        # Check cache first to avoid redundant Ollama LLM calls
        cache_key = self._cache_key(q_clean, document_names)
        if cache_key in self._cache:
            print(f"[QueryUnderstanding] Cache hit for query: {q_clean[:50]}")
            return self._cache[cache_key]

        # 1. Identify uppercase potential acronyms (2-5 letters) from user query
        # e.g., 'PE', 'ML', 'CSE', 'AI'
        words = re.findall(r"\b[A-Za-z]{2,6}\b", q_clean)
        # Identify potential acronyms: uppercase 2-6 letter tokens, or short 2-4 letter tokens
        # that are not common English function words and match expansions in the document.
        COMMON_WORDS = {
            "to", "in", "on", "at", "it", "is", "we", "he", "me", "my", "do", "no", "so", "up",
            "as", "by", "if", "or", "an", "be", "of", "am", "us", "go", "how", "why", "the", "and",
            "for", "are", "but", "not", "you", "all", "any", "can", "had", "her", "was", "one", "our",
            "out", "day", "get", "has", "him", "his", "man", "new", "now", "old", "see", "two",
            "way", "who", "boy", "did", "its", "let", "put", "say", "she", "too", "use", "what", "which",
            "from", "with", "have", "been", "will", "would", "could", "should", "want", "earn"
        }
        potential_acronyms = []
        for w in words:
            w_lower = w.lower()
            if w.isupper() and 2 <= len(w) <= 6:
                potential_acronyms.append(w.upper())
            elif 2 <= len(w) <= 4 and w_lower not in COMMON_WORDS:
                # Dynamic check: does the document contain initials or parenthetical matching this token?
                candidate_matches = extract_acronym_candidates_from_docs(
                    w.upper(), user_email, document_names=document_names, max_candidates=2
                )
                if candidate_matches:
                    potential_acronyms.append(w.upper())

        # Deduplicate
        potential_acronyms = list(dict.fromkeys(potential_acronyms))

        # 2. Gather candidate expansions from document context
        acronym_candidates: Dict[str, List[str]] = {}
        for acr in potential_acronyms:
            cands = extract_acronym_candidates_from_docs(
                acr, user_email, document_names=document_names, max_candidates=8
            )
            if cands:
                acronym_candidates[acr] = cands

        # 3. Gather top document concepts for context
        doc_concepts = extract_document_top_concepts(user_email, document_names=document_names, max_terms=20)

        # 4. Prompt Ollama for structured interpretation
        cfg = get_ollama_config()
        base_url = cfg["base_url"]
        model = cfg["chat_model"]

        prompt = (
            "You are a document-aware search query analyzer. Interpret the user's question in the context of the document.\n"
            "Output valid JSON only with keys: 'target_entity', 'information_type', 'resolved_entity', 'expanded_query', 'search_queries'.\n\n"
            f"USER QUERY: \"{q_clean}\"\n"
            f"DETECTED ACRONYMS IN QUERY: {json.dumps(potential_acronyms)}\n"
            f"DOCUMENT CANDIDATE EXPANSIONS FOR ACRONYMS: {json.dumps(acronym_candidates)}\n"
            f"DOCUMENT HEADINGS SAMPLE: {json.dumps(doc_concepts[:15])}\n\n"
            "RULES:\n"
            "1. 'target_entity': The specific subject, course category, or concept requested.\n"
            "2. 'information_type': 'numeric_quantity' (if asking for credits, count, hours, cost, percent), 'explanation', 'list', or 'procedure'.\n"
            "3. 'resolved_entity': If an acronym matches a candidate expansion from the document that fits the query's subject, return that exact candidate name (e.g. 'Program Elective'). Otherwise null.\n"
            "4. 'expanded_query': Rewritten query substituting any resolved acronyms with their document expansion.\n"
            "5. 'search_queries': An array containing [original_query, expanded_query, and 1-2 focused keyword search phrases].\n\n"
            "JSON output:"
        )

        try:
            payload = json.dumps({
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 300,
                    "num_ctx": 4096,
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                res_json = json.loads(resp_data.get("response", "{}"))

            target_entity = res_json.get("target_entity")
            resolved_entity = res_json.get("resolved_entity")
            if not target_entity or target_entity == "None" or str(target_entity).lower() == "none":
                target_entity = resolved_entity or q_clean
            # Clean leading question boilerplate if target_entity is a full sentence
            if target_entity and len(target_entity) > 15:
                cleaned_target = re.sub(r"^(what\s+(is|are|were)|how\s+(many|much)|find|tell\s+me\s+about|give\s+me)\s+(the\s+)?(total\s+)?(credits?\s+(for|of|in|to\s+complete)\s+)?", "", target_entity, flags=re.I).strip("? .")
                if len(cleaned_target) >= 2:
                    target_entity = cleaned_target
            if resolved_entity == "None" or str(resolved_entity).lower() == "none":
                resolved_entity = None

            info_type = res_json.get("information_type", "general")
            expanded_query = res_json.get("expanded_query") or q_clean
            search_queries = res_json.get("search_queries") or [q_clean]

            # If resolved_entity is missing but expanded_query introduced words from candidate list:
            if not resolved_entity and acronym_candidates:
                for acr, cands in acronym_candidates.items():
                    for c in cands:
                        if c.lower() in (expanded_query or "").lower():
                            resolved_entity = c
                            if not target_entity or target_entity == q_clean:
                                target_entity = c
                            break

            # Ensure original query is always in search_queries
            if q_clean not in search_queries:
                search_queries.insert(0, q_clean)
            if expanded_query and expanded_query not in search_queries:
                search_queries.append(expanded_query)

            print(f"[QueryUnderstanding] Target: '{target_entity}' | Type: {info_type} | Resolved: {resolved_entity}")

            qplan = QueryPlan(
                original_query=q_clean,
                target_entity=target_entity,
                information_type=info_type,
                resolved_entity=resolved_entity,
                expanded_query=expanded_query,
                search_queries=search_queries,
                detected_acronyms=potential_acronyms,
            )
            # Cache result (evict oldest if full)
            if len(self._cache) >= self._cache_max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[cache_key] = qplan
            return qplan

        except Exception as e:
            print(f"[QueryUnderstanding] Fallback to original query due to error: {e}")
            # Dynamic fallback: if we found document candidates for an acronym, use the top candidate
            resolved = None
            expanded = q_clean
            if acronym_candidates:
                first_acr = list(acronym_candidates.keys())[0]
                cands = acronym_candidates[first_acr]
                if cands:
                    resolved = cands[0]
                    expanded = re.sub(rf"\b{re.escape(first_acr)}\b", resolved, q_clean, flags=re.IGNORECASE)

            # Detect if numeric quantity is requested
            is_numeric = bool(re.search(r"\b(how many|how much|credits?|number of|total|units?|hours?)\b", q_clean, re.I))

            search_qs = [q_clean]
            if expanded != q_clean:
                search_qs.append(expanded)
            if resolved:
                query_terms = [t for t in q_clean.split() if t.lower() not in COMMON_WORDS and t.lower() != resolved.lower()]
                search_qs.append(f"{resolved} {' '.join(query_terms)}".strip())

            return QueryPlan(
                original_query=q_clean,
                target_entity=resolved or q_clean,
                information_type="numeric_quantity" if is_numeric else "general",
                resolved_entity=resolved,
                expanded_query=expanded,
                search_queries=search_qs,
                detected_acronyms=potential_acronyms,
            )


query_understanding = QueryUnderstandingService()
