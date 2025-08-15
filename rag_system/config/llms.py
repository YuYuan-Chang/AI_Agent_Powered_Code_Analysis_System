"""LLM and embeddings configuration with caching."""

import os
from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# Chat model for LLM responses
chat_model = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    max_completion_tokens=None,
    timeout=None,
    max_retries=2,
    api_key=os.getenv("OPENAI_API_KEY")
)

# Set up cache store for embeddings - using RAG_repo cache directory
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
cache_dir = os.path.join(current_dir, "cache")
cache_store = LocalFileStore(cache_dir)

# Create underlying embeddings model
underlying_embeddings = OpenAIEmbeddings(
    model="text-embedding-3-large",
    api_key=os.getenv("OPENAI_API_KEY")
)

# Create cache-backed embeddings
EMBEDDINGS = CacheBackedEmbeddings.from_bytes_store(
    underlying_embeddings, 
    cache_store, 
    namespace=underlying_embeddings.model
)