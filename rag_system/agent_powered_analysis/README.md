# Multi-Agent Code Search Pipeline

**Intelligent code exploration through specialized LLM agents and graph-based reasoning**

A sophisticated multi-agent system that enables natural language search and exploration of codebases using a "Write then Translate" architecture. The system combines specialized LLM agents with Neo4j property graphs to provide deep code understanding and intelligent search capabilities.

## 🚀 Getting Started


### Usage Examples

#### Command Line Interface
```bash
# Analyze overall system architecture with result saving
python -m agent_powered_analysis --query "what's the overall system design of this codebase" --save-results results.md

# Interactive search with detailed logging
python -m agent_powered_analysis --query "Find classes implementing singleton pattern" --log-level DEBUG
```

## 🤖 Agent Design & Architecture

### Multi-Agent System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Multi-Agent Pipeline                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐     ┌────────────┐ │
│  │ Primary Agent   │────▶│ Translator      │────▶│ Executor   │ │
│  │ (Understanding) │     │ Agent (Cypher)  │     │ & Analysis │ │
│  └─────────────────┘     └─────────────────┘     └────────────┘ │
│           │                        │                     │      │
│           ▼                        ▼                     ▼      │
│  ┌─────────────────┐     ┌─────────────────┐     ┌────────────┐ │
│  │ Intent          │     │ Cypher Query    │     │ Results    │ │
│  │ Structuring     │     │ Generation      │     │ Evaluation │ │
│  └─────────────────┘     └─────────────────┘     └────────────┘ │
│                                                         │       │
│                                                         ▼       │
│                                             ┌─────────────────┐ │
│                                             │ Summary         │ │
│                                             │ Synthesis       │ │
│                                             └─────────────────┘ │  
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                                  │
                        ┌─────────▼─────────┐
                        │ Iterative Control │
                        │ & Refinement Loop │
                        └───────────────────┘
```

### Agent Specialization

#### 1. Primary Agent (Query Understanding)
**Role**: Natural language query analysis and intent extraction
**Capabilities**:
- Semantic understanding of code-related queries
- Context-aware intent structuring
- Ambiguity resolution and query clarification
- Domain-specific terminology mapping

**Design Pattern**: 
```python
class PrimaryAgent:
    def understand_query(self, user_query: str) -> StructuredIntent:
        # Analyze query semantics
        # Extract search targets (classes, methods, relationships)
        # Identify search scope and constraints
        # Produce structured natural language intent
```

#### 2. Translator Agent (Query Translation)
**Role**: Convert natural language intents to formal Cypher queries
**Capabilities**:
- Graph query language expertise
- Schema-aware query construction
- Query optimization and validation
- Complex relationship traversal logic

**Design Pattern**:
```python
class TranslatorAgent:
    def translate_intent(self, structured_intent: str) -> CypherQuery:
        # Parse intent structure
        # Map to graph schema elements
        # Generate optimized Cypher queries
        # Validate query syntax and semantics
```

#### 3. Sufficiency Analyzer (Result Evaluation)
**Role**: Evaluate result completeness and trigger refinements
**Capabilities**:
- Result quality assessment
- Completeness analysis
- Refinement strategy generation
- Iteration control logic

## 🏗️ System Design

### Core Architecture Principles

1. **Separation of Concerns**: Each agent has a single, well-defined responsibility
2. **Iterative Refinement**: Self-improving pipeline with feedback loops
3. **Schema-Aware Processing**: Deep understanding of code property graph structure
4. **Configurable Intelligence**: Tunable agent behavior and pipeline parameters

### Component Interaction Flow

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ User Query  │───▶│ Primary Agent    │───▶│ Structured      │
│ (Natural    │    │ - Semantic       │    │ Intent          │
│ Language)   │    │   Analysis       │    │ (Enhanced NL)   │
└─────────────┘    │ - Intent         │    └─────────────────┘
                   │   Extraction     │              │
                   └──────────────────┘              ▼
                                             ┌─────────────────┐
┌─────────────┐    ┌──────────────────┐    │ Translator      │
│ Formatted   │◀───│ Result Processor │◀───│ Agent           │
│ Answer      │    │ - Answer         │    │ - Schema        │
│             │    │   Formatting     │    │   Mapping       │
└─────────────┘    │ - Context        │    │ - Query         │
                   │   Enhancement    │    │   Generation    │
                   └──────────────────┘    └─────────────────┘
                            ▲                        │
                            │                        ▼
                   ┌──────────────────┐    ┌─────────────────┐
                   │ Summary          │    │ Query Executor  │
                   │ Synthesizer      │    │ - Neo4j         │
                   │ - Key Insights   │    │   Interface     │
                   │ - Pattern        │    │ - Result        │
                   │   Recognition    │    │   Processing    │
                   └──────────────────┘    └─────────────────┘
                            ▲                        │
                            │                        ▼
                   ┌──────────────────┐    ┌─────────────────┐
                   │ Sufficiency      │    │ Result          │
                   │ Analyzer         │    │ Aggregation     │
                   │ - Quality Check  │    │ - Combine       │
                   │ - Completeness   │    │   Iterations    │
                   │ - Refinement     │    │ - Enhance       │
                   └──────────────────┘    └─────────────────┘
```

### Data Flow & State Management

#### Pipeline State Transitions
```
INIT → UNDERSTANDING → TRANSLATION → EXECUTION → ANALYSIS → [REFINEMENT] → COMPLETION
  │         │              │            │           │            │            │
  │         ▼              ▼            ▼           ▼            ▼            ▼
  │    Intent Gen     Cypher Gen    Query Exec   Result Eval  Query Refine  Answer Format
```

#### Information Flow Between Agents
- **Primary → Translator**: Structured intent with semantic annotations
- **Translator → Executor**: Validated Cypher queries with metadata
- **Executor → Analyzer**: Raw results with execution statistics
- **Analyzer → Pipeline**: Sufficiency scores and refinement suggestions

## 🔄 Workflow Design

### Iterative Pipeline Process

#### Phase 1: Initial Processing
1. **Query Ingestion**: Receive and preprocess natural language query
2. **Intent Analysis**: Primary Agent extracts semantic meaning and search targets
3. **Query Generation**: Translator Agent produces initial Cypher query
4. **Execution**: Query Executor runs against Neo4j graph database

#### Phase 2: Result Evaluation
1. **Result Analysis**: Evaluate returned data completeness and relevance
2. **Sufficiency Scoring**: Calculate confidence score for result adequacy
3. **Decision Point**: Determine if results satisfy original query intent

#### Phase 3: Refinement Loop (If Needed)
1. **Gap Analysis**: Identify what information is missing or incomplete
2. **Strategy Generation**: Determine refinement approach (broaden, narrow, pivot)
3. **Query Modification**: Generate improved Cypher queries
4. **Re-execution**: Run refined queries with updated parameters

#### Phase 4: Final Processing
1. **Result Aggregation**: Combine results from all iterations
2. **Context Enhancement**: Add relevant metadata and relationships
3. **Summary Process**: Synthesize findings into key insights and patterns
4. **Answer Formatting**: Structure final response for human consumption

### Workflow Control Logic

```python
class IterativePipeline:
    def search(self, query: str) -> SearchResult:
        iteration = 0
        current_results = None
        
        while iteration < MAX_ITERATIONS:
            # Agent coordination
            intent = self.primary_agent.understand_query(query, current_results)
            cypher = self.translator_agent.translate(intent)
            results = self.executor.execute(cypher)
            
            # Sufficiency analysis
            sufficiency = self.analyze_sufficiency(query, results, iteration)
            
            if sufficiency.score >= THRESHOLD:
                return self.format_final_answer(results, sufficiency)
            
            # Refinement preparation
            current_results = results
            iteration += 1
        
        return self.format_final_answer(current_results, sufficiency)
```

### Decision Points & Control Flow

#### Sufficiency Evaluation Criteria
- **Coverage**: Does the result address all aspects of the query?
- **Depth**: Is the level of detail appropriate for the question?
- **Accuracy**: Are the returned relationships and data correct?
- **Completeness**: Are there obvious gaps in the information?

#### Refinement Strategies
- **Scope Expansion**: Broaden search to include related entities
- **Scope Narrowing**: Focus on specific aspects that were unclear
- **Relationship Exploration**: Investigate connected nodes and edges
- **Alternative Paths**: Try different graph traversal approaches

## 🔧 Technical Implementation

### Agent Communication Protocol
```python
@dataclass
class AgentMessage:
    agent_id: str
    message_type: MessageType
    content: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: datetime
```

### Pipeline Configuration
```python
PIPELINE_CONFIG = {
    'max_iterations': 3,
    'sufficiency_threshold': 0.8,
    'refinement_strategies': ['expand', 'narrow', 'pivot'],
    'agent_timeouts': {
        'primary': 30,
        'translator': 45,
        'analyzer': 15
    }
}
```

### Graph Schema Design
```cypher
// Code Property Graph Schema
CREATE CONSTRAINT FOR (m:MODULE) REQUIRE m.name IS UNIQUE;
CREATE CONSTRAINT FOR (c:CLASS) REQUIRE (c.name, c.file_path) IS UNIQUE;
CREATE INDEX FOR (f:FUNCTION) ON (f.name);
CREATE INDEX FOR (m:METHOD) ON (m.class, m.name);
```

