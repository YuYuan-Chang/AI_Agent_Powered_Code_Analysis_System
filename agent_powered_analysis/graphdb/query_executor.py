"""
Query executor for running Cypher queries and returning structured results.
Handles query execution, result processing, and error handling.
"""

import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from neo4j import Record
from .neo4j_connector import Neo4jConnector
from ..utils.code_extractor import CodeExtractor


@dataclass
class QueryResult:
    """
    Structured result from a Cypher query execution.
    """
    records: List[Dict[str, Any]]
    summary: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None
    query: Optional[str] = None
    execution_time_ms: Optional[float] = None


class QueryExecutor:
    """
    Executes Cypher queries and processes results into structured formats.
    """
    
    def __init__(self, connector: Optional[Neo4jConnector] = None, base_path: Optional[str] = None):
        """
        Initialize the query executor.
        
        Args:
            connector: Optional Neo4j connector instance. If None, creates a new one.
            base_path: Optional base path for resolving source code file paths
        """
        self.connector = connector or Neo4jConnector()
        self.logger = logging.getLogger(__name__)
        self.code_extractor = CodeExtractor(base_path=base_path)
    
    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> QueryResult:
        """
        Execute a Cypher query and return structured results.
        
        Args:
            query: Cypher query string
            parameters: Optional query parameters
            
        Returns:
            QueryResult object containing processed results
        """
        try:
            import time
            start_time = time.time()
            
            self.logger.info(f"Executing query: {query}")
            
            # Execute the query
            records = self.connector.execute_query(query, parameters)
            
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Process results
            processed_records = self._process_records(records)
            
            # Create summary
            summary = self._create_summary(records, query, execution_time)
            
            result = QueryResult(
                records=processed_records,
                summary=summary,
                success=True,
                query=query,
                execution_time_ms=execution_time
            )
            
            self.logger.info(f"Query executed successfully. Found {len(processed_records)} results in {execution_time:.2f}ms")
            return result
            
        except Exception as e:
            self.logger.error(f"Query execution failed: {str(e)}")
            
            return QueryResult(
                records=[],
                summary={"error": str(e)},
                success=False,
                error_message=str(e),
                query=query
            )
    
    def execute_batch(self, queries: List[str], parameters_list: Optional[List[Dict[str, Any]]] = None) -> List[QueryResult]:
        """
        Execute multiple queries in batch.
        
        Args:
            queries: List of Cypher query strings
            parameters_list: Optional list of parameter dictionaries for each query
            
        Returns:
            List of QueryResult objects
        """
        if parameters_list and len(parameters_list) != len(queries):
            raise ValueError("Parameters list length must match queries list length")
        
        results = []
        for i, query in enumerate(queries):
            params = parameters_list[i] if parameters_list else None
            result = self.execute(query, params)
            results.append(result)
        
        return results
    
    def _process_records(self, records: List[Record]) -> List[Dict[str, Any]]:
        """
        Process Neo4j records into Python dictionaries.
        
        Args:
            records: List of Neo4j Record objects
            
        Returns:
            List of dictionaries with processed data
        """
        processed = []
        
        for record in records:
            processed_record = {}
            
            for key in record.keys():
                value = record[key]
                processed_record[key] = self._process_value(value)
            
            processed.append(processed_record)
        
        return processed
    
    def _process_value(self, value: Any) -> Any:
        """
        Process individual values from Neo4j records.
        
        Args:
            value: Value from Neo4j record
            
        Returns:
            Processed Python value
        """
        # print(f"\n📄 PROCESSING VALUE:")
        # print("-" * 50)
        # print(value)
        # print("-" * 50)
        # Handle primitive strings that might contain code metadata
        if isinstance(value, str) and value.startswith('<CODE>'):
            extracted_code = self._extract_code_content(value, "primitive_string", ["unknown"])
            # print(f"\n📄 EXTRACTED CODE:")
            # print("-" * 50)
            # print(extracted_code)
            # print("-" * 50)
            return extracted_code
        # Handle Neo4j nodes
        # if hasattr(value, 'labels') and hasattr(value, 'items'):
        #     properties = dict(value.items())
        #     node_labels = list(value.labels)
        #     node_name = properties.get('name', 'unknown')
            
        #     # Extract actual code content if code property contains metadata
        #     if 'code' in properties:
        #         self.logger.info(f"Processing node with code attribute: {':'.join(node_labels)} '{node_name}' (ID: {value.id})")
        #         original_code = properties['code']
        #         extracted_code = self._extract_code_content(properties['code'], node_name, node_labels)
        #         properties['code'] = extracted_code
                
        #         # Log success/failure of code extraction
        #         if extracted_code != original_code and isinstance(extracted_code, str):
        #             print(f"\n📄 EXTRACTED CODE:")
        #             print("-" * 50)
        #             print(extracted_code)
        #             print("-" * 50)
        #             self.logger.info(f"✅ Code extraction successful for {':'.join(node_labels)} '{node_name}': {len(extracted_code)} characters extracted")
        #         else:
        #             self.logger.info(f"⚠️  Code extraction not performed for {':'.join(node_labels)} '{node_name}': using original value")
            
        #     # Convert relative file_path to absolute path
        #     if 'file_path' in properties:
        #         properties['file_path'] = self._resolve_to_absolute_path(properties['file_path'])
        #     return {
        #         'labels': node_labels,
        #         'properties': properties,
        #         'id': value.id
        #     }
        
        # # Handle Neo4j relationships
        # if hasattr(value, 'type') and hasattr(value, 'start_node'):
        #     return {
        #         'type': value.type,
        #         'properties': dict(value.items()),
        #         'start_node_id': value.start_node.id,
        #         'end_node_id': value.end_node.id,
        #         'id': value.id
        #     }
        
        # # Handle Neo4j paths
        # if hasattr(value, 'nodes') and hasattr(value, 'relationships'):
        #     return {
        #         'nodes': [self._process_value(node) for node in value.nodes],
        #         'relationships': [self._process_value(rel) for rel in value.relationships],
        #         'length': len(value.relationships)
        #     }
        
        # # Handle lists
        # if isinstance(value, list):
        #     return [self._process_value(item) for item in value]
        
        # # Handle dictionaries
        # if isinstance(value, dict):
        #     return {k: self._process_value(v) for k, v in value.items()}
        
        
        
        # Return primitive types as-is
        return value
    
    def _extract_code_content(self, code_value: Any, node_name: str = "unknown", node_labels: list = None) -> Any:
        """
        Extract actual code content from metadata if applicable.
        
        Args:
            code_value: The value of a 'code' property, could be metadata or actual code
            node_name: Name of the node being processed (for logging)
            node_labels: Labels of the node being processed (for logging)
        
        Returns:
            Actual source code if extraction is possible, otherwise the original value
        """
        # Only process string values that look like metadata
        if not isinstance(code_value, str) or not code_value.startswith('<CODE>'):
            self.logger.debug(f"Skipping code extraction for {':'.join(node_labels or [])} '{node_name}': not metadata format")
            return code_value
        
        try:
            self.logger.debug(f"Attempting code extraction for {':'.join(node_labels or [])} '{node_name}' from metadata: {code_value[:100]}...")
            
            # Extract actual code using the code extractor
            extracted_code = self.code_extractor.extract_code_from_metadata(code_value)
            
            # If extraction succeeded, return the actual code
            if extracted_code is not None:
                # print(f"\n📄 EXTRACTED CODE:")
                # print("-" * 50)
                # print(extracted_code)
                # print("-" * 50)
                # Parse metadata to get file info for logging
                import json
                import re
                try:
                    pattern = r'<CODE>(.*?)</CODE>'
                    match = re.search(pattern, code_value)
                    if match:
                        metadata = json.loads(match.group(1))
                        file_path = metadata.get('F', 'unknown')
                        line_range = f"{metadata.get('S', '?')}-{metadata.get('E', '?')}"
                        self.logger.info(f"📄 Code extracted from {file_path} lines {line_range} for {':'.join(node_labels or [])} '{node_name}': {len(extracted_code)} chars")
                except:
                    self.logger.info(f"📄 Code extracted for {':'.join(node_labels or [])} '{node_name}': {len(extracted_code)} characters")
                
                return extracted_code
            else:
                self.logger.warning(f"❌ Failed to extract code from metadata for {':'.join(node_labels or [])} '{node_name}': {code_value[:100]}...")
                return code_value
                
        except Exception as e:
            self.logger.error(f"❌ Error extracting code content for {':'.join(node_labels or [])} '{node_name}': {str(e)}")
            return code_value
    
    def _resolve_to_absolute_path(self, file_path: str) -> str:
        """
        Convert relative file paths to absolute paths using the code extractor's base path.
        
        Args:
            file_path: The file path (could be relative or absolute)
            
        Returns:
            Absolute file path if resolution is successful, otherwise the original path
        """
        try:
            # If already absolute and exists, return as-is
            from pathlib import Path
            path = Path(file_path)
            if path.is_absolute() and path.exists():
                return str(path)
            
            # Try to resolve using the code extractor's logic
            if self.code_extractor.base_path:
                resolved_path = self.code_extractor._resolve_file_path(file_path)
                if resolved_path and resolved_path.exists():
                    return str(resolved_path.resolve())
            
            # If we can't resolve it, return the original path
            self.logger.debug(f"Could not resolve path to absolute: {file_path}")
            return file_path
            
        except Exception as e:
            self.logger.warning(f"Error resolving file path {file_path}: {str(e)}")
            return file_path
    
    def _create_summary(self, records: List[Record], query: str, execution_time: float) -> Dict[str, Any]:
        """
        Create a summary of query execution results.
        
        Args:
            records: List of Neo4j records
            query: The executed query
            execution_time: Execution time in milliseconds
            
        Returns:
            Summary dictionary
        """
        summary = {
            'total_records': len(records),
            'execution_time_ms': execution_time,
            'query_type': self._determine_query_type(query)
        }
        
        if records:
            # Analyze the structure of returned data
            first_record = records[0]
            summary['returned_fields'] = list(first_record.keys())
            
            # Count different types of returned objects
            field_types = {}
            for key in first_record.keys():
                value = first_record[key]
                field_types[key] = self._get_value_type(value)
            
            summary['field_types'] = field_types
        
        return summary
    
    def _determine_query_type(self, query: str) -> str:
        """
        Determine the type of query based on its content.
        
        Args:
            query: Cypher query string
            
        Returns:
            Query type string
        """
        query_upper = query.upper().strip()
        
        if query_upper.startswith('MATCH'):
            return 'read'
        elif query_upper.startswith('CREATE'):
            return 'create'
        elif query_upper.startswith('MERGE'):
            return 'merge'
        elif query_upper.startswith('DELETE'):
            return 'delete'
        elif query_upper.startswith('SET'):
            return 'update'
        else:
            return 'unknown'
    
    def _get_value_type(self, value: Any) -> str:
        """
        Get the type description of a value from Neo4j.
        
        Args:
            value: Value to analyze
            
        Returns:
            Type description string
        """
        if hasattr(value, 'labels'):
            return 'node'
        elif hasattr(value, 'type') and hasattr(value, 'start_node'):
            return 'relationship'
        elif hasattr(value, 'nodes') and hasattr(value, 'relationships'):
            return 'path'
        elif isinstance(value, list):
            return 'list'
        elif isinstance(value, dict):
            return 'map'
        else:
            return type(value).__name__
    
    def format_results_for_display(self, result: QueryResult) -> str:
        """
        Format query results for human-readable display.
        
        Args:
            result: QueryResult object to format
            
        Returns:
            Formatted string representation of results
        """
        if not result.success:
            return f"Query failed: {result.error_message}"
        
        if not result.records:
            return "No results found."
        
        lines = []
        lines.append(f"Found {len(result.records)} results (executed in {result.execution_time_ms:.2f}ms):")
        lines.append("")
        
        for record in result.records:
            for key, value in record.items():
                lines.append(f"{key}: {self._format_value_for_display(value)}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_value_for_display(self, value: Any, indent: int = 4) -> str:
        """
        Format a value for human-readable display.
        
        Args:
            value: Value to format
            indent: Indentation level
            
        Returns:
            Formatted string
        """
        if isinstance(value, dict):
            if 'labels' in value and 'properties' in value:
                # This is a node
                labels = ":".join(value['labels'])
                props = ", ".join(f"{k}={v}" for k, v in value['properties'].items())
                return f"({labels} {{{props}}})"
            else:
                # Regular dictionary
                items = []
                for k, v in value.items():
                    formatted_v = self._format_value_for_display(v, indent + 2)
                    items.append(f"{k}: {formatted_v}")
                return "{" + ", ".join(items) + "}"
        elif isinstance(value, list):
            formatted_items = [self._format_value_for_display(item, indent + 2) for item in value]
            return "[" + ", ".join(formatted_items) + "]"
        else:
            return str(value)