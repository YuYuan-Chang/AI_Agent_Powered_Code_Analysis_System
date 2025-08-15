# Code Repository RAG System

A Retrieval-Augmented Generation (RAG) system for indexing and querying code repositories using OpenAI embeddings and LLM-powered summaries.

## Features

### Part 1: Repository Ingestion
- **Input**: Local absolute path to a code repository
- **Task**: Recursively parse and embed all source code files
- **Output**: Store vector embeddings in cache with file metadata (path, filename, language, etc.)

### Part 2: Query and Retrieval
- **Input**: Natural language query
- **Task**: Semantic search over cached embeddings
- **Output**: LLM-generated summary of relevant code snippets

## Key Components

- **Repository Parser**: Extracts and processes code files with language detection
- **Vector Store**: Cache-based storage using LangChain's InMemoryVectorStore
- **Code Retriever**: Semantic search with filtering capabilities
- **LLM Summarizer**: Generates comprehensive summaries using GPT-4
- **CLI Interface**: Command-line tool for indexing and querying



## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your OpenAI API key:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

## Usage

### Command Line Interface

#### Index a Repository
```bash
python main.py index --repo-path /absolute/path/to/repository
```

#### Search with LLM Summary
```bash
python main.py search --query "how does authentication work"
```

#### Search Raw Documents (No LLM Summary)
```bash
python main.py search-only --query "authentication functions"
```

#### Search with Filters
```bash
# Search in specific language (with summary)
python main.py search --query "database connection" --language python

# Search raw documents in specific directory
python main.py search-only --query "api endpoints" --directory src/api

# Limit number of results
python main.py search --query "error handling" --k 3
python main.py search-only --query "error handling" --k 3
```

#### Check System Status
```bash
python main.py status
```

#### Clear Index
```bash
python main.py clear
```


## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Repository      │───▶│ Repository       │───▶│ Vector Store    │
│ (Code Files)    │    │ Parser           │    │ (Cached)        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌──────────────────┐           │
│ User Query      │───▶│ Code Retriever   │◄──────────┘
└─────────────────┘    └──────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌──────────────────┐
│ LLM Summary     │◄───│ Code Summarizer  │
└─────────────────┘    └──────────────────┘
```

## Features

### Smart Repository Parsing
- Automatic language detection
- Respects `.gitignore` files
- Filters binary files and large files
- Handles common project structures

### Intelligent Chunking
- Context-aware text splitting
- Preserves code structure
- Maintains metadata for each chunk

### Advanced Search
- Semantic similarity search
- Filter by programming language
- Filter by directory/path
- Configurable result count

### LLM-Powered Summaries
- Context-aware code explanation
- Highlights relevant code snippets
- Provides implementation insights
- Suggests related searches

### Caching System
- Embeddings cached using LangChain's cache system
- Persistent storage for indexed repositories
- Fast subsequent searches
- Efficient memory usage

## Configuration

### Cache Directory
Default: `./cache`
- Stores vector embeddings
- Stores document metadata
- Reusable across sessions

### File Size Limits
Default: 1MB per file
- Prevents processing of large files
- Configurable in `RepositoryParser`

### Chunk Size
Default: 2000 characters with 200 overlap
- Balances context preservation and search precision
- Configurable in `vector_store.py`

## Error Handling

The system handles various edge cases:
- Missing or invalid repository paths
- Empty repositories
- Binary file detection
- API rate limiting
- Large file filtering
- Permission errors

## Example Output

```
🔍 Search Query: how does user authentication work
📄 Documents Found: 8

📝 Summary:
The authentication system in this repository uses JWT tokens with a middleware-based approach. The main authentication logic is implemented in `auth_middleware.py` where incoming requests are validated against stored JWT tokens. The system supports both session-based and token-based authentication...

📁 Key Files:
  • auth_middleware.py (python)
  • login_handler.py (python)
  • user_model.py (python)
  • auth_utils.js (javascript)

💻 Languages: python, javascript
💡 Suggestions:
  • Try searching within specific languages: python, javascript
  • Consider searching for related terms like 'jwt', 'session', 'login'
```

## Limitations

- Requires OpenAI API access
- Performance depends on repository size
- Memory usage scales with number of indexed files
- Language detection is extension-based
