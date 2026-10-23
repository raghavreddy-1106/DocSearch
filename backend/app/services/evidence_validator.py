"""
Evidence Validator Service
--------------------------
Performs dynamic validation on generated LLM answers against retrieved evidence passages:
1. Verifies that the answer addresses the specific entity/category requested in the user query.
2. Validates numeric attribution: checks whether numbers cited in the answer belong to the
   requested category or were mistakenly taken from a neighboring row, footnote, or overall total.
3. Detects if an overall programme total (e.g. total degree credits, honors credits) was
   substituted for a specific component requirement (e.g. elective credits).
4. If a misattribution or category confusion is detected, runs a targeted correction step
   using the retrieved evidence tables to ensure accurate, grounded output.
"""
import re
import json
import urllib.request
from typing import List, Dict, Any, Optional

from app.services.ollama_service import get_ollama_config


class EvidenceValidator:
    """
    Validates and corrects LLM responses against retrieved evidence passages.
    """

    def validate_and_refine(
        self,
        query: str,
        answer: str,
        passages: List[Dict[str, Any]],
        target_entity: Optional[str] = None,
        information_type: str = "general",
        resolved_entity: Optional[str] = None,
        timeout: int = 25,
    ) -> Dict[str, Any]:
        """
        Validate the generated answer against the retrieved evidence passages.
        Returns dict with:
          - validated_answer: str
          - is_corrected: bool
          - validation_status: str ("VERIFIED" | "CORRECTED" | "UNVERIFIED")
          - notes: Optional[str]
        """
        if not answer or not passages:
            return {
                "validated_answer": answer,
                "is_corrected": False,
                "validation_status": "UNVERIFIED",
                "notes": "No answer or passages to validate."
            }

        effective_entity = resolved_entity or target_entity
        is_numeric = information_type == "numeric_quantity" or bool(
            re.search(r"\b(how many|how much|credits?|total\s+credits?|units?|percentage|score|marks)\b", query, re.I)
        )
        is_list = not is_numeric and (
            information_type in ("list", "components", "courses", "subjects") or bool(
                re.search(r"\b(what\s+are\s+(?:the\s+)?(?:courses?|subjects?|components?|electives?)|list\s+(?:the\s+)?(?:courses?|subjects?)|which\s+courses?)\b", query, re.I)
            )
        )

        # ── 1.0 Check for Course / Subject List Completeness ───────────────────
        if is_list and passages:
            clean_ent = (effective_entity or "").lower()
            norm_ent = clean_ent.replace("honours", "honor").replace("honors", "honor").replace("programme", "program")
            ent_words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", norm_ent) if w not in {"what", "are", "the", "courses", "subjects", "under", "for", "list"}]

            for p in passages[:3]:
                p_text = p.get("text", "")
                p_text_lower = p_text.lower().replace("honours", "honor").replace("honors", "honor").replace("programme", "program")
                p_doc = p.get("document", "the document")
                p_page = p.get("page", 1)

                # Ensure this table belongs to the requested entity/category
                cat_match = not ent_words or norm_ent in p_text_lower or any(w in p_text_lower for w in ent_words)

                if cat_match and bool(re.search(r"\|\s*(?:course\s*name|course\s*code|s\.no)\s*\|", p_text, re.I)):
                    table_rows = []
                    for line in p_text.splitlines():
                        m = re.match(r"\|\s*(\d+)\s*\|\s*([A-Za-z0-9]+)\s*\|\s*([^|]+)\|", line)
                        if m:
                            table_rows.append({
                                "sno": m.group(1).strip(),
                                "code": m.group(2).strip(),
                                "name": m.group(3).strip(),
                            })

                    if len(table_rows) >= 3:
                        ans_lower = answer.lower()
                        missing = [r for r in table_rows if r["code"].lower() not in ans_lower and r["name"].lower() not in ans_lower]
                        if missing:
                            print(f"[EvidenceValidator] Detected {len(missing)} missing items from course table! Formatting complete list.")
                            cat_title = effective_entity or "the requested category"
                            items_str = "\n".join([f"- **{r['code']}**: {r['name']}" for r in table_rows])
                            corrected = (
                                f"The courses under {cat_title} (Page {p_page}) are:\n\n"
                                f"{items_str}\n\n"
                                f"Source: [{p_doc}, Page {p_page}]"
                            )
                            return {
                                "validated_answer": corrected,
                                "is_corrected": True,
                                "validation_status": "CORRECTED",
                                "notes": f"Restored {len(missing)} missing courses from Page {p_page} master table",
                            }

        # ── 1. Programmatic Check for Category Misattribution ─────────────────
        # Extract numbers from the answer
        nums_in_answer = re.findall(r"\b\d+(?:\.\d+)?\b", answer)

        # Look for table rows in passages matching effective_entity
        entity_table_row_num = None
        broader_total_num = None
        if effective_entity and len(effective_entity) > 2:
            entity_clean = effective_entity.lower().strip()
            # Remove generic question and grammar stopwords to isolate true entity terms
            stopwords = {"what", "how", "many", "much", "total", "the", "are", "for", "complete", "earn", "i", "want", "to", "requirement", "component", "find", "show", "give", "tell", "need", "does", "is", "a", "an"}
            # Normalize British/American spellings dynamically
            normalized_entity = entity_clean.replace("honours", "honor").replace("honors", "honor").replace("programme", "program")
            entity_words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", normalized_entity) if w not in stopwords]

            for p in passages:
                text = p.get("text", "")
                for line in text.split("\n"):
                    line_lower = line.lower().replace("honours", "honor").replace("honors", "honor").replace("programme", "program")
                    # Check both markdown tables and structured footnotes/bullet lines
                    is_structured = "|" in line or line.strip().startswith(("*", "-", "•")) or "credits is required" in line_lower or "total credits" in line_lower
                    if is_structured:
                        is_match = False
                        if entity_clean in line_lower or normalized_entity in line_lower:
                            is_match = True
                        elif entity_words and all(w in line_lower for w in entity_words):
                            is_match = True

                        if is_match and not entity_table_row_num:
                            row_nums = re.findall(r"\b\d+\b", line)
                            if row_nums:
                                entity_table_row_num = row_nums[-1]

                    if re.search(r"\b(grand total|overall total|cumulative total|degree total|programme total)\b", line_lower):
                        tot_nums = re.findall(r"\b\d+\b", line)
                        if tot_nums and not broader_total_num:
                            broader_total_num = tot_nums[-1]

        # If user asked about a specific sub-category (like Program Elective), but answer reported the broader total (like 180 or 160)
        potential_misattribution = False
        if is_numeric and entity_table_row_num and nums_in_answer:
            if entity_table_row_num not in nums_in_answer:
                potential_misattribution = True
                print(f"[EvidenceValidator] Detected potential misattribution: expected entity num {entity_table_row_num}, but answer contains {nums_in_answer}")

        # Fast path verification: if answer already matches the verified table row number, mark verified
        if is_numeric and entity_table_row_num and (entity_table_row_num in nums_in_answer):
            print(f"[EvidenceValidator] Verified: answer contains matching table number {entity_table_row_num} for {effective_entity}")
            return {
                "validated_answer": answer,
                "is_corrected": False,
                "validation_status": "VERIFIED",
                "notes": f"Verified against table row: {entity_table_row_num}",
            }

        # If no misattribution suspected and not numeric, return as verified
        if not potential_misattribution and not is_numeric:
            return {
                "validated_answer": answer,
                "is_corrected": False,
                "validation_status": "VERIFIED",
            }

        # ── 2. LLM-Based Evidence Validation & Verification ──────────────────
        cfg = get_ollama_config()
        base_url = cfg["base_url"]
        model = cfg["chat_model"]

        # Format compact passages for verification
        passage_excerpts = []
        for p in passages[:4]:
            doc = p.get("document", "Doc")
            page = p.get("page", "?")
            passage_excerpts.append(f"[{doc} - Page {page}]\n{p.get('text', '')[:700]}")
        evidence_str = "\n\n---\n\n".join(passage_excerpts)

        val_prompt = (
            "You are a strict evidence verification and numeric attribution engine.\n"
            "Review the user's question, the candidate answer, and the retrieved document evidence.\n\n"
            f"USER QUESTION: {query}\n"
            f"REQUESTED ENTITY / CATEGORY: {effective_entity or 'Unspecified'}\n"
            f"CANDIDATE ANSWER:\n{answer}\n\n"
            f"DOCUMENT EVIDENCE:\n{evidence_str}\n\n"
            "VERIFICATION INSTRUCTIONS:\n"
            "1. Did the candidate answer address the EXACT entity/category asked by the user, or did it confuse it with an overall degree total, honors total, or neighboring row?\n"
            "2. If the candidate answer is 100% accurate and correctly attributes numbers to the requested entity: return JSON with 'is_valid': true, 'corrected_answer': null.\n"
            "3. If the candidate answer is inaccurate, confused the category, or used the wrong number: return JSON with 'is_valid': false, 'corrected_answer': '<direct, accurate answer with correct number and source page cited>'.\n\n"
            "Output JSON only: {\"is_valid\": boolean, \"reason\": string, \"corrected_answer\": string | null}"
        )

        try:
            payload = json.dumps({
                "model": model,
                "prompt": val_prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 400,
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
                val_json = json.loads(resp_data.get("response", "{}"))

            is_valid = val_json.get("is_valid", True)
            corrected_answer = val_json.get("corrected_answer")
            reason = val_json.get("reason", "")

            if not is_valid and corrected_answer and len(corrected_answer.strip()) > 10:
                # Grounding check: every number in the proposed correction MUST exist in the retrieved document evidence
                corr_nums = re.findall(r"\b\d+\b", corrected_answer)
                all_evidence_text = " ".join(p.get("text", "") for p in passages)
                corr_grounded = all(n in all_evidence_text for n in corr_nums)

                if corr_grounded:
                    print(f"[EvidenceValidator] Answer corrected by validator. Reason: {reason}")
                    return {
                        "validated_answer": corrected_answer.strip(),
                        "is_corrected": True,
                        "validation_status": "CORRECTED",
                        "notes": reason,
                    }
                else:
                    print(f"[EvidenceValidator] Rejected ungrounded validator correction (contains {corr_nums} not in evidence). Preserving grounded candidate answer.")

            if potential_misattribution and entity_table_row_num:
                return self._programmatic_correction(
                    query, answer, passages, effective_entity, entity_table_row_num
                )

            return {
                "validated_answer": answer,
                "is_corrected": False,
                "validation_status": "VERIFIED",
                "notes": reason,
            }

        except Exception as e:
            print(f"[EvidenceValidator] Validation check notice: {e}")
            if entity_table_row_num and potential_misattribution:
                return self._programmatic_correction(
                    query, answer, passages, effective_entity, entity_table_row_num
                )

            return {
                "validated_answer": answer,
                "is_corrected": False,
                "validation_status": "UNVERIFIED",
            }

    def _programmatic_correction(
        self,
        query: str,
        original_answer: str,
        passages: List[Dict[str, Any]],
        effective_entity: Optional[str],
        entity_table_row_num: str,
    ) -> Dict[str, Any]:
        p_page = passages[0].get("page", 1) if passages else 1
        p_doc = passages[0].get("document", "the document") if passages else "the document"
        for p in passages:
            if entity_table_row_num in p.get("text", "") and (effective_entity or "").lower() in p.get("text", "").lower():
                p_page = p.get("page", p_page)
                p_doc = p.get("document", p_doc)
                break

        metric_match = re.search(r"\b(credits?|hours?|units?|points?|marks?|percent(?:age)?|\$|usd|inr|eur)\b", query, re.I)
        metric_str = f" {metric_match.group(0)}" if metric_match else ""
        corrected = (
            f"Based on {p_doc} (Page {p_page}), {effective_entity or 'the requested component'} "
            f"requires {entity_table_row_num}{metric_str}.\n\n"
            f"Source: [{p_doc}, page {p_page}]"
        )
        print(f"[EvidenceValidator] Programmatic table-grounded correction applied: {entity_table_row_num} for {effective_entity}")
        return {
            "validated_answer": corrected,
            "is_corrected": True,
            "validation_status": "CORRECTED",
            "notes": f"Programmatic correction from verified table row ({entity_table_row_num})",
        }


evidence_validator = EvidenceValidator()
