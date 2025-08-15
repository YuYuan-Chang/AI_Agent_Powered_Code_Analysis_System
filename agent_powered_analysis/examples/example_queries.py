"""
Example queries demonstrating different search capabilities of CodexGraph.
Shows various types of code structure queries and their expected usage patterns.
"""

from typing import List, Dict, Any
from ..search.iterative_pipeline import IterativePipeline


class ExampleQueries:
    """
    Collection of example queries for demonstrating CodexGraph capabilities.
    """
    
    def __init__(self):
        self.pipeline = IterativePipeline()
    
    def get_example_queries(self) -> List[Dict[str, Any]]:
        """
        Get a list of example queries with descriptions and categories.
        
        Returns:
            List of example query dictionaries
        """
        return [
            {
                "category": "Class Discovery",
                "query": "List all classes in core.utils that use the field cache_size",
                "description": "Find classes in a specific module that reference a particular field",
                "complexity": "medium"
            },
            {
                "category": "Module Search",
                "query": "Find all modules that contain a function named load_config",
                "description": "Locate modules containing specific function names",
                "complexity": "easy"
            },
            {
                "category": "Inheritance Analysis",
                "query": "What are the base classes of SecureSession?",
                "description": "Explore class inheritance hierarchy",
                "complexity": "medium"
            },
            {
                "category": "Variable Usage",
                "query": "Which methods use the global variable ENV_SECRET?",
                "description": "Track usage of global variables across the codebase",
                "complexity": "medium"
            },
            {
                "category": "Method Discovery",
                "query": "Find all classes with a method called validate",
                "description": "Search for classes containing specific methods",
                "complexity": "easy"
            },
            {
                "category": "Structural Analysis",
                "query": "Show me the complete inheritance tree for DatabaseConnection",
                "description": "Get full inheritance hierarchy (parents and children)",
                "complexity": "hard"
            },
            {
                "category": "Cross-Module Analysis",
                "query": "What classes from module auth.models are used in module api.views?",
                "description": "Analyze dependencies between modules",
                "complexity": "hard"
            },
            {
                "category": "Field Analysis",
                "query": "List all fields in User class and which methods access them",
                "description": "Analyze field usage within a class",
                "complexity": "medium"
            },
            {
                "category": "Function Dependencies",
                "query": "Find all functions that call the function encrypt_password",
                "description": "Trace function call dependencies",
                "complexity": "medium"
            },
            {
                "category": "Pattern Search",
                "query": "Find all classes that implement the Singleton pattern",
                "description": "Search for design patterns in code structure",
                "complexity": "hard"
            }
        ]
    
    def run_example(self, query: str) -> None:
        """
        Run a specific example query and display results.
        
        Args:
            query: The query string to execute
        """
        print(f"Executing query: {query}")
        print("=" * 60)
        
        try:
            result = self.pipeline.search(query)
            
            if result.success:
                print(result.final_answer)
                print(f"\nExecution completed in {result.total_execution_time_ms:.2f}ms")
                print(f"Used {len(result.iterations)} iterations")
            else:
                print(f"Query failed: {result.error_message}")
        
        except Exception as e:
            print(f"Error executing query: {str(e)}")
        
        print("\n" + "=" * 60 + "\n")
    
    def run_all_examples(self) -> None:
        """Run all example queries and display results."""
        examples = self.get_example_queries()
        
        print("Running all example queries...")
        print("=" * 80)
        
        for i, example in enumerate(examples, 1):
            print(f"\nExample {i}: {example['category']}")
            print(f"Description: {example['description']}")
            print(f"Complexity: {example['complexity']}")
            print("-" * 40)
            
            self.run_example(example['query'])
    
    def run_examples_by_category(self, category: str) -> None:
        """
        Run all examples in a specific category.
        
        Args:
            category: Category name to filter by
        """
        examples = self.get_example_queries()
        filtered_examples = [ex for ex in examples if ex['category'].lower() == category.lower()]
        
        if not filtered_examples:
            print(f"No examples found for category: {category}")
            return
        
        print(f"Running examples for category: {category}")
        print("=" * 60)
        
        for example in filtered_examples:
            print(f"\nQuery: {example['query']}")
            print(f"Description: {example['description']}")
            print("-" * 40)
            
            self.run_example(example['query'])
    
    def demonstrate_iterative_refinement(self) -> None:
        """Demonstrate how the iterative pipeline refines queries."""
        print("Demonstrating Iterative Refinement")
        print("=" * 50)
        
        # Start with a deliberately vague query
        vague_query = "Find database stuff"
        
        print(f"Starting with vague query: '{vague_query}'")
        print("Watch how the system iteratively refines the search...\n")
        
        result = self.pipeline.search(vague_query)
        
        print("Iteration Details:")
        print("-" * 30)
        
        for i, iteration in enumerate(result.iterations, 1):
            print(f"Iteration {i}:")
            print(f"  Intent: {iteration.nl_intent}")
            print(f"  Cypher: {iteration.cypher_query}")
            print(f"  Results: {len(iteration.query_result.records)} records found")
            print(f"  Sufficient: {iteration.sufficient} (confidence: {iteration.confidence:.2f})")
            if iteration.feedback:
                print(f"  Feedback: {iteration.feedback}")
            print()
        
        print("Final Answer:")
        print("-" * 15)
        print(result.final_answer)


def main():
    """Main function for running examples."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run CodexGraph example queries")
    parser.add_argument("--category", help="Run examples for specific category")
    parser.add_argument("--all", action="store_true", help="Run all examples")
    parser.add_argument("--list", action="store_true", help="List all example categories")
    parser.add_argument("--iterative", action="store_true", help="Demonstrate iterative refinement")
    parser.add_argument("--query", help="Run a specific query")
    
    args = parser.parse_args()
    
    examples = ExampleQueries()
    
    if args.list:
        print("Available example categories:")
        categories = set(ex['category'] for ex in examples.get_example_queries())
        for category in sorted(categories):
            print(f"  - {category}")
    
    elif args.category:
        examples.run_examples_by_category(args.category)
    
    elif args.all:
        examples.run_all_examples()
    
    elif args.iterative:
        examples.demonstrate_iterative_refinement()
    
    elif args.query:
        examples.run_example(args.query)
    
    else:
        # Show available options
        print("CodexGraph Examples")
        print("=" * 30)
        print("Available commands:")
        print("  --list         List all example categories")
        print("  --all          Run all examples")
        print("  --category X   Run examples for category X")
        print("  --iterative    Demonstrate iterative refinement")
        print("  --query 'X'    Run specific query X")
        print()
        
        print("Example categories:")
        categories = set(ex['category'] for ex in examples.get_example_queries())
        for category in sorted(categories):
            print(f"  - {category}")


if __name__ == "__main__":
    main()