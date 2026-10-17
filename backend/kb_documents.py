from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from kb_config import KB_SOURCE_DIR, KB_CHUNK_SIZE, KB_CHUNK_OVERLAP


def load_kb_documents(source_dir=KB_SOURCE_DIR):
    documents = []
    for file_path in sorted(source_dir.glob("*.md")):
        text = file_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError("A support article is empty.")
        documents.append(Document(page_content=text, metadata={
            "source": file_path.stem,
            "title": text.splitlines()[0].lstrip("# "),
        }))
    if not documents:
        raise ValueError("Add at least one support article.")
    return documents


def split_kb_documents(documents):
    kb_splitter = RecursiveCharacterTextSplitter(
        chunk_size=KB_CHUNK_SIZE, chunk_overlap=KB_CHUNK_OVERLAP,
    )
    chunks = []
    for document in documents:
        for number, chunk in enumerate(kb_splitter.split_documents([document])):
            chunk.metadata["chunk_id"] = f"{document.metadata['source']}#chunk-{number:03d}"
            chunks.append(chunk)
    return chunks
