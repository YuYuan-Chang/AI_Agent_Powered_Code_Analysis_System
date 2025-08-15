"""LLM-based summarizer for retrieved code documents."""

from typing import List, Dict, Any
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from ..config.llms import chat_model
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeSummarizer:
    """Summarizes retrieved code documents using LLM."""
    
    def __init__(self):
        """Initialize code summarizer."""
        self.chat_model = chat_model
        
        # Template for summarizing code documents
        self.summary_template = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful assistant that analyzes and summarizes code documents based on user queries.

Your task is to:
1. Analyze the provided code snippets in the context of the user's query
2. Provide a clear, comprehensive summary that addresses the user's question
3. Highlight the most relevant parts of the code
4. Explain what the code does and how it relates to the query
5. Include specific file paths, function names, and key code elements when relevant

Be concise but thorough. Focus on answering the user's question directly."""),
            ("human", """User Query: {query}

Retrieved Code Documents:
{documents}

Please provide a comprehensive summary that addresses the user's query based on these code documents.""")
        ])
        
        # Template for explaining specific code functionality
        self.explain_template = ChatPromptTemplate.from_messages([
            ("system", """You are a code expert that explains how code works to developers.

Your task is to:
1. Analyze the provided code snippets
2. Explain the functionality, purpose, and implementation details
3. Identify key components, functions, classes, and their relationships
4. Highlight important patterns, algorithms, or design decisions
5. Provide context about how different parts work together

Be detailed and educational while remaining clear and organized."""),
            ("human", """Code to explain:
{documents}

Please provide a detailed explanation of how this code works.""")
        ])
        
    def summarize_search_results(self, query: str, documents: List[Document], max_docs: int = 10) -> str:
        """Summarize search results based on user query.
        
        Args:
            query: User's search query
            documents: Retrieved documents
            max_docs: Maximum number of documents to include
            
        Returns:
            LLM-generated summary
        """
        if not documents:
            return "No relevant code documents were found for your query."
            
        logger.info(f"Summarizing {len(documents)} documents for query: '{query[:50]}...'")
        
        try:
            # Limit documents to prevent token limit issues
            docs_to_summarize = documents[:max_docs]
            
            # Format documents for the prompt
            formatted_docs = self._format_documents(docs_to_summarize)
            
            # Generate summary using LLM
            chain = self.summary_template | self.chat_model
            response = chain.invoke({
                "query": query,
                "documents": formatted_docs
            })
            
            logger.info("Summary generated successfully")
            return response.content
            
        except Exception as e:
            error_msg = f"Error generating summary: {e}"
            logger.error(error_msg)
            return f"Sorry, I encountered an error while generating the summary: {error_msg}"
            
    def explain_code(self, documents: List[Document], max_docs: int = 5) -> str:
        """Provide detailed explanation of code functionality.
        
        Args:
            documents: Code documents to explain
            max_docs: Maximum number of documents to include
            
        Returns:
            LLM-generated code explanation
        """
        if not documents:
            return "No code documents provided for explanation."
            
        logger.info(f"Explaining {len(documents)} code documents")
        
        try:
            # Limit documents to prevent token limit issues
            docs_to_explain = documents[:max_docs]
            
            # Format documents for the prompt
            formatted_docs = self._format_documents(docs_to_explain)
            
            # Generate explanation using LLM
            chain = self.explain_template | self.chat_model
            response = chain.invoke({
                "documents": formatted_docs
            })
            
            logger.info("Code explanation generated successfully")
            return response.content
            
        except Exception as e:
            error_msg = f"Error generating explanation: {e}"
            logger.error(error_msg)
            return f"Sorry, I encountered an error while explaining the code: {error_msg}"
            
    def generate_insights(self, query: str, documents: List[Document]) -> Dict[str, Any]:
        """Generate comprehensive insights about the retrieved code.
        
        Args:
            query: User's search query
            documents: Retrieved documents
            
        Returns:
            Dictionary with various insights
        """
        if not documents:
            return {
                'summary': "No relevant code documents found.",
                'key_files': [],
                'languages': [],
                'concepts': [],
                'suggestions': []
            }
            
        logger.info(f"Generating insights for {len(documents)} documents")
        
        try:
            # Generate main summary
            summary = self.summarize_search_results(query, documents)
            
            # Extract metadata insights
            key_files = []
            languages = set()
            directories = set()
            
            for doc in documents:
                metadata = doc.metadata
                
                # Collect file information
                if 'source' in metadata and 'filename' in metadata:
                    key_files.append({
                        'file': metadata['filename'],
                        'path': metadata.get('relative_path', ''),
                        'language': metadata.get('language', 'unknown'),
                        'size': metadata.get('size', 0)
                    })
                    
                # Collect languages and directories
                if 'language' in metadata:
                    languages.add(metadata['language'])
                if 'directory' in metadata:
                    directories.add(metadata['directory'])
                    
            # Generate suggestions based on findings
            suggestions = self._generate_suggestions(query, documents, list(languages))
            
            return {
                'summary': summary,
                'key_files': key_files[:10],  # Limit to top 10 files
                'languages': sorted(list(languages)),
                'directories': sorted(list(directories)),
                'total_documents': len(documents),
                'suggestions': suggestions
            }
            
        except Exception as e:
            error_msg = f"Error generating insights: {e}"
            logger.error(error_msg)
            return {
                'summary': f"Error generating insights: {error_msg}",
                'key_files': [],
                'languages': [],
                'directories': [],
                'total_documents': 0,
                'suggestions': []
            }
            
    def _format_documents(self, documents: List[Document]) -> str:
        """Format documents for LLM prompt.
        
        Args:
            documents: List of documents to format
            
        Returns:
            Formatted string representation
        """
        formatted = []
        
        for i, doc in enumerate(documents, 1):
            metadata = doc.metadata
            
            # Create header with file information
            header_parts = [f"Document {i}"]
            
            if 'filename' in metadata:
                header_parts.append(f"File: {metadata['filename']}")
            if 'relative_path' in metadata:
                header_parts.append(f"Path: {metadata['relative_path']}")
            if 'language' in metadata:
                header_parts.append(f"Language: {metadata['language']}")
                
            header = " | ".join(header_parts)
            
            # Add content
            content = doc.page_content.strip()
            
            formatted.append(f"{header}\n{'='*len(header)}\n{content}\n")
            
        return "\n".join(formatted)
        
    def _generate_suggestions(self, query: str, documents: List[Document], languages: List[str]) -> List[str]:
        """Generate helpful suggestions based on the search results.
        
        Args:
            query: User's search query
            documents: Retrieved documents
            languages: Programming languages found
            
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        # Suggest language-specific searches
        if len(languages) > 1:
            suggestions.append(f"Try searching within specific languages: {', '.join(languages)}")
            
        # Suggest directory-based searches
        directories = set()
        for doc in documents:
            if 'directory' in doc.metadata and doc.metadata['directory']:
                directories.add(doc.metadata['directory'])
                
        if len(directories) > 1:
            top_dirs = sorted(list(directories))[:3]
            suggestions.append(f"Try searching within specific directories: {', '.join(top_dirs)}")
            
        # Suggest more specific queries
        if len(documents) > 8:
            suggestions.append("Try using more specific search terms to narrow down results")
        elif len(documents) < 3:
            suggestions.append("Try using broader search terms or synonyms to find more results")
            
        # Suggest exploring related concepts
        if any(lang in ['python', 'javascript', 'typescript'] for lang in languages):
            suggestions.append("Consider searching for related terms like 'class', 'function', 'method', or 'import'")
            
        return suggestions