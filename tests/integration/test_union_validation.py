#!/usr/bin/env python3
"""
Test the improved UNION validation to catch column count mismatches.
"""

from agent_powered_analysis.agents.translator_agent import TranslatorAgent

def test_union_validation():
    """Test UNION validation catches column count and name mismatches."""
    print("Testing UNION Validation")
    print("=" * 40)
    
    translator = TranslatorAgent()
    
    # Test the problematic query that caused the error
    problematic_query = """
    MATCH (m:MODULE)-[:CONTAINS]->(n) WHERE n:CLASS OR n:FUNCTION OR n:GLOBAL_VARIABLE 
    RETURN m.name AS module_name, labels(n)[0] AS node_type, n.name AS component_name, n.file_path AS file_path 
    ORDER BY m.name, node_type, n.name 
    UNION 
    MATCH (n1)-[r]->(n2) WHERE (n1:CLASS OR n1:FUNCTION OR n1:GLOBAL_VARIABLE) AND (n2:CLASS OR n2:FUNCTION OR n2:GLOBAL_VARIABLE) 
    RETURN labels(n1)[0] AS source_type, n1.name AS source_name, type(r) AS relationship, labels(n2)[0] AS target_type, n2.name AS target_name 
    ORDER BY source_type, source_name, relationship, target_type, target_name
    """.strip()
    
    print("Testing problematic query (should FAIL validation):")
    print(f"Query: {problematic_query[:100]}...")
    
    is_valid = translator.validate_cypher(problematic_query)
    print(f"Validation result: {is_valid}")
    print("Expected: False (should catch column count mismatch)")
    
    # Test a correct query
    correct_query = """
    MATCH (m:MODULE)-[:CONTAINS]->(n) WHERE n:CLASS OR n:FUNCTION 
    OPTIONAL MATCH (n)-[r]->(n2) WHERE n2:CLASS OR n2:FUNCTION 
    RETURN m.name AS module_name, n.name AS component_name, labels(n)[0] AS component_type, 
           type(r) AS relationship_type, n2.name AS related_component 
    ORDER BY m.name, n.name
    """.strip()
    
    print("\nTesting correct query (should PASS validation):")
    print(f"Query: {correct_query[:100]}...")
    
    is_valid = translator.validate_cypher(correct_query)
    print(f"Validation result: {is_valid}")
    print("Expected: True (should pass)")
    
    print(f"\n{'✅' if not translator.validate_cypher(problematic_query) else '❌'} Validation correctly catches problematic UNION queries")
    print(f"{'✅' if translator.validate_cypher(correct_query) else '❌'} Validation allows correct queries")

if __name__ == "__main__":
    test_union_validation()