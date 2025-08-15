"""
RAG Agent for integrating vector-based code search with the graph-based pipeline.
This agent interfaces with the RAG_repo system to provide document-based search results.
"""

import logging
import sys
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Add rag_system to path for imports
rag_system_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'rag_system')
sys.path.append(rag_system_path)

try:
    from rag_system import CodeRAGSystem
except ImportError as e:
    logging.getLogger(__name__).error(f"Failed to import RAG system: {e}")
    CodeRAGSystem = None


@dataclass
class RAGSearchResult:
    """Result from RAG-based search."""
    query: str
    documents_found: int
    key_files: List[Dict[str, Any]]
    languages: List[str]
    directories: List[str]
    success: bool
    error_message: Optional[str] = None


class RAGAgent:
    """
    RAG Agent responsible for performing vector-based similarity search
    on the code repository to complement graph-based queries.
    """
    
    def __init__(self, cache_directory: str = None):
        """
        Initialize the RAG Agent.
        
        Args:
            cache_directory: Directory for RAG cache (defaults to RAG_repo/cache)
        """
        self.logger = logging.getLogger(__name__)
        
        if CodeRAGSystem is None:
            self.logger.error("RAG system not available - CodeRAGSystem import failed")
            self.rag_system = None
            return
            
        # Default cache directory to project root cache  
        if cache_directory is None:
            # Get ai-agents directory (4 levels up from this file)
            current_dir = os.path.dirname(__file__)  # agents/
            agent_powered_analysis_dir = os.path.dirname(current_dir)  # agent_powered_analysis/
            project_root = os.path.dirname(agent_powered_analysis_dir)  # ai-agents/
            cache_directory = os.path.join(project_root, 'cache')
            
        try:
            self.rag_system = CodeRAGSystem(cache_directory)
            self.logger.info(f"Initialized RAG agent with cache directory: {cache_directory}")
        except Exception as e:
            self.logger.error(f"Failed to initialize RAG system: {str(e)}")
            self.rag_system = None
    
    def is_available(self) -> bool:
        """
        Check if the RAG system is available and has indexed data.
        
        Returns:
            True if RAG system is ready to use, False otherwise
        """
        if self.rag_system is None:
            return False
            
        try:
            status = self.rag_system.get_system_status()
            return status['has_indexed_data']
        except Exception as e:
            self.logger.error(f"Error checking RAG availability: {str(e)}")
            return False
    
    def search_documents(self, query: str, k: int = 5, language: Optional[str] = None, 
                        directory: Optional[str] = None) -> RAGSearchResult:
        """
        Search for relevant code documents using vector similarity.
        
        Args:
            query: Natural language query
            k: Number of top documents to retrieve
            language: Optional language filter (e.g., 'python', 'javascript')
            directory: Optional directory filter
            
        Returns:
            RAGSearchResult with search results and metadata
        """
        if not self.is_available():
            return RAGSearchResult(
                query=query,
                documents_found=0,
                key_files=[],
                languages=[],
                directories=[],
                success=False,
                error_message="RAG system not available or no data indexed"
            )
        
        try:
            self.logger.info(f"RAG search for: '{query}' (k={k}, language={language}, directory={directory})")
            
            # Use the search_only method to avoid LLM summarization in RAG pipeline
            # (we'll do our own summarization in the main pipeline)
            result = self.rag_system.search_only(
                query=query,
                k=k,
                language=language,
                directory=directory
            )
            
            if result['documents_found'] == 0:
                return RAGSearchResult(
                    query=query,
                    documents_found=0,
                    key_files=[],
                    languages=[],
                    directories=[],
                    success=True,
                    error_message=result.get('message', 'No documents found')
                )
            
            return RAGSearchResult(
                query=query,
                documents_found=result['documents_found'],
                key_files=result['key_files'],
                languages=result['languages'],
                directories=result['directories'],
                success=True
            )
            
        except Exception as e:
            self.logger.error(f"RAG search failed: {str(e)}")
            return RAGSearchResult(
                query=query,
                documents_found=0,
                key_files=[],
                languages=[],
                directories=[],
                success=False,
                error_message=f"RAG search failed: {str(e)}"
            )
    
    def get_system_info(self) -> Dict[str, Any]:
        """
        Get information about the RAG system status.
        
        Returns:
            Dictionary with system information
        """
        if self.rag_system is None:
            return {
                'available': False,
                'error': 'RAG system not initialized'
            }
        
        try:
            status = self.rag_system.get_system_status()
            return {
                'available': True,
                'has_indexed_data': status['has_indexed_data'],
                'repository_stats': status['repository_stats']
            }
        except Exception as e:
            self.logger.error(f"Error getting RAG system info: {str(e)}")
            return {
                'available': False,
                'error': str(e)
            }