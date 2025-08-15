# AI Agents - Code Analysis System

A powerful system that combines graph-based code analysis with Retrieval-Augmented Generation (RAG) for comprehensive codebase understanding and exploration.

## Features

- **Graph Database Integration**: Uses Neo4j to store and query code relationships
- **RAG-Based Search**: Vector similarity search across code documents  
- **Multi-Agent Architecture**: Specialized agents for different analysis tasks
- **Iterative Pipeline**: Refines queries until sufficient results are found
- **Dual Search Strategy**: Combines structural (graph) and content (RAG) analysis
- **OpenAI Integration**: Leverages GPT models for intelligent code understanding

## Project Structure

```
ai-agents/
├── agent_powered_analysis/  # Main Agent Powered Analysis package
│   ├── agents/              # AI agents (primary, translator, summary, rag)
│   ├── search/              # Search pipeline implementation
│   ├── graphdb/             # Neo4j integration
│   ├── models/              # Data models
│   └── utils/               # Utilities and prompts
├── rag_system/              # Separate RAG module
│   ├── core/                # Core RAG functionality
│   ├── config/              # RAG configuration
│   └── cache/               # Embedding cache
├── tests/                   # Organized test suite
├── docs/                    # Documentation
└── scripts/                 # Utility scripts
```


## Usage Commands

### 🌐 Agent Powered Analysis System (Primary - Graph + RAG Combined)

**Agent Powered Analysis is the main system** that intelligently combines both graph-based code structure analysis and RAG document search for comprehensive codebase understanding.


#### Interactive Mode (Recommended)
```bash
# Start interactive mode - best way to explore your codebase
python -m agent_powered_analysis --interactive

# In interactive mode, you can:
# - Ask: "what's the overall system design?"
# - Ask: "how does authentication work?"
# - Ask: "find all classes that inherit from BaseModel"
# - Save reports: save my_report.md
# - Auto-save: save
# - Get help: help
# - Exit: exit or quit
```

#### Single Query Execution
```bash
# Basic query - gets results from both graph DB and RAG search
python -m agent_powered_analysis --query "what's the overall system design?"

# Save comprehensive analysis to file
python -m agent_powered_analysis --query "how does user authentication work" --save-results auth_analysis.md

# Find specific code patterns
python -m agent_powered_analysis --query "find all classes that inherit from BaseModel"

# Analyze system architecture
python -m agent_powered_analysis --query "show me the main components and their relationships"

# JSON output format for programmatic use
python -m agent_powered_analysis --query "find all classes" --output-format json

# Specify base path for code extraction
python -m agent_powered_analysis --query "show me the main components" --base-path /path/to/your/code
```


### 🔍 RAG System (Standalone Document Search)

**Use RAG system directly** when you only need document-based search without graph analysis.

#### Index a Repository (Required First Step)
```bash
# Index your current project
python -m rag_system.main index --repo-path /absolute/path/to/your/code

# Index this project
python -m rag_system.main index --repo-path /Users/changyuyuan/Documents/Side_projects/ai-agents
```

#### Check RAG System Status
```bash
python -m rag_system.main status
```

#### Search with AI Summary
```bash
python -m rag_system.main search --query "authentication logic"
python -m rag_system.main search --query "how does the RAG system work"
```

#### Search without AI Summary (faster)
```bash
python -m rag_system.main search-only --query "user authentication implementation"
```

#### Filter by Language
```bash
python -m rag_system.main search --query "database queries" --language python
python -m rag_system.main search --query "API endpoints" --language javascript
```

#### Filter by Directory
```bash
python -m rag_system.main search --query "API endpoints" --directory src/api
python -m rag_system.main search --query "models" --directory agent_powered_analysis/models
```

#### Clear RAG Index
```bash
python -m rag_system.main clear
```



