"""
CodexGraph - Code structure-aware search with multi-agent LLM pipeline.

A sophisticated system for searching and understanding code structure using
Neo4j property graphs and OpenAI-powered agents.
"""

__version__ = "1.0.0"
__author__ = "CodexGraph Team"

from .search.iterative_pipeline import IterativePipeline
from .models.search_models import SearchResult
from .agents.primary_agent import PrimaryAgent
from .agents.translator_agent import TranslatorAgent
from .graphdb.neo4j_connector import Neo4jConnector
from .graphdb.query_executor import QueryExecutor, QueryResult
from .config import config

__all__ = [
    "IterativePipeline",
    "SearchResult", 
    "PrimaryAgent",
    "TranslatorAgent",
    "Neo4jConnector",
    "QueryExecutor",
    "QueryResult",
    "config"
]