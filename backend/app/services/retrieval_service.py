import re
import math
from typing import List, Dict, Any, Optional
from app.services.document_store import doc_store

DEFINITION_TRIGGERS = [
    r"^what\s+(?:is|are|was|were)\s+(?:a\s+|an\s+|the\s+)?(.+?)\??$",
    r"^what\s+does\s+(.+?)\s+mean\??$",
    r"^define\s+(?:a\s+|an\s+|the\s+)?(.+?)\??$",
    r"^meaning\s+of\s+(.+?)\??$",
    r"^explain\s+(?:the\s+meaning\s+of\s+)?(?:a\s+|an\s+|the\s+)?(.+?)\??$",
    r"^how\s+does\s+the\s+document\s+explain\s+(.+?)\??$"
]

DEFINITION_PATTERNS = [
    r"\bcalled\s+{term}\b",
    r"\b{term}\s+(?:is|are|was|were)\b",
    r"\b{term}\s+refers\s+to\b",
    r"\b{term}\s+means\b",
    r"\bknown\s+as\s+{term}\b",
    r"\bthe\s+term\s+{term}\b",
    r"\bdefinition\s+of\s+{term}\b"
]

STOPWORDS = {
    "what", "is", "the", "a", "an", "are", "in", "of", "for", "to",
    "how", "why", "does", "do", "explain", "define", "tell", "me", "about",
    "this", "document", "mean", "meaning", "author", "use", "used"
}

class RetrievalService:
    def __init__(self, store=doc_store):
        self.store = store

    def detect_definition_intent(self, query: str) -> Optional[str]:
        """
        Checks if the query is asking for a definition or explanation of a term.
        Returns the extracted focal term or None.
        """
        q_clean = query.strip().lower()
        for pattern in DEFINITION_TRIGGERS:
            match = re.search(pattern, q_clean)
            if match:
                focal = match.group(1).strip()
                # Clean focal term
                focal = re.sub(r'^(?:the\s+|a\s+|an\s+)', '', focal)
                focal = re.sub(r'\s+in\s+this\s+document\??$', '', focal)
                focal = focal.strip("?.! \"'")
                if focal:
                    return focal
        return None

    def retrieve_evidence(
        self,
        query: str,
        document_names: Optional[List[str]] = None,
        max_pages: int = 5,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid retrieval combining exact definition matching, lexical BM25/keyword scoring,
        and contextual passage aggregation.
        Guarantees:
        - Pages appear uniquely (page-aware grouping).
        - Definition-style sentences receive heavy boost.
        - Returns structured evidence for both LLM context and UI citations.
        """
        email_clean = (user_email or "").strip().lower() if user_email else None

        if not email_clean and not user_id:
            return []

        if document_names is None:
            user_docs = set(d["filename"] for d in self.store.list_documents(user_email=email_clean, user_id=user_id))
            if not user_docs:
                return []
            document_names = list(user_docs)

        q_clean = query.strip().lower()
        focal_term = self.detect_definition_intent(q_clean)
        
        query_words = [w for w in re.findall(r'[\w\-]+', q_clean) if w not in STOPWORDS and len(w) > 2]
        if not query_words and focal_term:
            query_words = [w for w in re.findall(r'[\w\-]+', focal_term.lower()) if len(w) > 1]
        if not query_words:
            query_words = [w for w in re.findall(r'[\w\-]+', q_clean) if len(w) > 1]

        # Group chunks by (filename, page_number)
        page_chunks: Dict[tuple, List[str]] = {}
        for chunk in self.store.chunks:
            chunk_email = (chunk.get("user_email") or "").strip().lower() if chunk.get("user_email") else None
            if email_clean and chunk_email != email_clean:
                continue

            doc = chunk.get("filename", "")
            if document_names and doc not in document_names:
                continue
            page = chunk.get("page_number", 0)
            key = (doc, page)
            if key not in page_chunks:
                page_chunks[key] = []
            page_chunks[key].append(chunk.get("text", ""))

        scored_pages = []

        for (doc, page), texts in page_chunks.items():
            full_page_text = "\n".join(texts)
            text_lower = full_page_text.lower()
            
            score = 0.0
            highlighted_passages = []
            is_definition_hit = False

            # 1. Focal term match and definition patterns
            if focal_term:
                focal_lower = focal_term.lower()
                if focal_lower in text_lower:
                    score += 15.0 # High base score for focal term presence
                    
                    # Test specific definitional phrasing
                    for p_template in DEFINITION_PATTERNS:
                        pat = p_template.format(term=re.escape(focal_lower))
                        if re.search(pat, text_lower):
                            score += 25.0
                            is_definition_hit = True

                    # Find sentences containing the focal term
                    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_page_text) if len(s.strip()) > 15]
                    for s in sentences:
                        if focal_lower in s.lower():
                            highlighted_passages.append(s)

            # 2. Keyword overlap & BM25-like scoring across query words
            page_words = re.findall(r'[\w\-]+', text_lower)
            page_word_set = set(page_words)
            
            matches = [w for w in query_words if w in page_word_set]
            if matches:
                # BM25-like length normalized score
                tf_score = sum(text_lower.count(w) for w in matches)
                norm_len = math.log(len(page_words) + 10)
                score += (tf_score / norm_len) * 4.0

            # 3. Penalize pure index / bibliography pages if searching for conceptual definitions
            if "index" in text_lower[:200] or (len(re.findall(r'\b\d{1,3}\b', text_lower)) > 60 and len(page_words) < 200):
                score *= 0.3 # Reduce index listing weight

            if score > 0.5:
                # Select best passage/snippet for this page
                if not highlighted_passages:
                    # Pick sentence with most query words
                    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', full_page_text) if len(s.strip()) > 20]
                    best_s = ""
                    best_c = 0
                    for s in sentences:
                        c = sum(1 for w in query_words if w in s.lower())
                        if c > best_c:
                            best_c = c
                            best_s = s
                    if best_s:
                        highlighted_passages.append(best_s)
                    else:
                        highlighted_passages.append(full_page_text[:350] + "...")

                # Clean passages
                main_snippet = " ".join(highlighted_passages[:3])
                if len(main_snippet) > 600:
                    main_snippet = main_snippet[:600] + "..."

                scored_pages.append({
                    "document": doc,
                    "page": page,
                    "score": round(score, 3),
                    "text": main_snippet,
                    "full_text": full_page_text,
                    "is_definition": is_definition_hit,
                    "status": "RETRIEVED"
                })

        # Sort by score descending
        scored_pages.sort(key=lambda x: x["score"], reverse=True)
        top_pages = scored_pages[:max_pages]

        return top_pages

retrieval_service = RetrievalService(doc_store)
