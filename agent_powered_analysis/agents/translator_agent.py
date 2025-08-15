"""
Translator Agent for converting natural language intents into Cypher queries.
This agent takes structured natural language intents and converts them into
formal Cypher query strings for Neo4j using OpenAI Structured Outputs.
"""

import logging
import re
from typing import Optional, Dict, Any
import openai
import time
from ..config import config
from ..utils.prompts import TRANSLATOR_AGENT_SYSTEM_PROMPT, TRANSLATOR_AGENT_USER_PROMPT
from ..models.agent_models import TranslatorAgentResponse
from ..utils.openai_logger import openai_logger


class TranslatorAgent:
    """
    Translator Agent responsible for converting natural language intents 
    into Cypher queries for Neo4j.
    """
    
    def __init__(self):
        """Initialize the Translator Agent with OpenAI configuration."""
        self.client = openai.OpenAI(api_key=config.openai.api_key)
        self.model = config.openai.model
        self.temperature = config.openai.temperature
        self.max_tokens = config.openai.max_completion_tokens
        self.logger = logging.getLogger(__name__)
    
    def translate_to_cypher(self, nl_intent: str) -> TranslatorAgentResponse:
        """
        Convert a natural language intent into a Cypher query.
        
        Args:
            nl_intent: Structured natural language intent from the Primary Agent
            
        Returns:
            TranslatorAgentResponse with Cypher query and metadata
            
        Raises:
            Exception: If the OpenAI API call fails or query validation fails
        """
        try:
            self.logger.info(f"Translating intent to Cypher: {nl_intent}")
            
            messages = [
                {"role": "system", "content": TRANSLATOR_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": TRANSLATOR_AGENT_USER_PROMPT.format(nl_intent=nl_intent)}
            ]
            
            # Time the API call and log it
            start_time = time.time()
            response = self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_completion_tokens=self.max_tokens,
                response_format=TranslatorAgentResponse
            )
            duration_ms = (time.time() - start_time) * 1000
            
            # Log the API interaction
            openai_logger.log_api_call(
                method="chat.completions.parse",
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response=response,
                duration_ms=duration_ms,
                agent_name="TranslatorAgent"
            )
            
            # Handle refusal
            if response.choices[0].message.refusal:
                self.logger.warning(f"Translator agent refused: {response.choices[0].message.refusal}")
                raise Exception(f"Translator agent refused to process intent: {response.choices[0].message.refusal}")
            
            result = response.choices[0].message.parsed
            
            # Clean up the query (remove markdown formatting if present)
            cleaned_query = self._clean_cypher_query(result.cypher_query)
            
            # Validate the generated Cypher query
            if not self.validate_cypher(cleaned_query):
                raise Exception("Generated Cypher query failed validation")
            
            # Update the result with cleaned query
            result.cypher_query = cleaned_query
            
            self.logger.info(f"Generated Cypher query: {result.cypher_query}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error in translate_to_cypher: {str(e)}")
            raise Exception(f"Failed to translate intent to Cypher: {str(e)}")
    
    def refine_cypher(self, original_intent: str, current_query: str, feedback: str) -> TranslatorAgentResponse:
        """
        Refine a Cypher query based on feedback from query execution.
        
        Args:
            original_intent: The original natural language intent
            current_query: The current Cypher query that needs refinement
            feedback: Feedback about what needs to be improved
            
        Returns:
            TranslatorAgentResponse with refined Cypher query
        """
        try:
            self.logger.info(f"Refining Cypher query based on feedback: {feedback}")
            
            refinement_prompt = f"""
            Original intent: "{original_intent}"
            Current Cypher query: "{current_query}"
            Feedback for improvement: "{feedback}"
            
            Provide a refined Cypher query that addresses the feedback while maintaining the original intent.
            Ensure the query follows the graph schema and is syntactically correct.
            """
            
            messages = [
                {"role": "system", "content": TRANSLATOR_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": refinement_prompt}
            ]
            
            response = self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_completion_tokens=self.max_tokens,
                response_format=TranslatorAgentResponse
            )
            
            # Handle refusal
            if response.choices[0].message.refusal:
                self.logger.warning(f"Translator agent refused refinement: {response.choices[0].message.refusal}")
                raise Exception(f"Translator agent refused to refine query: {response.choices[0].message.refusal}")
            
            result = response.choices[0].message.parsed
            
            # Clean up the query
            cleaned_query = self._clean_cypher_query(result.cypher_query)
            
            if not self.validate_cypher(cleaned_query):
                raise Exception("Refined Cypher query failed validation")
            
            # Update the result with cleaned query
            result.cypher_query = cleaned_query
            
            self.logger.info(f"Refined Cypher query: {result.cypher_query}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error in refine_cypher: {str(e)}")
            raise Exception(f"Failed to refine Cypher query: {str(e)}")
    
    def validate_cypher(self, cypher_query: str) -> bool:
        """
        Validate that the generated Cypher query is syntactically correct.
        
        Args:
            cypher_query: The Cypher query to validate
            
        Returns:
            True if the query is valid, False otherwise
        """
        if not cypher_query or len(cypher_query.strip()) < 5:
            return False
        
        # Check for basic Cypher syntax
        cypher_upper = cypher_query.upper()
        
        # Must contain at least one of these Cypher keywords
        required_keywords = ['MATCH', 'CREATE', 'MERGE', 'DELETE', 'SET', 'REMOVE']
        if not any(keyword in cypher_upper for keyword in required_keywords):
            return False
        
        # Must contain RETURN if it's a read query
        if 'MATCH' in cypher_upper and 'RETURN' not in cypher_upper:
            return False
        
        # Check for balanced parentheses
        if cypher_query.count('(') != cypher_query.count(')'):
            return False
        
        # Check for balanced brackets
        if cypher_query.count('[') != cypher_query.count(']'):
            return False
        
        # Check for balanced braces
        if cypher_query.count('{') != cypher_query.count('}'):
            return False
        
        # Validate UNION queries have matching column names and counts
        if 'UNION' in cypher_upper:
            if not self._validate_union_query(cypher_query):
                self.logger.error("UNION query validation failed - this will cause Neo4j syntax error")
                return False  # Fail validation for column count mismatches
        
        # Check for deprecated exists() syntax
        if re.search(r'\bexists\s*\([^)]+\.[^)]+\)', cypher_query, re.IGNORECASE):
            self.logger.error("Deprecated exists() syntax detected - use 'property IS NOT NULL' instead")
            return False
        
        # Check for potential Cartesian products (disconnected patterns)
        if self._has_cartesian_product_risk(cypher_query):
            self.logger.warning("Query may create Cartesian product - consider using WITH clauses or connecting patterns via relationships")
            # Don't fail validation as this might be intentional, just warn
        
        return True
    
    def _validate_union_query(self, cypher_query: str) -> bool:
        """
        Validate that UNION queries have matching column names and counts.
        
        Args:
            cypher_query: The Cypher query containing UNION
            
        Returns:
            True if UNION queries are valid, False otherwise
        """
        try:
            # Split by UNION (case insensitive)
            import re
            union_parts = re.split(r'\bUNION\b', cypher_query, flags=re.IGNORECASE)
            
            if len(union_parts) < 2:
                return True  # No actual UNION found
            
            return_columns = []
            
            for part in union_parts:
                part = part.strip()
                if not part:
                    continue
                    
                # Extract RETURN clause
                return_match = re.search(r'\bRETURN\s+(.+?)(?:\s+ORDER|\s+LIMIT|\s+WHERE|$)', part, re.IGNORECASE | re.DOTALL)
                if not return_match:
                    continue
                    
                return_clause = return_match.group(1).strip()
                
                # Extract column names (handle AS aliases)
                columns = []
                for col in return_clause.split(','):
                    col = col.strip()
                    # Check for AS alias
                    if ' AS ' in col.upper():
                        alias_match = re.search(r'\bAS\s+(\w+)', col, re.IGNORECASE)
                        if alias_match:
                            columns.append(alias_match.group(1).lower())
                    else:
                        # Use the column expression as-is, clean it
                        clean_col = re.sub(r'[^\w.]', '', col.split('.')[-1])
                        if clean_col:
                            columns.append(clean_col.lower())
                
                return_columns.append(columns)
            
            # Check if all UNION parts have the same number of columns AND same column names
            if return_columns:
                first_count = len(return_columns[0])
                first_names = return_columns[0]
                for i, cols in enumerate(return_columns[1:], 1):
                    if len(cols) != first_count:
                        self.logger.error(f"UNION column count mismatch: part {i+1} has {len(cols)} columns vs part 1 has {first_count} columns")
                        self.logger.error(f"Part 1 columns: {first_names}")
                        self.logger.error(f"Part {i+1} columns: {cols}")
                        return False
                    # Check column names match
                    for j, col_name in enumerate(cols):
                        if j < len(first_names) and col_name != first_names[j]:
                            self.logger.error(f"UNION column name mismatch at position {j}: '{col_name}' vs '{first_names[j]}'")
                            return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Error validating UNION query: {str(e)}")
            return False
    
    def _clean_cypher_query(self, cypher_query: str) -> str:
        """
        Clean up the Cypher query by removing markdown formatting and extra whitespace.
        
        Args:
            cypher_query: Raw Cypher query that might contain formatting
            
        Returns:
            Cleaned Cypher query
        """
        # Remove markdown code blocks
        cypher_query = re.sub(r'```cypher\s*', '', cypher_query)
        cypher_query = re.sub(r'```\s*', '', cypher_query)
        
        # Remove extra whitespace and normalize
        cypher_query = ' '.join(cypher_query.split())
        
        return cypher_query.strip()
    
    def get_query_metadata(self, cypher_query: str) -> Dict[str, Any]:
        """
        Extract metadata about the Cypher query for analysis and optimization.
        
        Args:
            cypher_query: The Cypher query to analyze
            
        Returns:
            Dictionary containing query metadata
        """
        metadata = {
            'query_type': 'read' if 'MATCH' in cypher_query.upper() else 'write',
            'node_types': [],
            'relationship_types': [],
            'returns_data': 'RETURN' in cypher_query.upper()
        }
        
        # Extract node types
        node_pattern = r':(\w+)'
        metadata['node_types'] = list(set(re.findall(node_pattern, cypher_query)))
        
        # Extract relationship types
        rel_pattern = r'\[:(\w+)'
        metadata['relationship_types'] = list(set(re.findall(rel_pattern, cypher_query)))
        
        return metadata
    
    def _has_cartesian_product_risk(self, cypher_query: str) -> bool:
        """
        Check if query has patterns that might create Cartesian products.
        
        Args:
            cypher_query: The Cypher query to check
            
        Returns:
            True if query has Cartesian product risk, False otherwise
        """
        try:
            # Look for MATCH clauses with multiple disconnected node patterns
            # Pattern: MATCH (var1), (var2) where var1 and var2 are not connected
            disconnected_pattern = re.search(
                r'\bMATCH\s+\([^)]+\)\s*,\s*\([^)]+\)',
                cypher_query, 
                re.IGNORECASE
            )
            
            if disconnected_pattern:
                # Check if it's followed by WHERE clause that connects them
                remaining_query = cypher_query[disconnected_pattern.end():]
                has_connecting_where = re.search(
                    r'\bWHERE\s+[^<>=]*(<>|!=|=)',
                    remaining_query,
                    re.IGNORECASE
                )
                
                # If disconnected pattern exists and only has simple comparison WHERE clauses,
                # it's likely creating a Cartesian product
                return has_connecting_where is not None
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Error checking for Cartesian product risk: {str(e)}")
            return False