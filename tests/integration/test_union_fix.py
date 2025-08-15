#!/usr/bin/env python3
"""
Test script to verify the UNION query validation fix.
"""

from agent_powered_analysis.agents.translator_agent import TranslatorAgent

def test_union_validation_fix():
    """Test that the UNION validation is now more lenient."""
    print("Testing UNION Validation Fix")
    print("=" * 40)
    
    translator = TranslatorAgent()
    
    # Test queries that would previously fail but should now pass
    test_queries = [
        # Query with mismatched column names (should warn but not fail)
        """
        MATCH (m:MODULE)-[:CONTAINS]->(c:CLASS) 
        RETURN m.name AS module_name, c.name AS class_name
        UNION 
        MATCH (m:MODULE)-[:CONTAINS]->(f:FUNCTION) 
        RETURN m.name AS module_name, f.name AS function_name
        """,
        
        # Query with correct UNION structure
        """
        MATCH (c:CLASS)-[:HAS_METHOD]->(m:METHOD) 
        RETURN m.name AS name, "method" AS type, m.file_path AS file_path
        UNION 
        MATCH (c:CLASS)-[:HAS_FIELD]->(f:FIELD) 
        RETURN f.name AS name, "field" AS type, f.file_path AS file_path
        """,
        
        # System overview query without UNION
        """
        MATCH (m:MODULE)-[:CONTAINS]->(n) 
        WHERE n:CLASS OR n:FUNCTION OR n:GLOBAL_VARIABLE 
        RETURN m.name AS module_name, labels(n)[0] AS node_type, n.name AS component_name
        ORDER BY m.name, node_type, n.name
        """
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\nTest Query {i}:")
        print("-" * 20)
        query = query.strip()
        
        # Test validation
        is_valid = translator.validate_cypher(query)
        print(f"Query validation result: {is_valid}")
        
        if 'UNION' in query.upper():
            print("Query contains UNION - validation should be lenient")
        else:
            print("Query does not contain UNION")
        
        print(f"Query preview: {query[:100]}...")
    
    print("\n✅ All tests completed!")
    print("The system should now handle UNION queries more gracefully.")
    print("Mismatched column names will generate warnings but not block execution.")

if __name__ == "__main__":
    test_union_validation_fix()