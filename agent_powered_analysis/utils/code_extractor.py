"""
Code extractor utility for extracting actual source code from files.
Handles the metadata format used in the code property graph.
"""

import json
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path


class CodeExtractor:
    """
    Utility class for extracting source code from files using metadata.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the code extractor.
        
        Args:
            base_path: Optional base path for resolving relative file paths
        """
        self.base_path = Path(base_path) if base_path else None
        self.logger = logging.getLogger(__name__)
        self._file_cache = {}  # Cache file contents to avoid repeated reads
    
    def extract_code_from_metadata(self, code_metadata: str) -> Optional[str]:
        """
        Extract actual source code from the metadata format.
        
        Args:
            code_metadata: String containing code metadata like:
                          '<CODE>{"S":249,"E":253,"F":"/path/to/file"}</CODE>'
        
        Returns:
        
            Extracted source code or None if extraction fails
        """
        try:
            # Parse the metadata format
            metadata = self._parse_code_metadata(code_metadata)
            if not metadata:
                return None
            
            # Extract code from file
            return self._extract_code_from_file(
                file_path=metadata['F'],
                start_line=metadata['S'],
                end_line=metadata['E']
            )
            
        except Exception as e:
            self.logger.error(f"Failed to extract code from metadata: {str(e)}")
            return None
    
    def _parse_code_metadata(self, code_metadata: str) -> Optional[Dict[str, Any]]:
        """
        Parse the code metadata string to extract file path and line numbers.
        
        Args:
            code_metadata: String like '<CODE>{"S":249,"E":253,"F":"/path/to/file"}</CODE>'
        
        Returns:
            Dictionary with S (start line), E (end line), F (file path) or None
        """
        try:
            # Extract JSON from the <CODE>...</CODE> tags
            pattern = r'<CODE>(.*?)</CODE>'
            match = re.search(pattern, code_metadata)
            
            if not match:
                self.logger.warning(f"No <CODE> tags found in: {code_metadata}")
                return None
            
            json_str = match.group(1)
            metadata = json.loads(json_str)
            
            # Validate required fields
            required_fields = ['S', 'E', 'F']
            if not all(field in metadata for field in required_fields):
                self.logger.warning(f"Missing required fields in metadata: {metadata}")
                return None
            
            return metadata
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON from metadata: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing code metadata: {e}")
            return None
    
    def _extract_code_from_file(self, file_path: str, start_line: int, end_line: int) -> Optional[str]:
        """
        Extract code lines from a file.
        
        Args:
            file_path: Path to the source file
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (1-indexed, inclusive)
        
        Returns:
            Extracted source code or None if extraction fails
        """
        try:
            # Resolve file path
            resolved_path = self._resolve_file_path(file_path)
            
            if not resolved_path or not resolved_path.exists():
                self.logger.warning(f"File not found: {file_path} (resolved to: {resolved_path})")
                return None
            
            # Get file contents (with caching)
            file_lines = self._get_file_lines(resolved_path)
            if not file_lines:
                return None
            
            # Validate line numbers
            if start_line < 1 or end_line < start_line or end_line > len(file_lines):
                self.logger.warning(f"Invalid line range: {start_line}-{end_line} for file with {len(file_lines)} lines")
                return None
            
            # Extract the lines (convert to 0-indexed)
            extracted_lines = file_lines[start_line - 1:end_line]
            return '\n'.join(extracted_lines)
            
        except Exception as e:
            self.logger.error(f"Failed to extract code from file {file_path}: {str(e)}")
            return None
    
    def _resolve_file_path(self, file_path: str) -> Optional[Path]:
        """
        Resolve file path, handling both absolute and relative paths.
        
        Args:
            file_path: File path string
        
        Returns:
            Resolved Path object or None if invalid
        """
        try:
            path = Path(file_path)
            
            # If path is absolute and exists, return it
            if path.is_absolute() and path.exists():
                return path
            
            # If we have a base path, try resolving relative to it
            if self.base_path:
                # Handle paths that start with '/' but are actually relative to base_path
                # E.g., "/backend/airweave/..." relative to "/Users/.../airweave"
                if file_path.startswith('/'):
                    # Remove leading slash and try as relative path
                    relative_path = Path(file_path[1:])
                    resolved_path = self.base_path / relative_path
                    if resolved_path.exists():
                        return resolved_path
                
                # Try as normal relative path
                resolved_path = self.base_path / path
                if resolved_path.exists():
                    return resolved_path
                
                # Try removing leading path components to find the file
                for i in range(len(path.parts)):
                    partial_path = Path(*path.parts[i:])
                    resolved_path = self.base_path / partial_path
                    if resolved_path.exists():
                        return resolved_path
            
            # As a last resort, try the path as-is
            if path.exists():
                return path
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error resolving file path {file_path}: {e}")
            return None
    
    def _get_file_lines(self, file_path: Path) -> Optional[list]:
        """
        Get file lines with caching.
        
        Args:
            file_path: Path to the file
        
        Returns:
            List of file lines or None if reading fails
        """
        try:
            file_key = str(file_path)
            
            # Check cache first
            if file_key in self._file_cache:
                return self._file_cache[file_key]
            
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
            
            # Cache the result
            self._file_cache[file_key] = lines
            return lines
            
        except Exception as e:
            self.logger.error(f"Failed to read file {file_path}: {e}")
            return None
    
    def clear_cache(self):
        """Clear the file content cache."""
        self._file_cache.clear()
    
    def set_base_path(self, base_path: str):
        """
        Set or update the base path for resolving relative file paths.
        
        Args:
            base_path: New base path
        """
        self.base_path = Path(base_path)
        # Clear cache when base path changes
        self.clear_cache()


# Example usage:
# extractor = CodeExtractor(base_path="/Users/changyuyuan/Documents/GitHub/airweave")
# code = extractor.extract_code_from_metadata('<CODE>{"S":249,"E":253,"F":"/backend/airweave/platform/configs/config.py"}</CODE>')