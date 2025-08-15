"""
Pydantic models for analysis responses using OpenAI Structured Outputs.
"""

from pydantic import BaseModel, Field
from typing import Optional


class SufficiencyAnalysis(BaseModel):
    """
    Structured response for sufficiency analysis.
    
    This model ensures reliable parsing of sufficiency analysis results,
    eliminating the JSON parsing issues that caused infinite loops.
    """
    sufficient: bool = Field(
        description="Whether the current search results are sufficient to answer the user's query"
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0 for the sufficiency determination",
        ge=0.0,
        le=1.0
    )
    missing_info: str = Field(
        description="Description of what information is missing if results are insufficient. Empty string if sufficient.",
        default=""
    )
    suggested_followup: str = Field(
        description="Suggested follow-up query to get missing information. Empty string if sufficient.",
        default=""
    )
    reasoning: Optional[str] = Field(
        description="Brief explanation of why the results are or aren't sufficient",
        default=None
    )