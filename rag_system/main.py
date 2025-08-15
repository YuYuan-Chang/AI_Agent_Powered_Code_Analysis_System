"""Main interface for the Code Repository RAG system."""

import os
import argparse
from typing import Optional
from .core.retriever import CodeRetriever
from .core.summarizer import CodeSummarizer
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeRAGSystem:
    """Main class for the Code Repository RAG system."""
    
    def __init__(self, cache_directory: str = "./cache"):
        """Initialize the RAG system.
        
        Args:
            cache_directory: Directory to store cache files
        """
        self.retriever = CodeRetriever(cache_directory)
        self.summarizer = CodeSummarizer()
        logger.info(f"Initialized Code RAG system with cache directory: {cache_directory}")
        
    def index_repository(self, repo_path: str) -> dict:
        """Index a code repository for search.
        
        Args:
            repo_path: Absolute path to the repository
            
        Returns:
            Dictionary with indexing results
        """
        if not os.path.isabs(repo_path):
            raise ValueError("Repository path must be absolute")
            
        if not os.path.isdir(repo_path):
            raise ValueError(f"Repository path does not exist: {repo_path}")
            
        logger.info(f"Starting repository indexing: {repo_path}")
        result = self.retriever.index_repository(repo_path)
        
        if result['success']:
            print(f"✅ Successfully indexed repository!")
            print(f"📁 Repository: {repo_path}")
            print(f"📄 Files processed: {result['files_processed']}")
            print(f"🔤 Document chunks: {result['chunks_created']}")
            print(f"💻 Languages found: {', '.join(result['languages'])}")
            print(f"📊 Total code size: {result['total_code_size']:,} bytes")
        else:
            print(f"❌ Failed to index repository: {result['message']}")
            
        return result
        
    def search_only(self, query: str, k: int = 5, language: Optional[str] = None, 
                   directory: Optional[str] = None) -> dict:
        """Search repository and return documents without summary.
        
        Args:
            query: Search query
            k: Number of results to retrieve
            language: Optional language filter
            directory: Optional directory filter
            
        Returns:
            Dictionary with search results (no LLM summary)
        """
        logger.info(f"Searching for: '{query}' (no summary)")
        
        # Prepare filters
        filters = {}
        if language:
            filters['language'] = language
        if directory:
            filters['directory'] = directory
            
        # Search for relevant documents
        if language:
            documents = self.retriever.search_by_language(query, language, k)
        elif directory:
            documents = self.retriever.search_by_directory(query, directory, k)
        else:
            documents = self.retriever.search(query, k, filters)
            
        if not documents:
            return {
                'query': query,
                'documents_found': 0,
                'documents': [],
                'message': 'No relevant code documents found for your query.'
            }
            
        # Extract basic info without LLM processing
        key_files = []
        languages = set()
        directories = set()
        
        for doc in documents:
            metadata = doc.metadata
            
            if 'source' in metadata and 'filename' in metadata:
                key_files.append({
                    'file': metadata['filename'],
                    'path': metadata.get('relative_path', ''),
                    'language': metadata.get('language', 'unknown'),
                    'size': metadata.get('size', 0),
                    'content': doc.page_content
                })
                
            if 'language' in metadata:
                languages.add(metadata['language'])
            if 'directory' in metadata:
                directories.add(metadata['directory'])
                
        return {
            'query': query,
            'documents_found': len(documents),
            'documents': documents,
            'key_files': key_files,
            'languages': sorted(list(languages)),
            'directories': sorted(list(directories))
        }
    
    def search_and_summarize(self, query: str, k: int = 5, language: Optional[str] = None, 
                           directory: Optional[str] = None) -> dict:
        """Search repository and generate summary.
        
        Args:
            query: Search query
            k: Number of results to retrieve
            language: Optional language filter
            directory: Optional directory filter
            
        Returns:
            Dictionary with search results and summary
        """
        logger.info(f"Searching for: '{query}'")
        
        # Prepare filters
        filters = {}
        if language:
            filters['language'] = language
        if directory:
            filters['directory'] = directory
            
        # Search for relevant documents
        if language:
            documents = self.retriever.search_by_language(query, language, k)
        elif directory:
            documents = self.retriever.search_by_directory(query, directory, k)
        else:
            documents = self.retriever.search(query, k, filters)
            
        if not documents:
            return {
                'query': query,
                'documents_found': 0,
                'summary': 'No relevant code documents found for your query.',
                'suggestions': ['Try using different search terms', 'Check if the repository has been indexed']
            }
            
        # Generate comprehensive insights
        insights = self.summarizer.generate_insights(query, documents)
        
        return {
            'query': query,
            'documents_found': len(documents),
            'summary': insights['summary'],
            'key_files': insights['key_files'],
            'languages': insights['languages'],
            'directories': insights['directories'],
            'suggestions': insights['suggestions']
        }
        
    def get_system_status(self) -> dict:
        """Get current system status and statistics.
        
        Returns:
            Dictionary with system status
        """
        stats = self.retriever.get_repository_stats()
        has_data = self.retriever.has_indexed_data()
        
        return {
            'has_indexed_data': has_data,
            'repository_stats': stats
        }
        
    def clear_index(self):
        """Clear all indexed data."""
        self.retriever.clear_index()
        print("🗑️ Cleared all indexed data")


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description='Code Repository RAG System')
    parser.add_argument('command', choices=['index', 'search', 'search-only', 'status', 'clear'],
                       help='Command to execute')
    parser.add_argument('--repo-path', type=str,
                       help='Absolute path to repository (for index command)')
    parser.add_argument('--query', type=str,
                       help='Search query (for search command)')
    parser.add_argument('--language', type=str,
                       help='Filter by programming language')
    parser.add_argument('--directory', type=str,
                       help='Filter by directory')
    parser.add_argument('--k', type=int, default=5,
                       help='Number of results to return (default: 5)')
    parser.add_argument('--cache-dir', type=str, default='./cache',
                       help='Cache directory (default: ./cache)')
    
    args = parser.parse_args()
    
    # Initialize system
    rag_system = CodeRAGSystem(args.cache_dir)
    
    if args.command == 'index':
        if not args.repo_path:
            print("❌ --repo-path is required for index command")
            return
            
        try:
            rag_system.index_repository(args.repo_path)
        except Exception as e:
            print(f"❌ Error: {e}")
            
    elif args.command == 'search-only':
        if not args.query:
            print("❌ --query is required for search-only command")
            return
            
        try:
            result = rag_system.search_only(
                query=args.query,
                k=args.k,
                language=args.language,
                directory=args.directory
            )
            
            print(f"\n🔍 Search Query: {result['query']}")
            print(f"📄 Documents Found: {result['documents_found']}")
            
            if result['documents_found'] > 0:
                if result['key_files']:
                    print(f"\n📁 Found Files:")
                    for file_info in result['key_files']:
                        print(f"\n📄 File: {file_info['file']} ({file_info['language']})")
                        print(f"📂 Path: {file_info['path']}")
                        print(f"📏 Size: {file_info['size']} bytes")
                        print("📝 Content:")
                        print("-" * 50)
                        print(file_info['content'])
                        print("-" * 50)
                        
                if result['languages']:
                    print(f"\n💻 Languages: {', '.join(result['languages'])}")
                    
            else:
                print(f"\n❌ {result['message']}")
                        
        except Exception as e:
            print(f"❌ Error: {e}")
            
    elif args.command == 'search':
        if not args.query:
            print("❌ --query is required for search command")
            return
            
        try:
            result = rag_system.search_and_summarize(
                query=args.query,
                k=args.k,
                language=args.language,
                directory=args.directory
            )
            
            print(f"\n🔍 Search Query: {result['query']}")
            print(f"📄 Documents Found: {result['documents_found']}")
            
            if result['documents_found'] > 0:
                print(f"\n📝 Summary:\n{result['summary']}")
                
                if result['key_files']:
                    print(f"\n📁 Key Files:")
                    for file_info in result['key_files'][:5]:
                        print(f"  • {file_info['file']} ({file_info['language']})")
                        
                if result['languages']:
                    print(f"\n💻 Languages: {', '.join(result['languages'])}")
                    
                if result['suggestions']:
                    print(f"\n💡 Suggestions:")
                    for suggestion in result['suggestions']:
                        print(f"  • {suggestion}")
                        
        except Exception as e:
            print(f"❌ Error: {e}")
            
    elif args.command == 'status':
        try:
            status = rag_system.get_system_status()
            
            if status['has_indexed_data']:
                stats = status['repository_stats']
                print("✅ Repository is indexed")
                print(f"📄 Total documents: {stats.get('total_documents', 0)}")
                print(f"💻 Languages: {', '.join(stats.get('languages', []))}")
                print(f"📁 Directories: {len(stats.get('directories', []))}")
                print(f"📊 Total code size: {stats.get('total_code_size_bytes', 0):,} bytes")
                
                if 'repository_path' in stats:
                    print(f"📂 Repository: {stats['repository_path']}")
                if 'last_indexed' in stats:
                    print(f"🕐 Last indexed: {stats['last_indexed']}")
            else:
                print("❌ No repository indexed yet")
                print("Use 'python main.py index --repo-path /path/to/repo' to index a repository")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            
    elif args.command == 'clear':
        try:
            rag_system.clear_index()
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()