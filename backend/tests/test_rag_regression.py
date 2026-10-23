"""
Comprehensive Test Suite for DocSearch Document Intelligence.
Validates:
1. Dynamic PDF parsing and Markdown table extraction.
2. Dynamic query understanding and abbreviation resolution.
3. Category-specific credit reasoning (Program Elective = 24, Program Core = 52, Honours = 180).
4. List extraction (Foundation Core components).
5. Abstention when evidence is absent (no hallucination).
6. Search count and page consistency (exact vs semantic).
7. User isolation across documents.
8. Evaluation metrics calculation integrity.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.services.hybrid_rag import hybrid_rag
from app.services.query_understanding import query_understanding
from app.services.document_store import doc_store
from app.services.search_service import search_service
from app.services.history_store import history_store
from app.api.endpoints.history import get_evaluation_metrics

USER_EMAIL = "raghavareddy11012005@gmail.com"
TEST_DOC = "CSE CURRICULUM AND SYLLABUS 2021.pdf"


def test_table_structure_extracted():
    """Verify Page 9 contains structured Markdown table with exact row association."""
    page_text = doc_store.get_page_text(TEST_DOC, 9, user_email=USER_EMAIL)
    assert page_text, "Page 9 text must be present in doc_store"
    assert "|" in page_text, "Page 9 must contain markdown table formatting"
    assert "Program Elective" in page_text, "Page 9 must contain 'Program Elective'"
    assert "24" in page_text, "Page 9 must contain '24'"
    matching_rows = [line for line in page_text.splitlines() if "Program Elective" in line and "|" in line]
    assert len(matching_rows) > 0, "Must have a table row containing 'Program Elective'"
    assert "24" in matching_rows[0], f"Table row for Program Elective must associate with 24 credits: {matching_rows[0]}"


def test_dynamic_query_understanding_acronym_resolution():
    """Verify PE is dynamically resolved to 'Program Elective' from document context without hardcoding."""
    plan = query_understanding.analyze_query(
        query="how many credits i want to earn to complete PE course",
        user_email=USER_EMAIL,
        document_names=[TEST_DOC],
    )
    assert plan.resolved_entity is not None, "PE should be resolved from document context"
    assert "program elective" in plan.resolved_entity.lower(), f"Expected 'Program Elective', got: {plan.resolved_entity}"
    assert plan.information_type == "numeric_quantity", f"Expected 'numeric_quantity', got: {plan.information_type}"


def test_pe_credits_retrieval_and_answer():
    """Verify that 'how many credits i want to earn to complete PE course' answers 24 and cites Page 9."""
    res = hybrid_rag.generate(
        query="how many credits i want to earn to complete PE course",
        user_email=USER_EMAIL,
        document_names=[TEST_DOC],
    )
    assert res["status"] == "SUCCESS", f"Generation failed: {res}"
    answer = res["answer"]
    citations = res["citations"]

    assert "24" in answer, f"Expected 24 credits in answer, got: {answer}"
    assert "180" not in answer or "honours" in answer.lower(), f"Answer incorrectly assigned 180 credits to PE: {answer}"
    assert len(citations) > 0, "Must return citations"
    assert citations[0]["page"] == 9, f"Top citation should be page 9, got: {citations[0]}"


def test_program_core_credits_answer():
    """Verify that Program Core (PC) credit question returns 52 credits from Page 9."""
    res = hybrid_rag.generate(
        query="how many credits are required for Program Core course",
        user_email=USER_EMAIL,
        document_names=[TEST_DOC],
    )
    assert res["status"] == "SUCCESS", f"Generation failed: {res}"
    answer = res["answer"]
    assert "52" in answer, f"Expected 52 credits for Program Core, got: {answer}"
    assert any(c["page"] == 9 for c in res["citations"]), f"Expected page 9 citation, got: {res['citations']}"


def test_foundation_core_list_answer():
    """Verify Foundation Core list question extracts components from Page 9."""
    res = hybrid_rag.generate(
        query="what are the components in Foundation Core",
        user_email=USER_EMAIL,
        document_names=[TEST_DOC],
    )
    assert res["status"] == "SUCCESS", f"Generation failed: {res}"
    answer_lower = res["answer"].lower()
    # Verify that the model lists either the Foundation Core courses (Page 10) or component areas (Page 9)
    found_items = sum(
        1 for term in [
            "problem solving", "python programming", "211cse1401", "211cse1402",
            "mathematics", "engineering", "computing", "human values"
        ] if term in answer_lower
    )
    assert found_items >= 2, f"Expected Foundation Core courses/components in answer, got: {res['answer']}"


def test_honours_credits_answer():
    """Verify that 'What are the total credits for B.Tech Honours?' answers 180 and cites Page 9."""
    res = hybrid_rag.generate(
        query="What are the total credits for B.Tech Honours?",
        user_email=USER_EMAIL,
        document_names=[TEST_DOC],
    )
    assert res["status"] == "SUCCESS", f"Generation failed: {res}"
    answer = res["answer"]
    assert "180" in answer, f"Expected 180 credits in answer, got: {answer}"
    assert any(c["page"] == 9 for c in res["citations"]), f"Expected page 9 citation, got: {res['citations']}"


def test_abstention_when_no_evidence():
    """Verify that questions with no evidence in the document cause the system to abstain honestly."""
    res = hybrid_rag.generate(
        query="What is the diplomatic policy of ancient Sparta toward Carthage?",
        user_email=USER_EMAIL,
        document_names=[TEST_DOC],
    )
    # The system must not invent answers from general knowledge
    assert res["status"] in ["NO_EVIDENCE", "ABSTAINED"] or "could not find" in res["answer"].lower(), (
        f"Expected abstention or no-evidence message, got status: {res['status']}, answer: {res['answer']}"
    )


def test_search_count_consistency():
    """Verify that search results never report 0 pages while displaying result cards."""
    res = hybrid_rag.generate(
        query="Program Elective",
        user_email=USER_EMAIL,
        document_names=[TEST_DOC],
    )
    sr = res.get("search_results")
    assert sr is not None, "search_results must be returned"
    if len(sr.get("results", [])) > 0:
        assert sr.get("total_pages", 0) > 0, "total_pages must not be 0 when results exist"
        assert sr.get("total_pages") == len(sr["results"]), "total_pages must equal the count of results"


def test_user_document_isolation():
    """Verify that a different user cannot access another user's document chunks."""
    unauthorized_user = "attacker@evil.com"
    other_chunks = [c for c in doc_store.chunks if (c.get("user_email") or "").lower() == unauthorized_user]
    assert len(other_chunks) == 0, "Unauthorized user should have 0 chunks"
    page_text = doc_store.get_page_text(TEST_DOC, 9, user_email=unauthorized_user)
    assert page_text == "", "Unauthorized user should not retrieve page text of other user"


def test_evaluation_metrics_structure():
    """Verify evaluation metrics endpoint returns valid non-negative metrics."""
    data = get_evaluation_metrics(authorization=None, x_user_email=USER_EMAIL, x_user_id=None)
    assert data["has_data"] is True
    metrics = data["metrics"]
    assert 0 <= metrics["query_success_rate"] <= 100
    assert 0 <= metrics["abstention_rate"] <= 100
    assert 0 <= metrics["evidence_coverage_rate"] <= 100
    assert 0 <= metrics["avg_latency_seconds"] < 100
    assert 0 <= metrics["avg_result_pages"] <= 20, f"Average pages found should be realistic, got: {metrics['avg_result_pages']}"


if __name__ == "__main__":
    test_table_structure_extracted()
    print("✓ test_table_structure_extracted passed")
    test_dynamic_query_understanding_acronym_resolution()
    print("✓ test_dynamic_query_understanding_acronym_resolution passed")
    test_pe_credits_retrieval_and_answer()
    print("✓ test_pe_credits_retrieval_and_answer passed")
    test_program_core_credits_answer()
    print("✓ test_program_core_credits_answer passed")
    test_foundation_core_list_answer()
    print("✓ test_foundation_core_list_answer passed")
    test_honours_credits_answer()
    print("✓ test_honours_credits_answer passed")
    test_abstention_when_no_evidence()
    print("✓ test_abstention_when_no_evidence passed")
    test_search_count_consistency()
    print("✓ test_search_count_consistency passed")
    test_user_document_isolation()
    print("✓ test_user_document_isolation passed")
    test_evaluation_metrics_structure()
    print("✓ test_evaluation_metrics_structure passed")
    print("\nALL AUTOMATED REGRESSION TESTS PASSED SUCCESSFULLY!")
