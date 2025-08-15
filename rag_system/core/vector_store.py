"""Vector store for code repository using InMemoryVectorStore with cache."""

import os
import json
import pickle
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    Language,
    PythonCodeTextSplitter,
    MarkdownTextSplitter,
    LatexTextSplitter
)
from ..config.llms import EMBEDDINGS
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeVectorStore:
    """Vector store for code embeddings using cached InMemoryVectorStore."""
    
    def __init__(self, cache_directory: str = "./cache"):
        """Initialize vector store.
        
        Args:
            cache_directory: Directory to store cache files
        """
        self.cache_directory = cache_directory
        self.vector_store = InMemoryVectorStore(embedding=EMBEDDINGS)
        
        # Create cache directory if it doesn't exist
        os.makedirs(cache_directory, exist_ok=True)
        
        # Cache files
        self.documents_cache_file = os.path.join(cache_directory, "repo_documents.pkl")
        self.metadata_file = os.path.join(cache_directory, "repo_metadata.json")
        
        # Default text splitter for general files
        self.default_text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=150,
            length_function=len,
        )
        
        # File extension to language mapping for semantic chunking
        self.extension_to_language = {
            '.py': Language.PYTHON,
            '.js': Language.JS,
            '.jsx': Language.JS,
            '.ts': Language.TS,
            '.tsx': Language.TS,
            '.java': Language.JAVA,
            '.cpp': Language.CPP,
            '.c': Language.C,
            '.cc': Language.CPP,
            '.cxx': Language.CPP,
            '.go': Language.GO,
            '.rs': Language.RUST,
            '.rb': Language.RUBY,
            '.php': Language.PHP,
            '.swift': Language.SWIFT,
            '.kt': Language.KOTLIN,
            '.scala': Language.SCALA,
            '.cs': Language.CSHARP,
            '.lua': Language.LUA,
            '.pl': Language.PERL,
            '.hs': Language.HASKELL,
            '.ex': Language.ELIXIR,
            '.exs': Language.ELIXIR,
            '.md': Language.MARKDOWN,
            '.markdown': Language.MARKDOWN,
            '.tex': Language.LATEX,
            '.html': Language.HTML,
            '.htm': Language.HTML,
            '.sol': Language.SOL,
            '.ps1': Language.POWERSHELL,
            '.vb': Language.VISUALBASIC6,
            '.cob': Language.COBOL,
        }
        
        # Load existing cache
        self.cached_documents = []
        self._load_cache()
    
    def _get_semantic_chunks(self, documents: List[Document]) -> List[Document]:
        """Split documents using semantic chunking based on file type and content structure."""
        chunks = []
        
        for doc in documents:
            filename = doc.metadata.get('filename', '')
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Select appropriate text splitter based on file extension
            if file_ext in self.extension_to_language:
                language = self.extension_to_language[file_ext]
                
                try:
                    if language == Language.PYTHON:
                        splitter = PythonCodeTextSplitter(
                            chunk_size=1500,
                            chunk_overlap=150,
                            length_function=len,
                        )
                    elif language == Language.MARKDOWN:
                        splitter = MarkdownTextSplitter(
                            chunk_size=1500,
                            chunk_overlap=150,
                            length_function=len,
                        )
                    elif language == Language.LATEX:
                        splitter = LatexTextSplitter(
                            chunk_size=1500,
                            chunk_overlap=150,
                            length_function=len,
                        )
                    else:
                        # Use RecursiveCharacterTextSplitter with language-specific separators
                        splitter = RecursiveCharacterTextSplitter.from_language(
                            language=language,
                            chunk_size=1500,
                            chunk_overlap=150,
                            length_function=len,
                        )
                    
                    doc_chunks = splitter.split_documents([doc])
                    logger.debug(f"Used {language.value} semantic chunking for {filename}")
                    
                except Exception as e:
                    logger.warning(f"Failed to use semantic chunking for {filename}: {e}, falling back to default")
                    doc_chunks = self.default_text_splitter.split_documents([doc])
            else:
                # Use default text splitter for unknown file types
                doc_chunks = self.default_text_splitter.split_documents([doc])
                logger.debug(f"Used default chunking for {filename}")
            
            # Add semantic metadata to chunks
            for chunk in doc_chunks:
                if file_ext in self.extension_to_language:
                    chunk.metadata['chunking_strategy'] = 'semantic'
                    chunk.metadata['detected_language'] = self.extension_to_language[file_ext].value
                else:
                    chunk.metadata['chunking_strategy'] = 'default'
                    chunk.metadata['detected_language'] = 'unknown'
            
            chunks.extend(doc_chunks)
        
        return chunks
        
    def _load_cache(self):
        """Load cached documents if they exist."""
        try:
            if os.path.exists(self.documents_cache_file):
                with open(self.documents_cache_file, 'rb') as f:
                    self.cached_documents = pickle.load(f)
                
                # Add cached documents to vector store
                if self.cached_documents:
                    self.vector_store.add_documents(self.cached_documents)
                    logger.info(f"Loaded {len(self.cached_documents)} cached documents")
                    
        except Exception as e:
            logger.warning(f"Error loading cache: {e}")
            self.cached_documents = []
            
    def _save_cache(self, all_documents: List[Document], repo_path: str = None):
        """Save documents to cache."""
        try:
            # Save documents
            with open(self.documents_cache_file, 'wb') as f:
                pickle.dump(all_documents, f)
                
            # Save metadata
            metadata = {
                'repository_path': repo_path,
                'total_documents': len(all_documents),
                'last_indexed': datetime.now().isoformat(),
                'cache_directory': self.cache_directory
            }
            
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            logger.info(f"Cached {len(all_documents)} documents")
            
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            
    def add_documents(self, documents: List[Document], repo_path: str = None) -> List[str]:
        """Add documents to the vector store in batches.
        
        Args:
            documents: List of Document objects to add
            repo_path: Path to the repository (for metadata)
            
        Returns:
            List of document IDs
        """
        if not documents:
            logger.warning("No documents provided to add")
            return []
            
        logger.info(f"Adding {len(documents)} documents to vector store...")
        
        try:
            # Split all documents into chunks using semantic chunking
            all_chunks = []
            for i, doc in enumerate(documents, 1):
                chunks = self._get_semantic_chunks([doc])
                filename = doc.metadata.get('filename', f'doc_{i}')
                logger.info(f"Prepared file {i}/{len(documents)}: {filename} ({len(chunks)} chunks)")
                all_chunks.extend(chunks)
                
            logger.info(f"Created {len(all_chunks)} total chunks, processing in batches of 100...")
            
            # Process in smaller batches to stay under OpenAI's 300K token limit
            # With 2000 char chunks, 50 chunks ≈ 100K chars ≈ 75K tokens (safe margin)
            batch_size = 200
            all_ids = []
            successful_chunks = []
            
            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(all_chunks) + batch_size - 1) // batch_size
                
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)")
                
                try:
                    # Calculate approximate token count for the batch
                    total_chars = sum(len(chunk.page_content) for chunk in batch)
                    estimated_tokens = int(total_chars * 0.75)  # Rough estimate: 0.75 tokens per char
                    
                    if estimated_tokens > 250000:  # Conservative limit (250K tokens)
                        logger.warning(f"Batch {batch_num} estimated tokens ({estimated_tokens}) too high, processing individually")
                        # Process chunks individually if batch is too large
                        for chunk in batch:
                            try:
                                chunk_ids = self.vector_store.add_documents([chunk])
                                all_ids.extend(chunk_ids)
                                successful_chunks.append(chunk)
                            except Exception as chunk_error:
                                filename = chunk.metadata.get('filename', 'unknown')
                                logger.warning(f"Failed to add chunk from {filename}: {chunk_error}")
                                continue
                    else:
                        # Add batch to vector store
                        batch_ids = self.vector_store.add_documents(batch)
                        all_ids.extend(batch_ids)
                        successful_chunks.extend(batch)
                        logger.info(f"Successfully processed batch {batch_num} ({estimated_tokens} estimated tokens)")
                except Exception as e:
                    logger.warning(f"Failed to process batch {batch_num}: {e}")
                    # Try adding chunks one by one in this batch
                    for j, chunk in enumerate(batch):
                        try:
                            chunk_ids = self.vector_store.add_documents([chunk])
                            all_ids.extend(chunk_ids)
                            successful_chunks.append(chunk)
                        except Exception as chunk_error:
                            filename = chunk.metadata.get('filename', 'unknown')
                            logger.warning(f"Failed to add chunk from {filename}: {chunk_error}")
                            continue
                            
            # Update cached documents
            self.cached_documents.extend(successful_chunks)
            
            # Save to cache
            self._save_cache(self.cached_documents, repo_path)
            
            total_batches = (len(all_chunks) + batch_size - 1) // batch_size
            logger.info(f"Successfully added {len(successful_chunks)}/{len(all_chunks)} chunks in {total_batches} batches")
            return all_ids
            
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")
            raise
            
    def similarity_search(self, query: str, k: int = 5, filter_dict: Dict[str, Any] = None) -> List[Document]:
        """Perform similarity search.
        
        Args:
            query: Search query
            k: Number of results to return
            filter_dict: Optional metadata filters
            
        Returns:
            List of matching documents
        """
        try:
            if filter_dict:
                # Filter documents manually since InMemoryVectorStore doesn't support filters
                filtered_docs = []
                for doc in self.cached_documents:
                    match = all(
                        doc.metadata.get(key) == value 
                        for key, value in filter_dict.items()
                    )
                    if match:
                        filtered_docs.append(doc)
                        
                if not filtered_docs:
                    logger.info("No documents match the filter criteria")
                    return []
                    
                # Create temporary vector store with filtered documents
                temp_store = InMemoryVectorStore(embedding=EMBEDDINGS)
                temp_store.add_documents(filtered_docs)
                results = temp_store.similarity_search(query=query, k=k)
            else:
                results = self.vector_store.similarity_search(query=query, k=k)
                
            logger.info(f"Found {len(results)} results for query: '{query[:50]}...'")
            return results
            
        except Exception as e:
            logger.error(f"Error performing similarity search: {e}")
            return []
            
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        try:
            languages = set()
            directories = set()
            file_types = set()
            total_size = 0
            
            for doc in self.cached_documents:
                metadata = doc.metadata
                if 'language' in metadata:
                    languages.add(metadata['language'])
                if 'directory' in metadata:
                    directories.add(metadata['directory'])
                if 'filename' in metadata:
                    ext = os.path.splitext(metadata['filename'])[1]
                    if ext:
                        file_types.add(ext)
                if 'size' in metadata:
                    total_size += metadata['size']
                    
            return {
                'total_documents': len(self.cached_documents),
                'languages': sorted(list(languages)),
                'directories': sorted(list(directories)),
                'file_types': sorted(list(file_types)),
                'total_code_size_bytes': total_size,
                'cache_directory': self.cache_directory
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
            
    def clear_cache(self):
        """Clear all cached data."""
        try:
            # Clear vector store
            self.vector_store = InMemoryVectorStore(embedding=EMBEDDINGS)
            self.cached_documents = []
            
            # Remove cache files
            for file_path in [self.documents_cache_file, self.metadata_file]:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
            logger.info("Cleared all cached data")
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            
    def load_repository_metadata(self) -> Optional[Dict[str, Any]]:
        """Load repository metadata from cache."""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load metadata: {e}")
        return None
        
    def search_by_language(self, query: str, language: str, k: int = 5) -> List[Document]:
        """Search for documents in a specific programming language."""
        return self.similarity_search(
            query=query,
            k=k,
            filter_dict={"language": language}
        )
        
    def search_by_directory(self, query: str, directory: str, k: int = 5) -> List[Document]:
        """Search for documents in a specific directory."""
        return self.similarity_search(
            query=query,
            k=k,
            filter_dict={"directory": directory}
        )
        
    def get_all_languages(self) -> List[str]:
        """Get all programming languages in the store."""
        stats = self.get_stats()
        return stats.get('languages', [])
        
    def get_all_directories(self) -> List[str]:
        """Get all directories in the store."""
        stats = self.get_stats()
        return stats.get('directories', [])