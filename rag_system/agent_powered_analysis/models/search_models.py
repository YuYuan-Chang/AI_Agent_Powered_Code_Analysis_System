"""
Pydantic models for search results using OpenAI Structured Outputs.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from dataclasses import dataclass
import logging
import json
import os
from datetime import datetime


class CodeElement(BaseModel):
    """Represents a single code element found in search results."""
    name: str = Field(description="Name of the code element")
    type: str = Field(description="Type of element (CLASS, FUNCTION, METHOD, etc.)")
    file_path: str = Field(description="File path where the element is located")
    description: Optional[str] = Field(description="Brief description of the element", default=None)
    

class SearchSection(BaseModel):
    """Represents a section of the formatted search results."""
    title: str = Field(description="Section title")
    elements: List[CodeElement] = Field(description="Code elements in this section")
    summary: Optional[str] = Field(description="Summary of this section", default=None)


class SearchResultFormatted(BaseModel):
    """
    Structured response for formatted search results.
    
    This model ensures consistent formatting of search results
    with proper sections and summaries.
    """
    title: str = Field(description="Main title for the search results")
    sections: List[SearchSection] = Field(description="Organized sections of results")
    summary: str = Field(description="Overall summary of the findings")
    total_results: int = Field(description="Total number of results found", ge=0)
    key_findings: List[str] = Field(description="List of key findings or insights")
    suggestions: Optional[List[str]] = Field(
        description="Suggestions for follow-up queries or related searches",
        default=None
    )


@dataclass
class SearchIteration:
    """Represents a single iteration in the search pipeline."""
    iteration_number: int
    nl_intent: str
    cypher_query: str
    result_summary: str  # Natural language summary instead of raw QueryResult
    records_count: int  # Keep track of result count for metrics
    execution_time_ms: float  # Keep execution time for performance tracking
    sufficient: bool
    confidence: float
    feedback: Optional[str] = None
    query_success: bool = True  # Track if the query executed successfully
    rag_summary: Optional[str] = None  # RAG-based search results summary
    rag_documents_count: int = 0  # Number of RAG documents found


@dataclass
class SearchResult:
    """Final result from the iterative search pipeline."""
    original_query: str
    iterations: List[SearchIteration]
    final_answer: str
    success: bool
    total_execution_time_ms: float
    error_message: Optional[str] = None
    records: List[Dict[str, Any]] = None  # Raw records from all successful queries
    
    def save_to_file(self, output_path: str, format: str = "md") -> bool:
        """
        Save the final report to a file.
        
        Args:
            output_path: Path where to save the results
            format: Output format ('md' for markdown report, 'json' for JSON with extracted code)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            
            if format.lower() == 'json':
                self._save_as_json(output_path)
            elif format.lower() == 'txt' or format.lower() == 'text':
                self._save_as_text(output_path)
            else:  # Default to markdown
                self._save_as_markdown(output_path)
            
            return True
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to save results to {output_path}: {str(e)}")
            return False
    
    def _extract_code_from_record(self, record: Dict[str, Any]) -> str:
        """Extract actual code content from a record."""
        try:
            # Look for code field with encoded location information
            if 'code' in record and isinstance(record['code'], str):
                code_ref = record['code']
                # Parse <CODE>{"S":start,"E":end,"F":"filepath"}</CODE> format
                if code_ref.startswith('<CODE>') and code_ref.endswith('</CODE>'):
                    json_str = code_ref[6:-7]  # Remove <CODE> and </CODE>
                    try:
                        code_info = json.loads(json_str)
                        file_path = code_info.get('F')
                        start_line = code_info.get('S')
                        end_line = code_info.get('E')
                        
                        if file_path and start_line is not None and end_line is not None:
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    lines = f.readlines()
                                    # Convert to 0-based indexing and extract lines
                                    start_idx = max(0, start_line - 1)
                                    end_idx = min(len(lines), end_line)
                                    code_lines = lines[start_idx:end_idx]
                                    return ''.join(code_lines).rstrip()
                            except (IOError, OSError):
                                return f"Could not read file: {file_path}"
                    except json.JSONDecodeError:
                        pass
            return "No code available"
        except Exception:
            return "Error extracting code"
    
    def _save_as_json(self, output_path: str):
        """Save results in JSON format."""
        # Process records to include actual extracted code
        enhanced_records = []
        if self.records:
            for record in self.records:
                enhanced_record = dict(record)
                # Add extracted code to the record
                enhanced_record['extracted_code'] = self._extract_code_from_record(record)
                enhanced_records.append(enhanced_record)
        
        result_data = {
            "timestamp": datetime.now().isoformat(),
            "original_query": self.original_query,
            "success": self.success,
            "total_execution_time_ms": self.total_execution_time_ms,
            "final_answer": self.final_answer,
            "error_message": self.error_message,
            "records": enhanced_records,  # Include raw records with extracted code
            "iterations": [
                {
                    "iteration_number": iter.iteration_number,
                    "nl_intent": iter.nl_intent,
                    "cypher_query": iter.cypher_query,
                    "sufficient": iter.sufficient,
                    "confidence": iter.confidence,
                    "feedback": iter.feedback,
                    "records_found": iter.records_count,
                    "execution_time_ms": iter.execution_time_ms,
                    "query_success": iter.query_success,
                    "result_summary": iter.result_summary
                }
                for iter in self.iterations
            ]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    def _save_as_text(self, output_path: str):
        """Save results in human-readable text format."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("SEARCH RESULTS\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Original Query: {self.original_query}\n")
            f.write(f"Success: {self.success}\n")
            f.write(f"Total Execution Time: {self.total_execution_time_ms:.2f}ms\n")
            f.write(f"Number of Iterations: {len(self.iterations)}\n\n")
            
            if self.error_message:
                f.write(f"Error: {self.error_message}\n\n")
            
            f.write("FINAL ANSWER:\n")
            f.write("-" * 40 + "\n")
            f.write(f"{self.final_answer}\n\n")
            
            f.write("ITERATION DETAILS:\n")
            f.write("-" * 40 + "\n")
            for iter in self.iterations:
                f.write(f"\n--- Iteration {iter.iteration_number} ---\n")
                f.write(f"Intent: {iter.nl_intent}\n")
                f.write(f"Confidence: {iter.confidence:.2f}\n")
                f.write(f"Sufficient: {iter.sufficient}\n")
                if iter.feedback:
                    f.write(f"Feedback: {iter.feedback}\n")
                f.write(f"Records Found: {iter.records_count}\n")
                f.write(f"Execution Time: {iter.execution_time_ms:.2f}ms\n")
                
                if iter.query_success and iter.result_summary:
                    f.write("Result Summary:\n")
                    f.write(f"  {iter.result_summary}\n")
                
                f.write(f"\nCypher Query:\n{iter.cypher_query}\n")
    
    def _save_as_markdown(self, output_path: str):
        """Save only the final formatted report as markdown."""
        with open(output_path, 'w', encoding='utf-8') as f:
            # Add metadata header
            f.write(f"---\n")
            f.write(f"title: System Analysis Report\n")
            f.write(f"generated: {datetime.now().isoformat()}\n")
            f.write(f"query: \"{self.original_query}\"\n")
            f.write(f"execution_time: {self.total_execution_time_ms:.2f}ms\n")
            f.write(f"iterations: {len(self.iterations)}\n")
            f.write(f"---\n\n")
            
            # Write the final formatted answer (which is the full report from RESULT_FORMATTING_PROMPT)
            f.write(self.final_answer)