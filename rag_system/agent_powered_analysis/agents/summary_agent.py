"""
Implementation Guide Agent for generating step-by-step implementation guides from codebase analysis.
Converts code analysis results into actionable development instructions.
"""

import logging
from typing import List, Dict, Any, Optional
import openai
import time
from ..config import config
from ..graphdb.query_executor import QueryResult
from ..utils.openai_logger import openai_logger


class SummaryAgent:
    """
    Agent responsible for generating step-by-step implementation guides
    from codebase analysis, focusing on actionable development instructions.
    """
    
    def __init__(self, openai_client: Optional[openai.OpenAI] = None):
        """
        Initialize the Implementation Guide Agent.
        
        Args:
            openai_client: Optional OpenAI client instance
        """
        self.openai_client = openai_client or openai.OpenAI(api_key=config.openai.api_key)
        self.logger = logging.getLogger(__name__)
    
    def generate_summary(self, query_result: QueryResult, original_intent: str) -> str:
        """
        Generate a step-by-step implementation guide from codebase analysis.
        
        Args:
            query_result: The codebase analysis results
            original_intent: The original feature implementation request
            
        Returns:
            Detailed implementation guide with step-by-step instructions
        """
        try:
            if not query_result.success:
                return f"Query failed: {query_result.error_message or 'Unknown error'}"
            
            if not query_result.records:
                return "No matching code elements found in the codebase."
            
            # Prepare structured data for implementation guide generation
            structured_data = self._prepare_data_for_summary(query_result.records)
            
            prompt = self._create_summary_prompt(original_intent, structured_data, len(query_result.records))
            messages = [{"role": "user", "content": prompt}]
            
            # Time the API call and log it
            start_time = time.time()
            response = self.openai_client.chat.completions.create(
                model=config.openai.model,
                messages=messages,
                temperature=1.0,
                max_completion_tokens=1500
            )
            duration_ms = (time.time() - start_time) * 1000
            
            # Log the API interaction
            openai_logger.log_api_call(
                method="chat.completions.create",
                messages=messages,
                model=config.openai.model,
                temperature=1.0,
                max_tokens=1500,
                response=response,
                duration_ms=duration_ms,
                agent_name="SummaryAgent"
            )
            
            summary = response.choices[0].message.content.strip()
            
            self.logger.info(f"Generated implementation guide for {len(query_result.records)} analysis results: {len(summary)} characters")
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Summary generation failed: {str(e)}")
            return f"Unable to generate implementation guide: {str(e)}"
    
    def _prepare_data_for_summary(self, records: List[Dict[str, Any]]) -> str:
        """
        Prepare codebase analysis data for implementation guidance by extracting relevant patterns.
        
        Args:
            records: List of codebase analysis records
            
        Returns:
            Structured text representation focusing on implementation context
        """
        if not records:
            return "No data to summarize."
        
        # Group records by type and extract implementation-relevant patterns
        patterns = {
            'classes': [],
            'functions': [],
            'methods': [],
            'modules': [],
            'relationships': [],
            'files': set(),
            'code_samples': [],
            'other': []
        }
        
        for record in records:
            for _, value in record.items():
                if isinstance(value, dict) and 'labels' in value:
                    labels = value.get('labels', [])
                    properties = value.get('properties', {})
                    
                    if 'CLASS' in labels:
                        class_info = {
                            'name': properties.get('name', 'Unknown'),
                            'file': properties.get('file_path', 'Unknown'),
                            'has_code': 'code' in properties and properties['code'],
                            'signature': properties.get('signature', ''),
                            'code': properties.get('code', '')[:500] if properties.get('code') else ''  # First 500 chars for context
                        }
                        patterns['classes'].append(class_info)
                        patterns['files'].add(properties.get('file_path', 'Unknown'))
                        if properties.get('code'):
                            patterns['code_samples'].append({'type': 'class', 'name': properties.get('name'), 'code': properties.get('code')[:300]})
                    
                    elif 'FUNCTION' in labels:
                        func_info = {
                            'name': properties.get('name', 'Unknown'),
                            'file': properties.get('file_path', 'Unknown'),
                            'has_signature': 'signature' in properties,
                            'signature': properties.get('signature', ''),
                            'code': properties.get('code', '')[:500] if properties.get('code') else ''
                        }
                        patterns['functions'].append(func_info)
                        patterns['files'].add(properties.get('file_path', 'Unknown'))
                        if properties.get('code'):
                            patterns['code_samples'].append({'type': 'function', 'name': properties.get('name'), 'code': properties.get('code')[:300]})
                    
                    elif 'METHOD' in labels:
                        method_info = {
                            'name': properties.get('name', 'Unknown'),
                            'class': properties.get('class', 'Unknown'),
                            'file': properties.get('file_path', 'Unknown'),
                            'signature': properties.get('signature', ''),
                            'code': properties.get('code', '')[:500] if properties.get('code') else ''
                        }
                        patterns['methods'].append(method_info)
                        patterns['files'].add(properties.get('file_path', 'Unknown'))
                        if properties.get('code'):
                            patterns['code_samples'].append({'type': 'method', 'name': f"{properties.get('class', 'Unknown')}.{properties.get('name', 'Unknown')}", 'code': properties.get('code')[:300]})
                    
                    elif 'MODULE' in labels:
                        module_info = {
                            'name': properties.get('name', 'Unknown'),
                            'file': properties.get('file_path', 'Unknown')
                        }
                        patterns['modules'].append(module_info)
                        patterns['files'].add(properties.get('file_path', 'Unknown'))
                    
                    else:
                        patterns['other'].append({
                            'labels': labels,
                            'name': properties.get('name', 'Unknown')
                        })
                
                elif isinstance(value, dict) and 'type' in value:
                    # This is a relationship
                    patterns['relationships'].append(value.get('type', 'Unknown'))
        
        # Build structured summary focusing on implementation context
        summary_parts = []
        
        if patterns['classes']:
            class_files = set(c['file'] for c in patterns['classes'])
            summary_parts.append(f"Classes: {len(patterns['classes'])} found across {len(class_files)} files")
            # Add sample class info for context
            if patterns['classes'][:2]:  # Show first 2 classes as examples
                class_examples = [f"{c['name']} ({c['file'].split('/')[-1]})" for c in patterns['classes'][:2]]
                summary_parts.append(f"Example classes: {', '.join(class_examples)}")
            
        if patterns['functions']:
            func_files = set(f['file'] for f in patterns['functions'])
            summary_parts.append(f"Functions: {len(patterns['functions'])} found across {len(func_files)} files")
            if patterns['functions'][:2]:
                func_examples = [f"{f['name']} ({f['file'].split('/')[-1]})" for f in patterns['functions'][:2]]
                summary_parts.append(f"Example functions: {', '.join(func_examples)}")
            
        if patterns['methods']:
            method_classes = set(m['class'] for m in patterns['methods'])
            summary_parts.append(f"Methods: {len(patterns['methods'])} found across {len(method_classes)} classes")
            if patterns['methods'][:2]:
                method_examples = [f"{m['class']}.{m['name']}" for m in patterns['methods'][:2]]
                summary_parts.append(f"Example methods: {', '.join(method_examples)}")
            
        if patterns['modules']:
            summary_parts.append(f"Modules: {len(patterns['modules'])} found")
        
        if patterns['relationships']:
            unique_rel_types = set(patterns['relationships'])
            summary_parts.append(f"Relationships: {len(unique_rel_types)} types ({', '.join(unique_rel_types)})")
        
        if patterns['files']:
            summary_parts.append(f"Files involved: {len(patterns['files'])} total")
        
        if patterns['code_samples']:
            summary_parts.append(f"Code samples available: {len(patterns['code_samples'])} for reference")
        
        return "; ".join(summary_parts) if summary_parts else "Various code elements found for implementation guidance"
    
    def _create_summary_prompt(self, original_intent: str, structured_data: str, total_results: int) -> str:
        """
        Create the prompt for generating step-by-step implementation guides.
        
        Args:
            original_intent: The original feature implementation request
            structured_data: Structured representation of codebase analysis
            total_results: Total number of analysis results
            
        Returns:
            Formatted prompt for generating implementation guide
        """
        prompt = f"""You are a senior software engineer tasked with creating a step-by-step implementation guide for a requested feature based on codebase analysis.

Feature Implementation Request: "{original_intent}"

Codebase Analysis Results:
- Total Analysis Results: {total_results}
- Codebase Context: {structured_data}

You are an expert in software development with deep knowledge of implementation patterns, best practices, and code architecture.

Generate a comprehensive implementation guide that includes:

**🎯 FEATURE IMPLEMENTATION GUIDE**

**1. FEATURE OVERVIEW**
- Brief description of what needs to be implemented
- Key functionality and integration points

**2. CODEBASE CONTEXT**
- Relevant existing code patterns found
- Files and components that will be affected or can serve as templates
- Architectural style observed in the codebase

**3. STEP-BY-STEP IMPLEMENTATION**

For each major implementation step, provide:
- **Step N**: [Clear step name]
- **Goal**: What this step achieves
- **Files to modify/create**: Specific file paths based on existing patterns
- **Implementation approach**: How to implement based on existing codebase patterns
- **Code structure**: General structure/pattern to follow (reference similar existing code)
- **Testing approach**: How to verify this step

**4. INTEGRATION & TESTING**
- How to integrate with existing codebase
- Testing strategy
- Potential issues and solutions

**5. DEPLOYMENT CONSIDERATIONS**
- Any configuration changes needed
- Dependencies to add
- Database changes if applicable

Base your recommendations on the existing codebase patterns and structure. If similar functionality exists, reference it as a template. Provide specific, actionable guidance that a developer can directly follow.

Implementation Guide:"""
        
        return prompt