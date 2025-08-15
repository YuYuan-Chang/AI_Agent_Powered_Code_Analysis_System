"""
Primary Agent for understanding user queries and producing natural language intents.
This agent takes natural language queries about code structure and converts them
into clear, structured natural language intents using OpenAI Structured Outputs.
"""

import logging
from typing import Optional
import openai
import time
from ..config import config
from ..utils.prompts import PRIMARY_AGENT_SYSTEM_PROMPT, PRIMARY_AGENT_USER_PROMPT, DELTY_SYSTEM_REPORT
from ..models.agent_models import PrimaryAgentResponse
from ..utils.openai_logger import openai_logger


class PrimaryAgent:
    """
    Primary Agent responsible for understanding user queries and producing 
    natural language query intents.
    """
    
    def __init__(self):
        """Initialize the Primary Agent with OpenAI configuration."""
        self.client = openai.OpenAI(api_key=config.openai.api_key)
        self.model = config.openai.model
        self.temperature = config.openai.temperature
        self.max_tokens = config.openai.max_completion_tokens
        self.logger = logging.getLogger(__name__)
    
    def understand_query(self, user_query: str) -> PrimaryAgentResponse:
        """
        Convert a natural language query into a structured natural language intent.
        
        Args:
            user_query: Natural language query from the user about code structure
            
        Returns:
            PrimaryAgentResponse with structured natural language intent and metadata
            
        Raises:
            Exception: If the OpenAI API call fails
        """
        try:
            self.logger.info(f"Processing user query: {user_query}")
            
            messages = [
                {"role": "system", "content": PRIMARY_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": PRIMARY_AGENT_USER_PROMPT.format(
                    user_query=user_query,
                    delty_system_report=DELTY_SYSTEM_REPORT
                )}
            ]
            
            # Time the API call and log it
            start_time = time.time()
            response = self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_completion_tokens=self.max_tokens,
                response_format=PrimaryAgentResponse
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
                agent_name="PrimaryAgent"
            )
            
            # Handle refusal
            if response.choices[0].message.refusal:
                self.logger.warning(f"Primary agent refused: {response.choices[0].message.refusal}")
                raise Exception(f"Primary agent refused to process query: {response.choices[0].message.refusal}")
            
            result = response.choices[0].message.parsed
            self.logger.info(f"Generated {len(result.query_intents)} intent(s), primary: {result.primary_intent}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in understand_query: {str(e)}")
            raise Exception(f"Failed to process query with Primary Agent: {str(e)}")
    
    def refine_query(self, original_query: str, feedback: str) -> PrimaryAgentResponse:
        """
        Refine a query based on feedback from previous iterations.
        
        Args:
            original_query: The original user query
            feedback: Feedback about what was missing or needed refinement
            
        Returns:
            PrimaryAgentResponse with refined natural language intent
        """
        try:
            self.logger.info(f"Refining query based on feedback: {feedback}")
            
            refinement_prompt = f"""
            Given the original query: "{original_query}"
            And this feedback about what's missing: "{feedback}"
            
            Provide a refined, more specific natural language intent that addresses the feedback.
            Focus on the missing aspects while maintaining the original intent.
            """
            
            messages = [
                {"role": "system", "content": PRIMARY_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": refinement_prompt}
            ]
            
            # Time the API call and log it
            start_time = time.time()
            response = self.client.chat.completions.parse(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_completion_tokens=self.max_tokens,
                response_format=PrimaryAgentResponse
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
                agent_name="PrimaryAgent.refine_query"
            )
            
            # Handle refusal
            if response.choices[0].message.refusal:
                self.logger.warning(f"Primary agent refused refinement: {response.choices[0].message.refusal}")
                raise Exception(f"Primary agent refused to refine query: {response.choices[0].message.refusal}")
            
            result = response.choices[0].message.parsed
            self.logger.info(f"Refined {len(result.query_intents)} intent(s), primary: {result.primary_intent}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in refine_query: {str(e)}")
            raise Exception(f"Failed to refine query with Primary Agent: {str(e)}")
    
    def validate_intent(self, intent: str) -> bool:
        """
        Validate that the generated intent is well-formed and actionable.
        
        Args:
            intent: The natural language intent to validate
            
        Returns:
            True if the intent is valid, False otherwise
        """
        if not intent or len(intent.strip()) < 10:
            return False
        
        # Check for basic code-related keywords
        code_keywords = [
            'class', 'function', 'method', 'module', 'variable', 'field',
            'inherit', 'contain', 'use', 'reference', 'call', 'define'
        ]
        
        intent_lower = intent.lower()
        return any(keyword in intent_lower for keyword in code_keywords)