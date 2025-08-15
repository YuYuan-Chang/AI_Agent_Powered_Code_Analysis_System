"""
Pydantic models for agent responses using OpenAI Structured Outputs.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class QueryIntent(BaseModel):
    """Individual query intent with metadata."""
    nl_intent: str = Field(
        description="A specific natural language intent that clearly expresses what to find"
    )
    priority: int = Field(
        description="Priority order for executing this query (1=highest priority)",
        ge=1
    )
    query_type: str = Field(
        description="Type of query (e.g., 'primary', 'follow_up', 'related', 'verification')",
        default="primary"
    )
    reasoning: Optional[str] = Field(
        description="Why this specific query is needed",
        default=None
    )


class PrimaryAgentResponse(BaseModel):
    """
    Enhanced structured response from the Primary Agent.
    
    The Primary Agent takes a natural language query and produces
    multiple natural language intents for comprehensive exploration.
    """
    query_intents: List[QueryIntent] = Field(
        description="List of natural language intents that together address the user's query",
        min_items=1,
        max_items=5
    )
    overall_confidence: float = Field(
        description="Overall confidence score between 0.0 and 1.0 for the complete query interpretation",
        ge=0.0,
        le=1.0
    )
    decomposition_strategy: str = Field(
        description="Strategy used to decompose the query (e.g., 'single_focus', 'multi_aspect', 'hierarchical', 'comprehensive')",
        default="single_focus"
    )
    reasoning: Optional[str] = Field(
        description="Brief explanation of how the original query was interpreted and decomposed",
        default=None
    )
    
    @property
    def primary_intent(self) -> str:
        """Get the primary (highest priority) intent for backward compatibility."""
        return min(self.query_intents, key=lambda x: x.priority).nl_intent


class TranslatorAgentResponse(BaseModel):
    """
    Structured response from the Translator Agent.
    
    The Translator Agent takes a natural language intent and converts
    it to a valid Cypher query for Neo4j.
    """
    cypher_query: str = Field(
        description="The Cypher query that implements the natural language intent"
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0 for the query translation",
        ge=0.0,
        le=1.0
    )
    explanation: Optional[str] = Field(
        description="Brief explanation of the Cypher query logic",
        default=None
    )
    query_type: str = Field(
        description="Type of query (e.g., 'find_nodes', 'find_relationships', 'count', 'complex')",
        default="general"
    )