"""Retriever module for code repository search."""

from typing import List, Dict, Any
from langchain_core.documents import Document
from .repository_parser import RepositoryParser, CodeFile
from .vector_store import CodeVectorStore
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeRetriever:
    """Retriever for searching code repositories."""
    
    def __init__(self, cache_directory: str = "./cache"):
        """Initialize code retriever.
        
        Args:
            cache_directory: Directory to store cache files
        """
        self.parser = RepositoryParser()
        self.vector_store = CodeVectorStore(cache_directory)
        
    def index_repository(self, repo_path: str) -> Dict[str, Any]:
        """Index a code repository.
        
        Args:
            repo_path: Absolute path to repository
            
        Returns:
            Dictionary with indexing results
        """
        logger.info(f"Starting to index repository: {repo_path}")
        
        try:
            # Parse repository
            code_files = self.parser.parse_repository(repo_path)
            logger.info(f"Found {len(code_files)} code files")
            
            if not code_files:
                logger.warning("No code files found to index")
                return {
                    'success': False,
                    'message': 'No code files found in repository',
                    'files_processed': 0,
                    'chunks_created': 0
                }
            
            # Create documents
            documents = self.parser.create_documents(code_files)
            logger.info(f"Created {len(documents)} document chunks")
            
            # Add to vector store
            document_ids = self.vector_store.add_documents(documents, repo_path)
            
            # Get statistics
            stats = self.vector_store.get_stats()
            
            result = {
                'success': True,
                'message': f'Successfully indexed {len(code_files)} files',
                'repository_path': repo_path,
                'files_processed': len(code_files),
                'chunks_created': len(documents),
                'document_ids': document_ids,
                'languages': stats.get('languages', []),
                'directories': stats.get('directories', []),
                'total_code_size': stats.get('total_code_size_bytes', 0)
            }
            
            logger.info(f"Repository indexing completed: {result['message']}")
            return result
            
        except Exception as e:
            error_msg = f"Error indexing repository: {e}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'files_processed': 0,
                'chunks_created': 0
            }
            
    def search(self, query: str, k: int = 5, filters: Dict[str, Any] = None) -> List[Document]:
        """Search the indexed repository.
        
        Args:
            query: Search query
            k: Number of results to return
            filters: Optional metadata filters (e.g., {'language': 'python'})
            
        Returns:
            List of relevant documents
        """
        logger.info(f"Searching for: '{query}' (k={k})")
        
        try:
            results = self.vector_store.similarity_search(
                query=query,
                k=k,
                filter_dict=filters
            )
            
            logger.info(f"Search completed, found {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
            
    def search_by_language(self, query: str, language: str, k: int = 5) -> List[Document]:
        """Search for code in a specific programming language.
        
        Args:
            query: Search query
            language: Programming language (e.g., 'python', 'javascript')
            k: Number of results to return
            
        Returns:
            List of relevant documents
        """
        return self.vector_store.search_by_language(query, language, k)
        
    def search_by_directory(self, query: str, directory: str, k: int = 5) -> List[Document]:
        """Search for code in a specific directory.
        
        Args:
            query: Search query
            directory: Directory path (relative to repository root)
            k: Number of results to return
            
        Returns:
            List of relevant documents
        """
        return self.vector_store.search_by_directory(query, directory, k)
        
    def get_repository_stats(self) -> Dict[str, Any]:
        """Get statistics about the indexed repository.
        
        Returns:
            Dictionary with repository statistics
        """
        try:
            stats = self.vector_store.get_stats()
            metadata = self.vector_store.load_repository_metadata()
            
            if metadata:
                stats.update({
                    'repository_path': metadata.get('repository_path'),
                    'last_indexed': metadata.get('last_indexed'),
                })
                
            return stats
            
        except Exception as e:
            logger.error(f"Error getting repository stats: {e}")
            return {}
            
    def get_available_languages(self) -> List[str]:
        """Get list of all programming languages in the indexed repository.
        
        Returns:
            List of programming languages
        """
        return self.vector_store.get_all_languages()
        
    def get_available_directories(self) -> List[str]:
        """Get list of all directories in the indexed repository.
        
        Returns:
            List of directory paths
        """
        return self.vector_store.get_all_directories()
        
    def clear_index(self):
        """Clear all indexed data."""
        logger.info("Clearing repository index")
        self.vector_store.clear_cache()
        logger.info("Repository index cleared")
        
    def has_indexed_data(self) -> bool:
        """Check if there is any indexed data.
        
        Returns:
            True if repository has been indexed, False otherwise
        """
        stats = self.vector_store.get_stats()
        return stats.get('total_documents', 0) > 0