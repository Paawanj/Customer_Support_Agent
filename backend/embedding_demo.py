from embeddings import kb_embeddings
from kb_config import KB_DIMENSIONS

examples = ["I cannot log in to NovaCart.", "My checkout shows an error."]
document_vectors = kb_embeddings.embed_documents(examples)
query_vector = kb_embeddings.embed_query("How can I reset my password?")

assert len(document_vectors) == len(examples)
assert all(len(vector) == KB_DIMENSIONS for vector in document_vectors)
assert len(query_vector) == KB_DIMENSIONS
print("Document vectors:", len(document_vectors))
print("Dimensions:", len(query_vector))
