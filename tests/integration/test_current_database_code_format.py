#!/usr/bin/env python3
"""
Test script to examine the actual code format in the current database.
"""

import sys
import os

# Add the agent_powered_analysis directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'agent_powered_analysis'))

from Multi_Agent_Search.graphdb.neo4j_connector import Neo4jConnector

def examine_database_code_format():
    """Examine what format the code attributes are in the database."""
    print("Examining Database Code Format")
    print("=" * 50)
    
    try:
        connector = Neo4jConnector()
        
        # Query to get nodes with code attributes
        query = """
        MATCH (n) 
        WHERE n.code IS NOT NULL 
        RETURN n.name, labels(n), n.code, n.file_path 
        LIMIT 10
        """
        
        print("Executing query to find nodes with code attributes...")
        results = connector.execute_query(query)
        
        print(f"Found {len(results)} nodes with code attributes:")
        print()
        
        for i, record in enumerate(results, 1):
            name = record.get('n.name', 'unknown')
            labels = record.get('labels(n)', [])
            code = record.get('n.code', '')
            file_path = record.get('n.file_path', '')
            
            print(f"{i}. {':'.join(labels)} '{name}'")
            print(f"   File: {file_path}")
            print(f"   Code format: {'METADATA' if str(code).startswith('<CODE>') else 'REGULAR'}")
            print(f"   Code preview: {str(code)[:100]}...")
            print()
        
        # Also check for any metadata format specifically
        metadata_query = """
        MATCH (n) 
        WHERE n.code STARTS WITH '<CODE>' 
        RETURN n.name, labels(n), n.code, n.file_path 
        LIMIT 5
        """
        
        print("\nLooking specifically for metadata format code...")
        metadata_results = connector.execute_query(metadata_query)
        
        if metadata_results:
            print(f"Found {len(metadata_results)} nodes with metadata format code:")
            for record in metadata_results:
                name = record.get('n.name', 'unknown')
                labels = record.get('labels(n)', [])
                code = record.get('n.code', '')
                print(f"- {':'.join(labels)} '{name}': {code}")
        else:
            print("No nodes found with metadata format code (<CODE>...)")
    
    except Exception as e:
        print(f"Error examining database: {str(e)}")

if __name__ == "__main__":
    examine_database_code_format()