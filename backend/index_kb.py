from kb_config import KB_DIMENSIONS, KB_METADATA
from kb_documents import load_kb_documents, split_kb_documents
from kb_store import open_kb_store


def index_kb(kb_store=None, chunks=None):
    if chunks is None:
        chunks = split_kb_documents(load_kb_documents())
    if not chunks:
        raise ValueError("There are no support chunks to index.")
    if kb_store is None:
        kb_store = open_kb_store()
    kb_vector_store, kb_collection = kb_store
    kb_collection.modify(metadata={**KB_METADATA, "ready": False})
    chunk_ids = [chunk.metadata["chunk_id"] for chunk in chunks]
    kb_vector_store.add_documents(documents=chunks, ids=chunk_ids)
    stale_ids = sorted(set(kb_collection.get()["ids"]) - set(chunk_ids))
    if stale_ids:
        kb_vector_store.delete(ids=stale_ids)
    stored_vectors = kb_collection.get(include=["embeddings"])["embeddings"]
    if any(len(vector) != KB_DIMENSIONS for vector in stored_vectors):
        raise ValueError("The stored embedding dimensions do not match.")
    kb_collection.modify(metadata={**KB_METADATA, "ready": True})
    return kb_collection.count()


if __name__ == "__main__":
    print("Indexed support chunks:", index_kb())
