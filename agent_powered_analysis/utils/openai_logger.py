"""
Utility for logging OpenAI API interactions.
Provides comprehensive logging of requests, responses, and token usage.
"""

import logging
import json
import time
from functools import wraps
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime


class OpenAILogger:
    """Utility class for logging OpenAI API interactions."""
    
    def __init__(self, logger_name: str = "openai_api"):
        """Initialize with a specific logger."""
        self.logger = logging.getLogger(logger_name)
    
    def log_api_call(
        self,
        method: str,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        response: Any,
        duration_ms: float,
        agent_name: str = "Unknown"
    ) -> None:
        """
        Log a complete OpenAI API interaction.
        
        Args:
            method: API method (e.g., 'chat.completions.parse')
            messages: Request messages
            model: Model used
            temperature: Temperature setting
            max_tokens: Max tokens setting
            response: API response object
            duration_ms: Request duration in milliseconds
            agent_name: Name of the agent making the call
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "method": method,
            "request": {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": messages
            },
            "response": self._extract_response_data(response),
            "duration_ms": duration_ms
        }
        
        # Log as structured JSON for easy parsing
        self.logger.info("=" * 80)
        self.logger.info(f"OpenAI API Call - {agent_name}")
        self.logger.info("=" * 80)
        self.logger.info(f"Request Messages ({len(messages)} messages):")
        for i, msg in enumerate(messages):
            # For FinalReportAgent, log full content; for others, truncate at 200 chars
            if agent_name == "FinalReportAgent":
                self.logger.info(f"  [{i+1}] {msg['role'].upper()}: \n{msg['content']}")
            else:
                self.logger.info(f"  [{i+1}] {msg['role'].upper()}: {msg['content'][:200]}{'...' if len(msg['content']) > 200 else ''}")
        
        response_data = self._extract_response_data(response)
        if response_data.get('content'):
            self.logger.info(f"Response Content: {response_data['content']}")
        
        if response_data.get('usage'):
            usage = response_data['usage']
            self.logger.info(f"Token Usage - Prompt: {usage.get('prompt_tokens', 0)}, "
                           f"Completion: {usage.get('completion_tokens', 0)}, "
                           f"Total: {usage.get('total_tokens', 0)}")
        
        self.logger.info(f"Duration: {duration_ms:.2f}ms | Model: {model} | Temp: {temperature}")
        self.logger.info("=" * 80)
        
        # Also log the full structured data for programmatic access
        self.logger.debug(f"FULL_API_LOG: {json.dumps(log_entry, indent=2)}")
    
    def _extract_response_data(self, response: Any) -> Dict[str, Any]:
        """Extract relevant data from OpenAI response object."""
        if not response:
            return {}
        
        try:
            data = {
                "id": getattr(response, 'id', None),
                "model": getattr(response, 'model', None),
                "created": getattr(response, 'created', None)
            }
            
            # Extract usage information
            if hasattr(response, 'usage') and response.usage:
                data["usage"] = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            
            # Extract message content - handle both GPT-5 responses API and traditional chat completions
            if hasattr(response, 'output') and response.output:
                # GPT-5 responses API format
                for output_item in response.output:
                    if hasattr(output_item, 'type') and output_item.type == 'message':
                        if hasattr(output_item, 'content') and output_item.content:
                            for content_item in output_item.content:
                                if hasattr(content_item, 'text'):
                                    data["content"] = content_item.text
                                    break
                        break
            elif hasattr(response, 'choices') and response.choices:
                # Traditional chat completions format
                choice = response.choices[0]
                if hasattr(choice, 'message'):
                    message = choice.message
                    if hasattr(message, 'content') and message.content:
                        data["content"] = message.content
                    elif hasattr(message, 'parsed') and message.parsed:
                        # For structured outputs
                        data["content"] = str(message.parsed)
                    if hasattr(message, 'refusal') and message.refusal:
                        data["refusal"] = message.refusal
            
            return data
        except Exception as e:
            self.logger.warning(f"Failed to extract response data: {e}")
            return {"error": str(e)}


def log_openai_call(agent_name: str = "Unknown", logger_name: str = "openai_api"):
    """
    Decorator to automatically log OpenAI API calls.
    
    Args:
        agent_name: Name of the agent making the call
        logger_name: Name of the logger to use
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            openai_logger = OpenAILogger(logger_name)
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                # Try to extract call details from the function context
                # This works for methods that call OpenAI API
                if hasattr(args[0], 'client') and 'messages' in kwargs:
                    openai_logger.log_api_call(
                        method=func.__name__,
                        messages=kwargs.get('messages', []),
                        model=kwargs.get('model', 'unknown'),
                        temperature=kwargs.get('temperature', 0),
                        max_tokens=kwargs.get('max_completion_tokens'),
                        response=result,
                        duration_ms=duration_ms,
                        agent_name=agent_name
                    )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                openai_logger.logger.error(f"OpenAI API call failed in {agent_name}: {str(e)} (took {duration_ms:.2f}ms)")
                raise
                
        return wrapper
    return decorator


# Global logger instance
openai_logger = OpenAILogger()