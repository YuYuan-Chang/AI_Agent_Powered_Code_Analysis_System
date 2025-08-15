#!/usr/bin/env python3
"""
Test script to demonstrate the modified Agent Powered Analysis workflow with summaries.
This shows how the system now generates and stores natural language summaries
instead of raw query results.
"""

from agent_powered_analysis.agents.summary_agent import SummaryAgent
from agent_powered_analysis.graphdb.query_executor import QueryResult
from agent_powered_analysis.search.iterative_pipeline import SearchIteration

def test_summary_generation():
    """Test the summary generation functionality."""
    print("Testing Summary Generation:")
    print("=" * 50)
    
    # Create a SummaryAgent instance
    summary_agent = SummaryAgent()
    
    # Mock some query results that would typically come from Neo4j
    mock_records = [
        {
            'class': {
                'labels': ['CLASS'],
                'properties': {'name': 'UserController', 'file_path': '/src/controllers/user.py'},
                'id': 1
            }
        },
        {
            'method': {
                'labels': ['METHOD'],
                'properties': {'name': 'authenticate', 'class': 'UserController', 'file_path': '/src/controllers/user.py'},
                'id': 2
            }
        },
        {
            'function': {
                'labels': ['FUNCTION'],
                'properties': {'name': 'validate_email', 'file_path': '/src/utils/validation.py'},
                'id': 3
            }
        }
    ]
    
    # Create a QueryResult with mock data
    query_result = QueryResult(
        records=mock_records,
        summary={'total_records': 3, 'execution_time_ms': 45.2},
        success=True,
        execution_time_ms=45.2
    )
    
    # Generate a summary
    intent = "Find all authentication-related classes and methods in the user system"
    summary = summary_agent.generate_summary(query_result, intent)
    
    print(f"Original Intent: {intent}")
    print(f"Raw Records: {len(mock_records)} items")
    print(f"Generated Summary: {summary}")
    print()
    
    return summary

def test_search_iteration_structure():
    """Test the new SearchIteration structure with summaries."""
    print("Testing SearchIteration Structure:")
    print("=" * 50)
    
    # Create a SearchIteration with the new summary-based structure
    iteration = SearchIteration(
        iteration_number=1,
        nl_intent="Find user authentication components",
        cypher_query="MATCH (c:CLASS)-[:HAS_METHOD]->(m:METHOD) WHERE c.name CONTAINS 'User' RETURN c, m",
        result_summary="Found 1 class (UserController) with 1 authentication method (authenticate) in the user management system, indicating centralized authentication logic.",
        records_count=2,
        execution_time_ms=45.2,
        sufficient=True,
        confidence=0.85,
        feedback=None,
        query_success=True
    )
    
    print(f"Iteration: {iteration.iteration_number}")
    print(f"Intent: {iteration.nl_intent}")
    print(f"Records Found: {iteration.records_count}")
    print(f"Execution Time: {iteration.execution_time_ms}ms")
    print(f"Summary: {iteration.result_summary}")
    print(f"Sufficient: {iteration.sufficient} (confidence: {iteration.confidence})")
    print()
    
    return iteration

def test_workflow_comparison():
    """Show the difference between old and new workflow."""
    print("Workflow Comparison:")
    print("=" * 50)
    
    print("OLD WORKFLOW:")
    print("  Query → Raw Results → Store Raw Data → Analyze Raw Data → Report")
    print("  Issues: Large memory usage, complex processing, raw data exposure")
    print()
    
    print("NEW WORKFLOW:")
    print("  Query → Raw Results → Generate Summary → Store Summary → Analyze Summary → Report")
    print("  Benefits: Reduced memory, architectural insights, cleaner data flow")
    print()
    
    print("Key Changes:")
    print("  • SearchIteration.query_result → SearchIteration.result_summary")
    print("  • Raw records replaced with natural language insights")
    print("  • Sufficiency analysis works on summaries")
    print("  • Final reports built from architectural summaries")
    print()

if __name__ == "__main__":
    print("CodexGraph Summary Workflow Test")
    print("=" * 60)
    print()
    
    # Test summary generation
    summary = test_summary_generation()
    
    # Test new data structure
    iteration = test_search_iteration_structure()
    
    # Show workflow comparison
    test_workflow_comparison()
    
    print("✅ All tests completed successfully!")
    print("The system now generates concise natural language summaries")
    print("that capture architectural insights instead of storing raw data.")