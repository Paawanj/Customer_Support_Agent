import chromadb
from langchain_chroma import Chroma

from kb_config import KB_DATA_DIR, KB_COLLECTION, KB_METADATA


def open_kb_store(kb_embeddings=None, data_dir=KB_DATA_DIR):
    kb_client = chromadb.PersistentClient(path=str(data_dir))
    kb_collection = kb_client.get_or_create_collection(
        name=KB_COLLECTION,
        embedding_function=None,
        metadata={**KB_METADATA, "ready": False},
        configuration={"hnsw": {"space": "cosine"}},
    )
    if any((kb_collection.metadata or {}).get(key) != value for key, value in KB_METADATA.items()):
        raise ValueError("The stored knowledge-base configuration does not match.")
    if kb_collection.configuration["hnsw"]["space"] != "cosine":
        raise ValueError("The knowledge-base distance must be cosine.")
    if kb_embeddings is None:
        from embeddings import kb_embeddings
    kb_vector_store = Chroma(
        client=kb_client,
        collection_name=KB_COLLECTION,
        embedding_function=kb_embeddings,
        create_collection_if_not_exists=False,
    )
    return kb_vector_store, kb_collection
