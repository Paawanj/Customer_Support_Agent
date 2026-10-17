from langchain_core.tools import tool

from kb_config import KB_MIN_SCORE
from kb_store import open_kb_store


def retrieve_kb_passages(query, kb_store):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Enter a support question.")
    kb_vector_store, kb_collection = kb_store
    if not kb_collection.metadata.get("ready") or kb_collection.count() == 0:
        raise ValueError("Index the support articles before answering tickets.")
    kb_retriever = kb_vector_store.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 3, "score_threshold": KB_MIN_SCORE},
    )
    passages = kb_retriever.invoke(query.strip())
    return [{
        "chunk_id": passage.metadata["chunk_id"],
        "source": passage.metadata["source"],
        "title": passage.metadata["title"],
        "text": passage.page_content,
    } for passage in passages]


@tool
def search_kb(query: str) -> list[dict]:
    """Find NovaCart support passages for a technical or FAQ question."""
    return retrieve_kb_passages(query, open_kb_store())
