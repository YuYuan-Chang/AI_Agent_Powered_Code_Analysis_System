"""
CLI entrypoint for the Agent Powered Analysis system.
Provides command-line interface for code structure-aware search.
"""

import argparse
import logging
import sys
from typing import Optional
import json
from datetime import datetime

from .search.iterative_pipeline import IterativePipeline
from .graphdb.neo4j_connector import Neo4jConnector
from .config import config


def setup_logging(level: str = "INFO") -> None:
    """
    Set up logging configuration with enhanced OpenAI API logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Clear any existing handlers to avoid conflicts
    logging.getLogger().handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Create file handler for all logs
    file_handler = logging.FileHandler('agent_powered_analysis.log')
    file_handler.setFormatter(formatter)
    
    # Create separate file handler for OpenAI API logs
    openai_handler = logging.FileHandler('openai_api.log')
    openai_handler.setFormatter(formatter)
    
    # Configure root logger to capture everything
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Configure OpenAI API logger specifically (also logs to openai_api.log)
    openai_api_logger = logging.getLogger('openai_api')
    openai_api_logger.addHandler(openai_handler)
    openai_api_logger.setLevel(log_level)
    
    # Test that logging works by writing to main log
    main_logger = logging.getLogger('agent_powered_analysis')
    main_logger.info("=" * 60)
    main_logger.info("Agent Powered Analysis System Starting - OpenAI Logging Enabled")
    main_logger.info("Main log: agent_powered_analysis.log | OpenAI API log: openai_api.log")
    main_logger.info("=" * 60)


def test_connections() -> bool:
    """
    Test connections to external services.
    
    Returns:
        True if all connections successful, False otherwise
    """
    print("Testing connections...")
    
    # Test Neo4j connection
    try:
        connector = Neo4jConnector()
        if connector.test_connection():
            print("✓ Neo4j connection successful")
        else:
            print("✗ Neo4j connection failed")
            return False
    except Exception as e:
        print(f"✗ Neo4j connection error: {str(e)}")
        return False
    
    # Test OpenAI API
    try:
        import openai
        client = openai.OpenAI(api_key=config.openai.api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "test"}],
            max_completion_tokens=5
        )
        print("✓ OpenAI API connection successful")
    except Exception as e:
        print(f"✗ OpenAI API connection error: {str(e)}")
        return False
    
    return True


def show_database_info() -> None:
    """Show information about the Neo4j database."""
    try:
        connector = Neo4jConnector()
        info = connector.get_database_info()
        
        print("Database Information:")
        print("=" * 50)
        
        print(f"Node Labels: {', '.join(info.get('labels', []))}")
        print(f"Relationship Types: {', '.join(info.get('relationship_types', []))}")
        
        print("\nNode Counts:")
        for label, count in info.get('node_counts', {}).items():
            print(f"  {label}: {count}")
        
        print("\nRelationship Counts:")
        for rel_type, count in info.get('relationship_counts', {}).items():
            print(f"  {rel_type}: {count}")
            
    except Exception as e:
        print(f"Error getting database info: {str(e)}")


def interactive_mode(base_path: Optional[str] = None) -> None:
    """Run the system in interactive mode."""
    print("Multi-Agent Code Search Interactive Mode")
    print("=" * 40)
    print("Enter natural language queries about your codebase.")
    print("Type 'exit' to quit, 'help' for help, 'save <filename>' to save last result.")
    print()
    
    pipeline = IterativePipeline(base_path=base_path)
    last_result = None
    
    while True:
        try:
            user_input = input("Query: ").strip()
            
            if user_input.lower() in ['exit', 'quit']:
                print("Goodbye!")
                break
            elif user_input.lower() == 'help':
                show_help()
                continue
            elif user_input.lower().startswith('save '):
                if last_result:
                    filename = user_input[5:].strip()
                    if not filename:
                        filename = f"system_report_{int(datetime.now().timestamp())}.md"
                    
                    # Always save as markdown
                    save_format = "md"
                    
                    if last_result.save_to_file(filename, save_format):
                        print(f"Results saved to: {filename}")
                    else:
                        print(f"Failed to save results to: {filename}")
                else:
                    print("No previous search results to save.")
                continue
            elif not user_input:
                continue
            
            print(f"\nSearching for: {user_input}")
            print("-" * 50)
            
            result = pipeline.search(user_input)
            last_result = result  # Store for potential saving
            
            if result.success:
                print(result.final_answer)
                print(f"\nCompleted in {result.total_execution_time_ms:.2f}ms using {len(result.iterations)} iterations")
            else:
                print(f"Search failed: {result.error_message}")
            
            print("\n" + "=" * 80 + "\n")
            
        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Goodbye!")
            break
        except Exception as e:
            print(f"Error: {str(e)}")


def show_help() -> None:
    """Show help information."""
    help_text = """
CodexGraph Help
===============

Example queries you can try:
• "Find all classes in the utils module that have a method called validate"
• "What are the base classes of DatabaseConnection?"
• "List all functions that use the global variable API_KEY"
• "Show me all methods in the User class"
• "Find classes that inherit from BaseModel"
• "What modules contain a function named load_config?"

Query Tips:
• Be specific about what you're looking for (classes, functions, methods, etc.)
• Mention specific names when you know them (module names, class names, etc.)
• Use natural language - the system will understand your intent

Commands:
• 'exit' or 'quit' - Exit the program
• 'help' - Show this help message  
• 'save <filename.md>' - Save the last system report to a markdown file
• 'save' - Save with auto-generated markdown filename
"""
    print(help_text)


def run_single_query(query: str, output_format: str = "text", base_path: Optional[str] = None, 
                     save_path: Optional[str] = None, save_format: str = "md") -> None:
    """
    Run a single query and output results.
    
    Args:
        query: Natural language query to execute
        output_format: Output format ('text' or 'json')
        base_path: Base path for resolving source code file paths
        save_path: Optional path to save results to file
        save_format: Format for saved results ('md' for markdown report)
    """
    pipeline = IterativePipeline(base_path=base_path)
    result = pipeline.search(query)
    
    # Save results if path provided
    if save_path:
        if result.save_to_file(save_path, save_format):
            print(f"Results saved to: {save_path}")
        else:
            print(f"Failed to save results to: {save_path}")
    
    if output_format == "json":
        # Convert result to JSON-serializable format
        result_dict = {
            "original_query": result.original_query,
            "success": result.success,
            "final_answer": result.final_answer,
            "total_execution_time_ms": result.total_execution_time_ms,
            "iterations": len(result.iterations),
            "error_message": result.error_message
        }
        print(json.dumps(result_dict, indent=2))
    else:
        if result.success:
            print(result.final_answer)
            print(f"\nCompleted in {result.total_execution_time_ms:.2f}ms using {len(result.iterations)} iterations")
        else:
            print(f"Search failed: {result.error_message}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CodexGraph - Code structure-aware search with LLM agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m agent_powered_analysis --interactive
  python -m agent_powered_analysis --query "Find all classes that inherit from BaseModel"
  python -m agent_powered_analysis --query "Show me all methods" --save-results report.md
  python -m agent_powered_analysis --test-connections
  python -m agent_powered_analysis --database-info
        """
    )
    
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Single query to execute"
    )
    
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode"
    )
    
    parser.add_argument(
        "--test-connections",
        action="store_true",
        help="Test connections to Neo4j and OpenAI API"
    )
    
    parser.add_argument(
        "--database-info",
        action="store_true",
        help="Show information about the Neo4j database"
    )
    
    parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        help="Output format for query results"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    parser.add_argument(
        "--base-path",
        type=str,
        help="Base path for resolving source code file paths (for code extraction)"
    )
    
    parser.add_argument(
        "--save-results", "-s",
        type=str,
        help="Save search results to specified file path"
    )
    
    parser.add_argument(
        "--save-format",
        choices=["md", "json", "txt"],
        default="md",
        help="Format for saved results (md=markdown report, json=JSON with extracted code, txt=text)"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.log_level)
    
    try:
        if args.test_connections:
            if test_connections():
                print("All connections successful!")
                sys.exit(0)
            else:
                print("Connection test failed!")
                sys.exit(1)
        
        elif args.database_info:
            show_database_info()
        
        elif args.query:
            run_single_query(args.query, args.output_format, args.base_path, 
                           args.save_results, args.save_format)
        
        elif args.interactive:
            interactive_mode(args.base_path)
        
        else:
            # Default to interactive mode
            interactive_mode(args.base_path)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        logging.error(f"Application error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()