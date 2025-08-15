"""Example usage of the Code Repository RAG system."""

import os
from main import CodeRAGSystem

def main():
    """Demonstrate the RAG system functionality."""
    
    print("🔍 Code Repository RAG System - Example Usage")
    print("=" * 50)
    
    # Initialize the system
    rag_system = CodeRAGSystem(cache_directory="./cache")
    print("✅ Initialized RAG system")
    
    # Check current status
    status = rag_system.get_system_status()
    print(f"📊 Has indexed data: {status['has_indexed_data']}")
    
    if not status['has_indexed_data']:
        print("\n⚠️  No repository indexed yet.")
        print("To test the system, please run:")
        print("python main.py index --repo-path /absolute/path/to/your/repository")
        return
        
    # Show repository stats
    stats = status['repository_stats']
    print(f"📄 Total documents: {stats.get('total_documents', 0)}")
    print(f"💻 Languages: {', '.join(stats.get('languages', []))}")
    print(f"📊 Code size: {stats.get('total_code_size_bytes', 0):,} bytes")
    
    # Example searches
    example_queries = [
        "how does authentication work",
        "database connection and queries", 
        "error handling patterns",
        "API endpoints and routing",
        "configuration and settings"
    ]
    
    print(f"\n🔍 Running example searches...")
    print("-" * 30)
    
    for i, query in enumerate(example_queries, 1):
        print(f"\n{i}. Query: '{query}'")
        
        try:
            result = rag_system.search_and_summarize(query, k=3)
            
            if result['documents_found'] > 0:
                print(f"   📄 Found: {result['documents_found']} documents")
                print(f"   💻 Languages: {', '.join(result['languages'])}")
                
                # Show brief summary (first 200 chars)
                summary = result['summary']
                if len(summary) > 200:
                    summary = summary[:200] + "..."
                print(f"   📝 Summary: {summary}")
                
            else:
                print("   ❌ No relevant documents found")
                
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
    
    print(f"\n🎉 Example usage complete!")
    print("\n💡 Try running your own searches:")
    print("python main.py search --query 'your search query here'")


if __name__ == "__main__":
    main()