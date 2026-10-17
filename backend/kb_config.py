from pathlib import Path

KB_SOURCE_DIR = Path(__file__).resolve().parent / "knowledge_base"
KB_DATA_DIR = Path(__file__).resolve().parent / "runtime" / "chroma"
KB_COLLECTION = "novacart_support_v1"
KB_MODEL = "text-embedding-3-small"
KB_DIMENSIONS = 1536
KB_CHUNK_SIZE = 600
KB_CHUNK_OVERLAP = 80
KB_MIN_SCORE = 0.55

KB_METADATA = {
    "embedding_model": KB_MODEL,
    "dimensions": KB_DIMENSIONS,
    "corpus_version": "v1",
    "distance": "cosine",
    "chunk_size": KB_CHUNK_SIZE,
    "chunk_overlap": KB_CHUNK_OVERLAP,
}
