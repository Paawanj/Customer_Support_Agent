from unittest.mock import Mock, patch

import chromadb
import pytest
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from kb_config import KB_COLLECTION, KB_DIMENSIONS, KB_METADATA
from kb_documents import load_kb_documents, split_kb_documents
from kb_store import open_kb_store
from index_kb import index_kb
from tech_tools import retrieve_kb_passages, search_kb
from tech_schema import TechAnswer
from tech_agent import run_tech_agent
from schemas import TicketClassification
from triage_graph import workflow


def mock_kb_embeddings():
    def vector_for(text):
        topics = ["login", "checkout", "tracking", "billing"]
        position = next((number for number, topic in enumerate(topics) if topic in text.lower()), 4)
        vector = [0.0] * KB_DIMENSIONS
        vector[position] = 1.0
        return vector
    kb_embeddings = Mock()
    kb_embeddings.embed_documents.side_effect = lambda texts: [vector_for(text) for text in texts]
    kb_embeddings.embed_query.side_effect = vector_for
    return kb_embeddings


def example_chunks():
    return split_kb_documents([
        Document(page_content="Login: request a password reset link.", metadata={"source": "KB-LOGIN", "title": "Login help"}),
        Document(page_content="Checkout: check your delivery PIN code.", metadata={"source": "KB-CHECKOUT", "title": "Checkout help"}),
    ])


def example_passages():
    return [{"chunk_id": "KB-LOGIN#chunk-000", "source": "KB-LOGIN", "title": "Login help", "text": "Use Forgot password on the login page."}]


def mock_kb_search(passages=None, error=None):
    kb_search = Mock()
    kb_search.invoke.return_value = passages or []
    kb_search.invoke.side_effect = error
    return kb_search


def mock_tech_model(answer):
    tech_model = Mock()
    tech_model.with_structured_output.return_value = RunnableLambda(lambda prompt_value: answer)
    return tech_model


def test_documents_have_stable_chunk_ids_and_metadata():
    documents = load_kb_documents()
    assert len(documents) == 4
    first = split_kb_documents(documents)
    second = split_kb_documents(load_kb_documents())
    assert [chunk.metadata["chunk_id"] for chunk in first] == [chunk.metadata["chunk_id"] for chunk in second]
    assert len({chunk.metadata["chunk_id"] for chunk in first}) == len(first)
    assert all(chunk.page_content and chunk.metadata["source"] and chunk.metadata["title"] for chunk in first)


def test_missing_and_empty_corpus_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_kb_documents(tmp_path)
    (tmp_path / "empty.md").write_text("   ", encoding="utf-8")
    with pytest.raises(ValueError):
        load_kb_documents(tmp_path)


def test_index_is_idempotent_and_reopens_from_disk(tmp_path):
    kb_embeddings = mock_kb_embeddings()
    kb_store = open_kb_store(kb_embeddings, tmp_path)
    chunks = example_chunks()
    assert index_kb(kb_store, chunks) == 2
    assert index_kb(kb_store, chunks) == 2
    reopened = open_kb_store(kb_embeddings, tmp_path)
    assert reopened[1].metadata["ready"] is True
    assert reopened[1].configuration["hnsw"]["space"] == "cosine"
    passages = retrieve_kb_passages("login problem", reopened)
    assert [item["source"] for item in passages] == ["KB-LOGIN"]
    assert kb_embeddings.embed_documents.call_count == 2


def test_reindex_removes_stale_chunks(tmp_path):
    kb_store = open_kb_store(mock_kb_embeddings(), tmp_path)
    chunks = example_chunks()
    index_kb(kb_store, chunks)
    assert index_kb(kb_store, chunks[:1]) == 1
    assert set(kb_store[1].get()["ids"]) == {chunks[0].metadata["chunk_id"]}


def test_existing_config_or_distance_mismatch_is_rejected(tmp_path):
    kb_client = chromadb.PersistentClient(path=str(tmp_path))
    kb_collection = kb_client.create_collection(
        name=KB_COLLECTION, embedding_function=None,
        metadata={**KB_METADATA, "embedding_model": "different-model", "ready": False},
        configuration={"hnsw": {"space": "cosine"}},
    )
    with pytest.raises(ValueError):
        open_kb_store(mock_kb_embeddings(), tmp_path)
    kb_collection.modify(metadata={**KB_METADATA, "ready": False})
    assert open_kb_store(mock_kb_embeddings(), tmp_path)[1].count() == 0
    other_path = tmp_path / "wrong-distance"
    other_client = chromadb.PersistentClient(path=str(other_path))
    other_client.create_collection(name=KB_COLLECTION, embedding_function=None, metadata={**KB_METADATA, "ready": False}, configuration={"hnsw": {"space": "l2"}})
    with pytest.raises(ValueError):
        open_kb_store(mock_kb_embeddings(), other_path)


def test_unready_index_and_wrong_dimensions_do_not_serve_passages(tmp_path):
    kb_embeddings = mock_kb_embeddings()
    kb_store = open_kb_store(kb_embeddings, tmp_path)
    with pytest.raises(ValueError):
        retrieve_kb_passages("login problem", kb_store)
    kb_embeddings.embed_query.assert_not_called()
    kb_embeddings.embed_documents.side_effect = lambda texts: [[1.0, 0.0, 0.0] for text in texts]
    with pytest.raises(ValueError):
        index_kb(kb_store, example_chunks())
    assert kb_store[1].metadata["ready"] is False
    with pytest.raises(ValueError):
        retrieve_kb_passages("login problem", kb_store)


def test_threshold_filters_unrelated_passages(tmp_path):
    kb_store = open_kb_store(mock_kb_embeddings(), tmp_path)
    index_kb(kb_store, example_chunks())
    assert retrieve_kb_passages("quantum astronomy", kb_store) == []


def test_search_kb_tool_uses_the_real_retriever(tmp_path):
    kb_store = open_kb_store(mock_kb_embeddings(), tmp_path)
    index_kb(kb_store, example_chunks())
    with patch("tech_tools.open_kb_store", return_value=kb_store):
        passages = search_kb.invoke({"query": "checkout error"})
    assert [item["source"] for item in passages] == ["KB-CHECKOUT"]
    for query in ["", "   ", None, 123]:
        with pytest.raises(ValueError):
            retrieve_kb_passages(query, kb_store)


def test_supported_answer_uses_only_retrieved_citations():
    passages = example_passages()
    tech_model = mock_tech_model(TechAnswer(supported=True, answer="Select Forgot password.", citations=[passages[0]["chunk_id"]]))
    with patch("tech_agent.search_kb", mock_kb_search(passages)):
        result = run_tech_agent({"ticket": "login problem"}, tech_model)
    assert result["status"] == "ANSWERED"
    assert result["citations"] == result["retrieved_source_ids"]
    assert "Sources: KB-LOGIN#chunk-000" in result["response"]
    assert result["tool_outcomes"][0]["tool"] == "search_kb"
    tech_model.with_structured_output.assert_called_once_with(TechAnswer)


def test_no_passages_does_not_call_the_model():
    tech_model = Mock()
    with patch("tech_agent.search_kb", mock_kb_search()):
        result = run_tech_agent({"ticket": "unrelated question"}, tech_model)
    assert result["escalation_reason"] == "kb_no_support"
    assert result["citations"] == []
    tech_model.with_structured_output.assert_not_called()


def test_unsupported_blank_or_invalid_citations_require_review():
    cases = [
        (TechAnswer(supported=False, answer="", citations=[]), "kb_answer_unsupported"),
        (TechAnswer(supported=True, answer="   ", citations=["KB-LOGIN#chunk-000"]), "kb_answer_unsupported"),
        (TechAnswer(supported=True, answer="Invented steps.", citations=[]), "kb_invalid_citation"),
        (TechAnswer(supported=True, answer="Invented steps.", citations=["MADE-UP"]), "kb_invalid_citation"),
    ]
    for answer, reason in cases:
        with patch("tech_agent.search_kb", mock_kb_search(example_passages())):
            result = run_tech_agent({"ticket": "login problem"}, mock_tech_model(answer))
        assert result["status"] == "NEEDS_REVIEW"
        assert result["escalation_reason"] == reason
        assert result["citations"] == []


def test_tech_failures_are_redacted_and_preserve_retrieved_ids():
    with patch("tech_agent.search_kb", mock_kb_search(error=RuntimeError("PRIVATE-KEY-DETAILS"))):
        result = run_tech_agent({"ticket": "login problem"}, Mock())
    assert result["escalation_reason"] == "tech_failed_RuntimeError"
    assert "PRIVATE-KEY-DETAILS" not in str(result)
    tech_model = Mock()
    tech_model.with_structured_output.side_effect = RuntimeError("PRIVATE-PROVIDER-DETAILS")
    with patch("tech_agent.search_kb", mock_kb_search(example_passages())):
        result = run_tech_agent({"ticket": "login problem"}, tech_model)
    assert result["retrieved_source_ids"] == ["KB-LOGIN#chunk-000"]
    assert "PRIVATE-PROVIDER-DETAILS" not in str(result)
    with patch("tech_agent.search_kb", mock_kb_search()) as kb_search:
        assert run_tech_agent({"ticket": ""}, Mock())["status"] == "NEEDS_REVIEW"
    kb_search.invoke.assert_not_called()


def test_tech_and_general_graph_answers_terminate():
    tech_model = mock_tech_model(TechAnswer(supported=True, answer="Select Forgot password.", citations=["KB-LOGIN#chunk-000"]))
    for category in ["tech", "general"]:
        classification = TicketClassification(category=category, confidence=0.9, reasoning="Support question.")
        with patch("graph_nodes.classify_ticket", return_value=classification), \
            patch("tech_agent.search_kb", mock_kb_search(example_passages())), \
            patch("tech_agent.run_tech_agent", side_effect=lambda state: run_tech_agent(state, tech_model)):
            updates = list(workflow.stream({"ticket_id": "T-RAG", "ticket": "login problem"}, stream_mode="updates"))
        assert [list(update)[0] for update in updates] == ["classify", "tech"]
        assert updates[-1]["tech"]["status"] == "ANSWERED"


def test_unknown_question_escalates_with_its_reason():
    classification = TicketClassification(category="general", confidence=0.9, reasoning="FAQ question.")
    with patch("graph_nodes.classify_ticket", return_value=classification), \
        patch("tech_agent.search_kb", mock_kb_search()):
        updates = list(workflow.stream({"ticket_id": "T-UNKNOWN", "ticket": "unrelated question"}, stream_mode="updates"))
    assert [list(update)[0] for update in updates] == ["classify", "tech", "escalate"]
    assert updates[-1]["escalate"]["status"] == "ESCALATED"
    assert updates[-2]["tech"]["escalation_reason"] == "kb_no_support"


def test_anger_bypasses_knowledge_base_search():
    classification = TicketClassification(category="tech", confidence=0.95, reasoning="Login issue.")
    with patch("graph_nodes.classify_ticket", return_value=classification), \
        patch("tech_agent.search_kb", mock_kb_search()) as kb_search:
        result = workflow.invoke({"ticket_id": "T-ANGRY", "ticket": "I am angry about login."})
    assert result["status"] == "ESCALATED"
    assert result["escalation_reason"] == "angry_ticket"
    kb_search.invoke.assert_not_called()
