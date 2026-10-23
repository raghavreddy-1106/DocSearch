"""
Hybrid RAG Engine — Semantic + Keyword Retrieval + Ollama Generation
---------------------------------------------------------------------
Implements a complete Retrieval-Augmented Generation pipeline:

1. Semantic search  → query embedding via Ollama nomic-embed-text
                      cosine similarity against stored chunk embeddings
2. Keyword search   → BM25-style TF scoring + exact phrase matching
3. Hybrid fusion    → reciprocal rank fusion (RRF) to merge results
4. Evidence validation → check relevance before sending to LLM
5. Ollama generation → qwen2.5:3b (or configured model) with PDF context

No hardcoded document-specific rules. Works on any PDF.
"""
import re
import math
import time
from typing import List, Dict, Any, Optional

from app.services.document_store import doc_store
from app.services.vector_store import vector_store
from app.services.ollama_service import ollama_service


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

STOPWORDS = {
    "what", "is", "the", "a", "an", "are", "in", "of", "for", "to",
    "how", "why", "does", "do", "explain", "define", "tell", "me", "about",
    "this", "document", "mean", "meaning", "use", "used", "way", "can",
    "could", "would", "should", "will", "may", "might", "with", "from",
    "by", "on", "at", "that", "which", "it", "its", "my", "their", "our",
    "has", "have", "had", "been", "was", "were", "be", "if", "then",
    "get", "got", "need", "want", "find", "show", "give", "many", "much",
    "all", "any", "some", "no", "not", "or", "and", "but",
}

MIN_SEMANTIC_SCORE = 0.18   # Lower = more recall, fewer false negatives
MIN_KEYWORD_SCORE = 0.5     # Minimum BM25-like score to include
RRF_K = 60                  # Reciprocal rank fusion constant
MAX_PASSAGES = 8            # Max passages sent to LLM (increased for list/table questions)


# ─────────────────────────────────────────────────────────────────────────────
# Query parsing
# ─────────────────────────────────────────────────────────────────────────────

def extract_query_terms(query: str) -> List[str]:
    """Extract meaningful non-stopword terms from query."""
    q = query.strip().lower()
    q = re.sub(r"[?.!,;:\"']", " ", q)
    words = re.findall(r"[\w\-]+", q)
    terms = [w for w in words if w not in STOPWORDS and len(w) > 1]
    if not terms:
        terms = [w for w in words if len(w) > 2]
    return terms


# ─────────────────────────────────────────────────────────────────────────────
# Keyword / BM25-style search over in-memory chunks
# ─────────────────────────────────────────────────────────────────────────────

def keyword_search(
    query: str,
    user_email: str,
    document_names: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    top_k: int = 12,
) -> List[Dict[str, Any]]:
    """
    BM25-style keyword search over all chunks belonging to the user.
    Groups matches by (document, page) and scores by term frequency.
    Returns results ranked by relevance score.
    """
    terms = extract_query_terms(query)
    if not terms:
        return []

    email_clean = (user_email or "").strip().lower()

    # Aggregate chunks by page
    page_groups: Dict[tuple, Dict] = {}

    for chunk in doc_store.chunks:
        chunk_email = (chunk.get("user_email") or "").strip().lower()
        if email_clean and chunk_email != email_clean:
            continue
        if not email_clean:
            continue

        doc = chunk.get("filename", "")
        if document_names and doc not in document_names:
            continue

        page = chunk.get("page_number", 0)
        key = (doc, page)
        text = chunk.get("text", "")

        if key not in page_groups:
            page_groups[key] = {"doc": doc, "page": page, "texts": [], "full_text": ""}
        page_groups[key]["texts"].append(text)

    # Score each page
    results = []
    for (doc, page), group in page_groups.items():
        full_text = " ".join(group["texts"])
        text_lower = full_text.lower()
        words = re.findall(r"[\w\-]+", text_lower)
        word_count = len(words) + 1

        # TF score with length normalization (BM25-inspired)
        score = 0.0
        matched_terms = []
        for term in terms:
            tf = text_lower.count(term)
            if tf > 0:
                # BM25-like: tf / (tf + k1*(1 - b + b*(len/avg_len)))
                # Using simpler approximation here
                normalized_tf = tf / (1 + math.log(word_count))
                score += normalized_tf
                matched_terms.append(term)

        # Bonus for exact phrase match
        phrase = query.lower().strip()
        if len(terms) > 1 and phrase in text_lower:
            score += 5.0

        # Bonus for matching many terms
        if len(matched_terms) > 0:
            coverage = len(matched_terms) / len(terms)
            score *= (0.5 + coverage)

        if score >= MIN_KEYWORD_SCORE and matched_terms:
            # Extract best snippet
            best_snippet = full_text[:600]
            for term in matched_terms:
                idx = text_lower.find(term)
                if idx != -1:
                    start = max(0, idx - 150)
                    end = min(len(full_text), idx + 400)
                    best_snippet = full_text[start:end].strip()
                    break

            results.append({
                "document": doc,
                "page": page,
                "text": best_snippet,
                "full_text": full_text,
                "score": score,
                "matched_terms": matched_terms,
                "retrieval_type": "keyword",
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# Reciprocal Rank Fusion
# ─────────────────────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    semantic_results: List[Dict],
    keyword_results: List[Dict],
    k: int = RRF_K,
    semantic_weight: float = 1.0,
    keyword_weight: float = 1.0,
) -> List[Dict]:
    """
    Merge semantic and keyword results using Reciprocal Rank Fusion.
    Higher weight = more influence on final ranking.
    """
    scores: Dict[tuple, float] = {}
    result_map: Dict[tuple, Dict] = {}

    for rank, r in enumerate(semantic_results):
        key = (r["document"], r["page"])
        rrf_score = semantic_weight / (k + rank + 1)
        scores[key] = scores.get(key, 0.0) + rrf_score
        if key not in result_map:
            result_map[key] = dict(r)
        result_map[key]["semantic_score"] = r.get("score", 0)

    for rank, r in enumerate(keyword_results):
        key = (r["document"], r["page"])
        rrf_score = keyword_weight / (k + rank + 1)
        scores[key] = scores.get(key, 0.0) + rrf_score
        if key not in result_map:
            result_map[key] = dict(r)
        result_map[key]["keyword_score"] = r.get("score", 0)

    merged = []
    for key, rrf_score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        item = result_map[key]
        item["rrf_score"] = rrf_score
        item["score"] = rrf_score  # unified score for downstream
        merged.append(item)

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Evidence validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_evidence(
    passages: List[Dict],
    query: str,
    min_passages: int = 1,
) -> Dict[str, Any]:
    """
    Validate that retrieved passages are relevant before sending to LLM.
    Returns validation result and filtered passages.
    """
    if not passages:
        return {
            "valid": False,
            "reason": "No passages retrieved from the document.",
            "passages": []
        }

    terms = extract_query_terms(query)
    # Check that at least some passages have keyword overlap or semantic score
    useful = []
    for p in passages:
        text_lower = p.get("text", "").lower()
        keyword_hit = any(t in text_lower for t in terms)
        semantic_score = p.get("semantic_score", 0) or 0
        rrf_score = p.get("rrf_score", 0) or p.get("score", 0)

        if keyword_hit or semantic_score > 0.25 or rrf_score > 0.005:
            useful.append(p)

    if not useful:
        return {
            "valid": False,
            "reason": "Retrieved passages do not appear relevant to the query.",
            "passages": passages[:2]  # Return top 2 anyway for diagnostics
        }

    return {
        "valid": True,
        "reason": f"Found {len(useful)} relevant passage(s)",
        "passages": useful
    }


from app.services.query_understanding import query_understanding, QueryPlan
from app.services.evidence_validator import evidence_validator


def document_aware_rerank(
    candidates: List[Dict[str, Any]],
    query_plan: QueryPlan,
    top_k: int = MAX_PASSAGES,
) -> List[Dict[str, Any]]:
    """
    Reranks candidate passages based on document-aware intent alignment:
    - Target entity alignment: boost passages containing the exact entity or resolved term.
    - Quantitative assertion alignment: if asking for numeric_quantity (e.g. credits, hours, count),
      boost passages that contain tabular structure or structured row with the target entity.
    - Prevents general degree totals or honors totals from outranking a requested component category.
    """
    if not candidates:
        return []

    target_entity = (query_plan.resolved_entity or query_plan.target_entity or "").strip()
    orig_q = (query_plan.original_query or "").lower()
    is_numeric = query_plan.information_type == "numeric_quantity" or bool(re.search(r"\b(how many|how much|credits?|total|units?|percentage|score|marks)\b", orig_q, re.I))
    is_list = query_plan.information_type in ("list", "components", "courses", "subjects") or bool(re.search(r"\b(courses?|subjects?|components?|list|electives?|modules?|curriculum|topics?)\b", orig_q, re.I))

    # Clean target entity from question boilerplate
    clean_target = re.sub(r"\b(what\s+(is|are)|courses?\s+(under|in|of)|subjects?\s+(under|in|of)|list\s+(of)?|components?\s+(in|of)|tell\s+me\s+about)\b", "", target_entity, flags=re.I).strip("? .")
    norm_target = clean_target.lower().replace("honours", "honor").replace("honors", "honor").replace("programme", "program")
    target_words = [w for w in norm_target.split() if len(w) > 2]

    reranked = []
    for item in candidates:
        score = item.get("rrf_score", item.get("score", 0.0))
        text = item.get("text", "")
        text_lower = text.lower().replace("honours", "honor").replace("honors", "honor").replace("programme", "program")

        # Check entity presence
        has_exact_entity = bool(norm_target and norm_target in text_lower)
        has_partial_entity = bool(target_words and any(w in text_lower for w in target_words))

        if has_exact_entity:
            score += 0.06
        elif has_partial_entity:
            score += 0.02

        has_table = "|" in text
        has_multi_course_table = bool(re.search(r"\|\s*(?:course\s*name|course\s*code|s\.no)\s*\|", text, re.I))

        # Prioritize master catalog/table when asking for lists of courses or subjects
        if is_list:
            if has_multi_course_table and (has_exact_entity or has_partial_entity):
                score += 0.22  # Master course catalog / table gets massive boost!
            elif has_table and (has_exact_entity or has_partial_entity):
                score += 0.12
            # Downweight single-course syllabus detail pages when asking for a catalog/list of courses
            if "course objectives:" in text_lower and not has_multi_course_table:
                score *= 0.55

        if is_numeric:
            table_row_match = False
            for line in text.split("\n"):
                line_lower = line.lower().replace("honours", "honor").replace("honors", "honor")
                is_row = "|" in line or line.strip().startswith(("*", "-", "•")) or "credits is required" in line_lower or "total credits" in line_lower
                if is_row and ((has_exact_entity and norm_target in line_lower) or (has_partial_entity and any(w in line_lower for w in target_words))):
                    table_row_match = True
                    break

            if table_row_match:
                score += 0.12  # High boost for direct tabular evidence!
            elif has_exact_entity and re.search(r"\b\d+\b", text):
                score += 0.04

            # Downweight unrelated broad totals if the user asked about a specific component
            if not has_exact_entity and not has_partial_entity:
                if re.search(r"\b(grand total|overall total|cumulative total|degree total|programme total)\b", text_lower):
                    score *= 0.7

        item_copy = dict(item)
        item_copy["rerank_score"] = score
        item_copy["score"] = score
        reranked.append(item_copy)

    reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    return reranked[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# Full page text retrieval (for context enrichment)
# ─────────────────────────────────────────────────────────────────────────────

def enrich_with_full_page(
    passages: List[Dict],
    user_email: str,
) -> List[Dict]:
    """Replace truncated chunk text with full page text for better context."""
    enriched = []
    seen = set()

    for p in passages:
        doc = p["document"]
        page = p["page"]
        key = (doc, page)

        if key in seen:
            continue
        seen.add(key)

        # Get full page text from doc store
        full_text = doc_store.get_page_text(doc, page, user_email=user_email)
        if full_text and len(full_text) > len(p.get("text", "")):
            p = dict(p)
            p["text"] = full_text[:3500]  # Cap at 3500 chars to preserve complete tables and list sections
        enriched.append(p)

    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# Main Hybrid RAG Engine
# ─────────────────────────────────────────────────────────────────────────────

class HybridRAGEngine:
    """
    Complete RAG pipeline:
    1. Document-aware query understanding (entity extraction, acronym resolution)
    2. Multi-query semantic + keyword retrieval
    3. RRF fusion + document-aware reranking
    4. Evidence validation
    5. Context enrichment with layout-aware Markdown tables
    6. Ollama generation with strict numeric attribution
    7. Dynamic post-generation evidence verification & correction
    """

    def retrieve(
        self,
        query: str,
        user_email: str,
        document_names: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        top_k: int = MAX_PASSAGES,
    ) -> Dict[str, Any]:
        """
        Retrieve relevant passages using hybrid search with query understanding and reranking.
        """
        t0 = time.time()

        # ── 1. Document-aware Query Understanding ─────────────────────────────
        query_plan = query_understanding.analyze_query(
            query=query,
            user_email=user_email,
            document_names=document_names,
        )

        search_queries = query_plan.search_queries
        print(f"[RAG] Search queries: {search_queries} | Target: '{query_plan.target_entity}'")

        # ── 2. Semantic search (across query variations) ──────────────────────
        semantic_results = []
        semantic_available = False

        # Always initialise accumulator dicts so keyword loop can reference them
        # even when Ollama / semantic search is unavailable.
        scores: Dict[tuple, float] = {}
        result_map: Dict[tuple, Dict] = {}
        semantic_count = 0

        ollama_health = ollama_service.health()
        if ollama_health["running"] and ollama_health.get("embed_model_available"):
            # Auto-index target documents if not already indexed
            target_docs = document_names if document_names else [
                d.get("filename") for d in doc_store.list_documents(user_email=user_email)
            ]
            for doc_name in target_docs:
                if doc_name and not vector_store.is_indexed(user_email, doc_name):
                    doc_chunks = [
                        c for c in doc_store.chunks
                        if c.get("filename") == doc_name
                        and (c.get("user_email") or "").lower() == (user_email or "").lower()
                    ]
                    if doc_chunks:
                        try:
                            print(f"[RAG] Auto-indexing {doc_name} for {user_email}...")
                            embs = ollama_service.embed_batch([c.get("text", "") for c in doc_chunks])
                            vector_store.save_document_embeddings(user_email, doc_name, doc_chunks, embs)
                        except Exception as e:
                            print(f"[RAG] Auto-indexing failed for {doc_name}: {e}")

            # ── 2. Semantic search (accumulating RRF across query variations) ─
            for q_idx, sq in enumerate(search_queries[:3]):
                query_emb = ollama_service.embed(sq)
                if query_emb:
                    semantic_available = True
                    sq_res = vector_store.semantic_search(
                        query_embedding=query_emb,
                        user_email=user_email,
                        document_names=document_names,
                        top_k=top_k * 2,
                        min_score=MIN_SEMANTIC_SCORE,
                    )
                    semantic_count += len(sq_res)
                    for rank, r in enumerate(sq_res):
                        key = (r["document"], r["page"])
                        scores[key] = scores.get(key, 0.0) + (1.0 / (RRF_K + rank + 1))
                        if key not in result_map:
                            result_map[key] = dict(r)
                        result_map[key]["semantic_score"] = max(result_map[key].get("semantic_score", 0), r.get("score", 0))

            print(f"[RAG] Semantic: {semantic_count} hits across {len(search_queries)} queries")

        # ── 3. Keyword search (accumulating RRF across query variations) ───────
        keyword_count = 0
        for q_idx, sq in enumerate(search_queries[:3]):
            sq_kw = keyword_search(
                query=sq,
                user_email=user_email,
                document_names=document_names,
                user_id=user_id,
                top_k=top_k * 2,
            )
            keyword_count += len(sq_kw)
            for rank, r in enumerate(sq_kw):
                key = (r["document"], r["page"])
                scores[key] = scores.get(key, 0.0) + (1.0 / (RRF_K + rank + 1))
                if key not in result_map:
                    result_map[key] = dict(r)
                result_map[key]["keyword_score"] = max(result_map[key].get("keyword_score", 0), r.get("score", 0))

        print(f"[RAG] Keyword: {keyword_count} hits across {len(search_queries)} queries")

        # ── 4. Reciprocal Rank Fusion List ────────────────────────────────────
        fused = []

        for key, rrf_sc in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            item = result_map[key]
            item["rrf_score"] = rrf_sc
            item["score"] = rrf_sc
            fused.append(item)

        # ── 5. Enrich candidates with full page layout text (preserves tables) ─
        enriched_candidates = enrich_with_full_page(fused[:top_k * 3], user_email=user_email)

        # ── 6. Document-Aware Reranking ───────────────────────────────────────
        reranked = document_aware_rerank(enriched_candidates, query_plan, top_k=top_k)

        elapsed = round(time.time() - t0, 3)
        print(f"[RAG] Retrieved and reranked {len(reranked)} passages in {elapsed}s")

        return {
            "passages": reranked,
            "semantic_available": semantic_available,
            "semantic_count": semantic_count,
            "keyword_count": keyword_count,
            "retrieval_time_s": elapsed,
            "query_plan": query_plan.to_dict(),
        }

    def generate(
        self,
        query: str,
        user_email: str,
        document_names: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full pipeline: query understanding + retrieve + rerank + generate + validate.
        """
        # Retrieve
        retrieval = self.retrieve(
            query=query,
            user_email=user_email,
            document_names=document_names,
            user_id=user_id,
        )
        passages = retrieval["passages"]
        plan_dict = retrieval.get("query_plan", {})

        # Validate evidence sufficiency
        validation = validate_evidence(passages, query)
        if not validation["valid"]:
            return {
                "answer": (
                    f"I searched your document(s) but could not find relevant information about: **\"{query}\"**.\n\n"
                    f"Reason: {validation['reason']}\n\n"
                    "Try rephrasing your question or ensure the document contains this information."
                ),
                "status": "NO_EVIDENCE",
                "confidence": "INSUFFICIENT",
                "evidence": [],
                "citations": [],
                "retrieval_info": retrieval,
            }

        best_passages = validation["passages"][:MAX_PASSAGES]

        # Check Ollama availability before attempting generation
        ollama_health = ollama_service.health()
        if not ollama_health["running"]:
            return {
                "answer": "",
                "status": "OLLAMA_UNAVAILABLE",
                "error": "Ollama is not running.",
                "hint": "Start Ollama: ollama serve",
                "confidence": "NONE",
                "evidence": [{"document": p["document"], "page": p["page"], "text": p["text"][:200], "status": "RETRIEVED", "score": p.get("score", 0)} for p in best_passages],
                "citations": [{"document": p["document"], "page": p["page"]} for p in best_passages],
                "retrieval_info": retrieval,
            }

        if not ollama_health.get("chat_model_available"):
            chat_model = ollama_health.get("chat_model", "qwen2.5:3b")
            return {
                "answer": "",
                "status": "MODEL_UNAVAILABLE",
                "error": f"Chat model '{chat_model}' is not loaded.",
                "hint": f"Run: ollama pull {chat_model}",
                "confidence": "NONE",
                "evidence": [{"document": p["document"], "page": p["page"], "text": p["text"][:200], "status": "RETRIEVED", "score": p.get("score", 0)} for p in best_passages],
                "citations": [{"document": p["document"], "page": p["page"]} for p in best_passages],
                "retrieval_info": retrieval,
            }

        # Generate with Ollama
        target_entity = plan_dict.get("target_entity")
        expanded_query = plan_dict.get("expanded_query")
        gen_result = ollama_service.answer(
            query=query,
            passages=best_passages,
            target_entity=target_entity,
            expanded_query=expanded_query,
            model=model,
            information_type=plan_dict.get("information_type", "general"),
        )

        raw_answer = gen_result.get("answer", "")

        # Dynamic Evidence Validation & Refinement
        # Only run the expensive LLM-based validator for numeric/list questions where
        # misattribution is most likely — skip it for general/explanation queries to reduce latency.
        info_type = plan_dict.get("information_type", "general")
        _needs_validation = info_type in ("numeric_quantity", "list")
        if _needs_validation:
            val_result = evidence_validator.validate_and_refine(
                query=query,
                answer=raw_answer,
                passages=best_passages,
                target_entity=target_entity,
                information_type=info_type,
                resolved_entity=plan_dict.get("resolved_entity"),
            )
        else:
            val_result = {
                "validated_answer": raw_answer,
                "is_corrected": False,
                "validation_status": "SKIPPED_NON_NUMERIC",
            }

        final_answer = val_result.get("validated_answer", raw_answer)

        # Distinguish evidence tiers: RETRIEVED (candidate), SUPPORTING (relevant entity/fact), VERIFIED (validated citation)
        from app.services.search_service import search_service
        exact_res = search_service.search_exact(
            query=query,
            document_names=document_names,
            user_email=user_email,
            user_id=user_id,
        )

        seen_citations = set((c.get("document"), c.get("page")) for c in gen_result.get("citations", []))

        evidence = []
        for p in best_passages:
            doc = p.get("document", "")
            page = p.get("page", 1)
            is_cited = (doc, page) in seen_citations
            has_target = bool(target_entity and target_entity.lower() in p.get("text", "").lower())

            if is_cited and doc_store.get_page_text(doc, page, user_email=user_email):
                ev_status = "VERIFIED"
            elif has_target or p.get("score", 0) > 0.15:
                ev_status = "SUPPORTING"
            else:
                ev_status = "RETRIEVED"

            evidence.append({
                "document": doc,
                "page": page,
                "text": p.get("text", "")[:350],
                "status": ev_status,
                "score": round(p.get("score", 0), 4),
            })

        # Ensure verified citations have real page verification in doc_store
        verified_citations = [
            {"document": c.get("document"), "page": c.get("page"), "score": c.get("score", 0)}
            for c in gen_result.get("citations", [])
            if doc_store.get_page_text(c.get("document"), c.get("page"), user_email=user_email)
        ]

        # Build unified search results: exact matches if present, or semantic matched pages from hybrid search
        if exact_res and exact_res.get("total_pages", 0) > 0:
            unified_search_results = exact_res
        else:
            sem_page_dict = {}
            for p in best_passages:
                doc = p.get("document", "")
                page = p.get("page", 1)
                key = (doc, page)
                if key not in sem_page_dict:
                    sem_page_dict[key] = {
                        "document": doc,
                        "page": page,
                        "match_count": 1,
                        "snippets": [p.get("text", "")[:250].strip() + ("..." if len(p.get("text", "")) > 250 else "")]
                    }
            sem_results = list(sem_page_dict.values())
            unified_search_results = {
                "query": query,
                "mode": "semantic_match" if sem_results else "no_matches",
                "total_pages": len(sem_results),
                "total_matches": len(sem_results),
                "results": sem_results,
                "related_results": exact_res.get("related_results", []) if exact_res else []
            }

        ans_lower = final_answer.lower()
        is_abstention = any(p in ans_lower for p in [
            "do not contain any information", "does not contain any information",
            "no relevant information", "not mentioned in the", "could not find",
            "cannot be determined from the provided", "no information available"
        ])

        if is_abstention:
            final_status = "ABSTAINED"
            confidence = "INSUFFICIENT"
        elif gen_result["status"] == "SUCCESS" or val_result.get("is_corrected"):
            final_status = "SUCCESS"
            confidence = "HIGH" if len(best_passages) >= 2 else "MEDIUM"
        else:
            final_status = gen_result["status"]
            confidence = "NONE"

        return {
            "answer": final_answer,
            "status": final_status,
            "confidence": confidence,
            "model_used": gen_result.get("model_used", "ollama"),
            "evidence": evidence,
            "citations": verified_citations,
            "search_results": unified_search_results,
            "latency_s": gen_result.get("latency_s", 0),
            "retrieval_info": retrieval,
            "validation": val_result,
            "error": gen_result.get("error") if final_status != "SUCCESS" and not is_abstention else None,
            "hint": gen_result.get("hint") if final_status != "SUCCESS" and not is_abstention else None,
        }


hybrid_rag = HybridRAGEngine()
