import re
import math
from typing import List, Dict, Any, Optional
from app.services.document_store import doc_store

DEFINITION_TRIGGERS = re.compile(
    r'^(?:what\s+(?:is|are|was|were)|what\s+does\s+.+?\s+mean|define|meaning\s+of|explain|how\s+does\s+.+?\s+work)',
    re.IGNORECASE
)

STOPWORDS = {
    "what", "is", "the", "a", "an", "are", "in", "of", "for", "to",
    "how", "why", "does", "do", "explain", "define", "tell", "me", "about",
    "this", "document", "mean", "meaning", "author", "use", "used", "does",
    "way", "can", "could", "would", "should", "will", "may", "might",
    "with", "from", "by", "on", "at", "that", "which", "it", "its"
}

def extract_query_terms(query: str) -> List[str]:
    """Extract meaningful search terms from any query."""
    q = query.strip().lower()
    # Remove question markers and leading question words
    q = re.sub(r'[?.!,;:"\']', ' ', q)
    words = re.findall(r'[\w\-]+', q)
    terms = [w for w in words if w not in STOPWORDS and len(w) > 1]
    if not terms:
        # fallback: keep any word longer than 2 chars
        terms = [w for w in words if len(w) > 2]
    return terms

def normalize_text(text: str) -> str:
    text = re.sub(r'[\r\n\t]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_snippet(text: str, match_start: int, match_end: int, window: int = 150) -> str:
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    if start > 0:
        sp = text.rfind(' ', max(0, start - 20), start)
        if sp != -1:
            start = sp + 1
    if end < len(text):
        sp = text.find(' ', end, min(len(text), end + 20))
        if sp != -1:
            end = sp
    snippet = text[start:end].strip()
    return ("..." if start > 0 else "") + snippet + ("..." if end < len(text) else "")

class SearchService:
    def __init__(self, store=doc_store):
        self.store = store

    def search_exact(
        self,
        query: str,
        document_names: Optional[List[str]] = None,
        sort_by: str = "page",
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Scans ALL indexed pages belonging to the user. Never restricts to top-K.
        Groups results by page. Each page appears exactly once.
        """
        raw_query = query.strip()
        if not raw_query:
            return {"query": query, "mode": "none", "total_pages": 0, "total_matches": 0, "results": [], "related_results": []}

        q_lower = raw_query.lower()
        q_tokens = [w for w in re.findall(r'[\w\-]+', q_lower) if len(w) > 0]
        if not q_tokens:
            return {"query": query, "mode": "none", "total_pages": 0, "total_matches": 0, "results": [], "related_results": []}

        email_clean = (user_email or "").strip().lower() if user_email else None

        if not email_clean and not user_id:
            return {"query": query, "mode": "none", "total_pages": 0, "total_matches": 0, "results": [], "related_results": []}

        # If user is specified and document_names is not, get user's documents
        if document_names is None:
            user_docs = set(d["filename"] for d in self.store.list_documents(user_email=email_clean, user_id=user_id))
            if not user_docs:
                return {"query": query, "mode": "none", "total_pages": 0, "total_matches": 0, "results": [], "related_results": []}
            document_names = list(user_docs)

        is_phrase = len(q_tokens) > 1

        # Build unique page texts (doc, page) -> full page text
        page_texts: Dict[tuple, str] = {}
        for chunk in self.store.chunks:
            chunk_email = (chunk.get("user_email") or "").strip().lower() if chunk.get("user_email") else None
            if email_clean and chunk_email != email_clean:
                continue
            if not email_clean:
                continue

            doc = chunk.get("filename", "Unknown")
            if document_names and doc not in document_names:
                continue
            page = chunk.get("page_number", 0)
            key = (doc, page)
            text = chunk.get("text", "")
            page_texts[key] = page_texts.get(key, "") + " " + text

        page_matches: Dict[tuple, Dict] = {}
        match_mode_used = "exact_phrase" if is_phrase else "exact_term"

        for (doc, page), raw_text in page_texts.items():
            norm_text = normalize_text(raw_text)
            norm_lower = norm_text.lower()
            snippets = []
            match_count = 0

            if is_phrase:
                # Exact phrase match first
                idx = 0
                while True:
                    found = norm_lower.find(q_lower, idx)
                    if found == -1:
                        break
                    match_count += 1
                    snip = extract_snippet(norm_text, found, found + len(q_lower))
                    # Highlight the match
                    hl = re.sub(re.escape(raw_query), f'**{raw_query}**', snip, flags=re.IGNORECASE)
                    if hl not in snippets:
                        snippets.append(hl)
                    idx = found + len(q_lower)

                if match_count == 0:
                    # Multi-term match using meaningful non-stopword terms
                    content_terms = extract_query_terms(raw_query)
                    if content_terms:
                        matched = [t for t in content_terms if re.search(rf'\b{re.escape(t)}\b', norm_lower)]
                        # Require at least 60% of query terms (or all if <=2 terms)
                        min_required = len(content_terms) if len(content_terms) <= 2 else max(2, int(len(content_terms) * 0.6))
                        if len(matched) >= min_required:
                            match_count = len(matched)
                            match_mode_used = "term_match"
                            for tok in matched:
                                m = re.search(rf'\b{re.escape(tok)}\b', norm_lower)
                                if m:
                                    snip = extract_snippet(norm_text, m.start(), m.end())
                                    hl = re.sub(rf'(\b{re.escape(tok)}\b)', r'**\1**', snip, flags=re.IGNORECASE)
                                    if hl not in snippets:
                                        snippets.append(hl)
            else:
                # Single term: word boundary match first, then substring
                term = q_tokens[0]
                pattern = re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
                for m in pattern.finditer(norm_lower):
                    match_count += 1
                    snip = extract_snippet(norm_text, m.start(), m.end())
                    hl = re.sub(rf'(\b{re.escape(term)}\b)', r'**\1**', snip, flags=re.IGNORECASE)
                    if hl not in snippets:
                        snippets.append(hl)

                if match_count == 0 and len(term) > 3:
                    # Substring fallback only for long terms
                    pattern2 = re.compile(re.escape(term), re.IGNORECASE)
                    for m in pattern2.finditer(norm_lower):
                        match_count += 1
                        snip = extract_snippet(norm_text, m.start(), m.end())
                        hl = re.sub(f'({re.escape(term)})', r'**\1**', snip, flags=re.IGNORECASE)
                        if hl not in snippets:
                            snippets.append(hl)

            if match_count > 0:
                page_matches[(doc, page)] = {
                    "document": doc,
                    "page": page,
                    "match_count": match_count,
                    "snippets": snippets[:5],  # up to 5 per page
                    "score": float(match_count)
                }

        # If phrase found no results, try focused related content using key terms
        related_results = []
        if len(page_matches) == 0 and is_phrase:
            match_mode_used = "no_matches"
            content_terms = extract_query_terms(raw_query)
            if content_terms:
                for (doc, page), raw_text in page_texts.items():
                    norm_text = normalize_text(raw_text)
                    norm_lower = norm_text.lower()
                    partial = [t for t in content_terms if re.search(rf'\b{re.escape(t)}\b', norm_lower)]
                    if partial and len(partial) >= 1:
                        m = re.search(rf'\b{re.escape(partial[0])}\b', norm_lower)
                        if m:
                            snip = extract_snippet(norm_text, m.start(), m.end())
                            hl = re.sub(rf'(\b{re.escape(partial[0])}\b)', r'**\1**', snip, flags=re.IGNORECASE)
                            related_results.append({
                                "document": doc,
                                "page": page,
                                "match_count": len(partial),
                                "snippets": [hl]
                            })
                related_results.sort(key=lambda x: x["match_count"], reverse=True)
                related_results = related_results[:10]

        results_list = list(page_matches.values())
        if sort_by == "relevance":
            results_list.sort(key=lambda x: x["score"], reverse=True)
        else:
            results_list.sort(key=lambda x: (x["document"], x["page"]))

        return {
            "query": query,
            "mode": match_mode_used,
            "total_pages": len(results_list),
            "total_matches": sum(r["match_count"] for r in results_list),
            "results": results_list,
            "related_results": related_results
        }


search_service = SearchService(doc_store)
from app.services.retrieval_service import retrieval_service, RetrievalService

