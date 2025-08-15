"""
Configuration management for CodexGraph system.
Handles API keys, Neo4j credentials, and runtime configuration.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class OpenAIConfig:
    """OpenAI API configuration."""
    api_key: str
    model: str = "gpt-4o-2024-08-06"
    temperature: float =0.1
    max_completion_tokens: int = None


@dataclass
class Neo4jConfig:
    """Neo4j database configuration."""
    uri: str
    username: str
    password: str
    database: str = "neo4j"


@dataclass
class PipelineConfig:
    """Iterative pipeline configuration."""
    max_iterations: int = 5
    sufficiency_threshold: float = 0.8
    enable_logging: bool = True


class Config:
    """Main configuration class for CodexGraph."""
    
    def __init__(self):
        self.openai = self._load_openai_config()
        self.neo4j = self._load_neo4j_config()
        self.pipeline = self._load_pipeline_config()
    
    def _load_openai_config(self) -> OpenAIConfig:
        """Load OpenAI configuration from environment variable."""
        # Get OpenAI API key from environment variable
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        return OpenAIConfig(
            api_key=api_key,
            model="gpt-4o-2024-08-06",  # Supports Structured Outputs
            temperature=0.1,
            max_completion_tokens=None
        )
    
    def _load_neo4j_config(self) -> Neo4jConfig:
        """Load Neo4j configuration - hardcoded values."""
        # Hardcoded Neo4j configuration
        uri = "neo4j://127.0.0.1:7687"
        username = "neo4j"
        password = "!Lawrence774"
        database = "localdb"
        
        return Neo4jConfig(
            uri=uri,
            username=username,
            password=password,
            database=database
        )
    
    def _load_pipeline_config(self) -> PipelineConfig:
        """Load pipeline configuration from environment variables."""
        return PipelineConfig(
            max_iterations=int(os.getenv("PIPELINE_MAX_ITERATIONS", "20")),
            sufficiency_threshold=float(os.getenv("PIPELINE_SUFFICIENCY_THRESHOLD", "0.8")),
            enable_logging=os.getenv("PIPELINE_ENABLE_LOGGING", "true").lower() == "true"
        )


# Global configuration instance
config = Config()