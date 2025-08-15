"""Repository parser for extracting and processing code files."""

import os
import pathlib
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
import magic
import pathspec
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class CodeFile:
    """Represents a code file with metadata."""
    path: str
    content: str
    language: str
    size: int
    relative_path: str
    filename: str
    directory: str


class RepositoryParser:
    """Parses code repositories and extracts relevant files."""
    
    # Common file extensions for different programming languages
    LANGUAGE_EXTENSIONS = {
        '.py': 'python',
        '.js': 'javascript', 
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.rb': 'ruby',
        '.go': 'go',
        '.rs': 'rust',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.clj': 'clojure',
        '.sh': 'shell',
        '.bash': 'shell',
        '.zsh': 'shell',
        '.fish': 'shell',
        '.ps1': 'powershell',
        '.r': 'r',
        '.R': 'r',
        '.sql': 'sql',
        '.html': 'html',
        '.htm': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.less': 'less',
        '.xml': 'xml',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'ini',
        '.conf': 'config',
        '.md': 'markdown',
        '.rst': 'restructuredtext',
        '.txt': 'text',
        '.dockerfile': 'dockerfile',
        '.makefile': 'makefile',
        '.gradle': 'gradle',
        '.maven': 'maven',
    }
    
    # Common directories to ignore
    DEFAULT_IGNORE_DIRS = {
        '.git', '.svn', '.hg', '.bzr',
        'node_modules', '__pycache__', '.pytest_cache',
        'target', 'build', 'dist', 'out',
        '.venv', 'venv', 'env', '.env',
        '.idea', '.vscode', '.settings',
        'coverage', '.coverage', '.nyc_output',
        'logs', 'log', 'tmp', 'temp',
        '.DS_Store', 'Thumbs.db'
    }
    
    # Binary file extensions to ignore
    BINARY_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib', '.a', '.lib',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
        '.mp3', '.mp4', '.avi', '.mkv', '.mov',
        '.ttf', '.otf', '.woff', '.woff2', '.eot'
    }

    def __init__(self, max_file_size: int = 1024*1024):  # 1MB default
        """Initialize repository parser.
        
        Args:
            max_file_size: Maximum file size in bytes to process
        """
        self.max_file_size = max_file_size
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
            length_function=len,
        )
        
    def _should_ignore_directory(self, dir_path: str) -> bool:
        """Check if directory should be ignored."""
        dir_name = os.path.basename(dir_path)
        return dir_name in self.DEFAULT_IGNORE_DIRS
        
    def _get_language_from_extension(self, file_path: str) -> Optional[str]:
        """Get programming language from file extension."""
        ext = pathlib.Path(file_path).suffix.lower()
        return self.LANGUAGE_EXTENSIONS.get(ext)
        
    def _is_binary_file(self, file_path: str) -> bool:
        """Check if file is binary."""
        ext = pathlib.Path(file_path).suffix.lower()
        if ext in self.BINARY_EXTENSIONS:
            return True
            
        try:
            # Use python-magic to detect file type
            mime = magic.from_file(file_path, mime=True)
            return not mime.startswith('text/')
        except:
            # Fallback: try to read as text
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.read(1024)  # Read first 1KB
                return False
            except (UnicodeDecodeError, OSError):
                return True
                
    def _read_gitignore(self, repo_path: str) -> Optional[pathspec.PathSpec]:
        """Read .gitignore file and return pathspec."""
        gitignore_path = os.path.join(repo_path, '.gitignore')
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    return pathspec.PathSpec.from_lines('gitwildmatch', f)
            except:
                pass
        return None
        
    def parse_repository(self, repo_path: str) -> List[CodeFile]:
        """Parse repository and extract all code files.
        
        Args:
            repo_path: Absolute path to repository root
            
        Returns:
            List of CodeFile objects
        """
        if not os.path.isdir(repo_path):
            raise ValueError(f"Repository path does not exist: {repo_path}")
            
        code_files = []
        gitignore_spec = self._read_gitignore(repo_path)
        
        for root, dirs, files in os.walk(repo_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if not self._should_ignore_directory(os.path.join(root, d))]
            
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, repo_path)
                
                # Skip files matching gitignore
                if gitignore_spec and gitignore_spec.match_file(relative_path):
                    continue
                    
                # Skip binary files
                if self._is_binary_file(file_path):
                    continue
                    
                # Skip files that are too large
                try:
                    file_size = os.path.getsize(file_path)
                    if file_size > self.max_file_size or file_size == 0:
                        continue
                except OSError:
                    continue
                    
                # Get language from extension
                language = self._get_language_from_extension(file_path)
                if not language:
                    continue
                    
                # Read file content
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                    if content.strip():  # Skip empty files
                        code_file = CodeFile(
                            path=file_path,
                            content=content,
                            language=language,
                            size=file_size,
                            relative_path=relative_path,
                            filename=file,
                            directory=os.path.dirname(relative_path)
                        )
                        code_files.append(code_file)
                        
                except (OSError, UnicodeDecodeError):
                    continue
                    
        return code_files
        
    def create_documents(self, code_files: List[CodeFile]) -> List[Document]:
        """Convert code files to LangChain documents with chunking.
        
        Args:
            code_files: List of CodeFile objects
            
        Returns:
            List of Document objects
        """
        documents = []
        
        for code_file in code_files:
            # Create metadata
            metadata = {
                'source': code_file.path,
                'filename': code_file.filename,
                'directory': code_file.directory,
                'relative_path': code_file.relative_path,
                'language': code_file.language,
                'size': code_file.size,
                'type': 'code'
            }
            
            # Split content into chunks
            chunks = self.text_splitter.split_text(code_file.content)
            
            for i, chunk in enumerate(chunks):
                chunk_metadata = metadata.copy()
                chunk_metadata['chunk_id'] = i
                chunk_metadata['total_chunks'] = len(chunks)
                
                documents.append(Document(
                    page_content=chunk,
                    metadata=chunk_metadata
                ))
                
        return documents