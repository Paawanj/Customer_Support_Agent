from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

from kb_config import KB_MODEL, KB_DIMENSIONS

load_dotenv()

kb_embeddings = OpenAIEmbeddings(model=KB_MODEL, dimensions=KB_DIMENSIONS)
