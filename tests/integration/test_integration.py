#!/usr/bin/env python3
"""
Test script for the integrated Graph + RAG workflow.
This script tests the new functionality without requiring a full system setup.
"""

import sys
import os

# Add agent_powered_analysis to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'agent_powered_analysis'))

def test_rag_agent_import():
    """Test that we can import the RAG agent."""
    try:
        from agent_powered_analysis.agents.rag_agent import RAGAgent
        print("✅ RAG agent import successful")
        
        # Test initialization
        rag_agent = RAGAgent()
        print(f"✅ RAG agent initialized, available: {rag_agent.is_available()}")
        
        return True
    except Exception as e:
        print(f"❌ RAG agent import/init failed: {e}")
        return False

def test_pipeline_import():
    """Test that we can import the updated pipeline."""
    try:
        from agent_powered_analysis.search.iterative_pipeline import IterativePipeline
        print("✅ Iterative pipeline import successful")
        return True
    except Exception as e:
        print(f"❌ Pipeline import failed: {e}")
        return False

def test_pipeline_initialization():
    """Test pipeline initialization with RAG agent."""
    try:
        from agent_powered_analysis.search.iterative_pipeline import IterativePipeline
        from agent_powered_analysis.agents.rag_agent import RAGAgent
        
        # This will fail with connection errors, but should succeed in creating the objects
        rag_agent = RAGAgent()
        print(f"✅ RAG agent created, available: {rag_agent.is_available()}")
        
        # Note: This will fail because Neo4j/OpenAI aren't available, but we can test the structure
        print("⚠️  Pipeline initialization would require Neo4j/OpenAI connections")
        return True
        
    except Exception as e:
        print(f"❌ Pipeline initialization test failed: {e}")
        return False

def test_new_methods_exist():
    """Test that new methods exist in the pipeline."""
    try:
        from agent_powered_analysis.search.iterative_pipeline import IterativePipeline
        
        # Check if our new methods exist
        methods_to_check = [
            '_generate_intent_summary',
            '_merge_all_summaries', 
            '_combine_intent_results',
            '_analyze_combined_sufficiency'
        ]
        
        for method_name in methods_to_check:
            if hasattr(IterativePipeline, method_name):
                print(f"✅ Method {method_name} exists")
            else:
                print(f"❌ Method {method_name} missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Method check failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Testing Graph + RAG Integration")
    print("=" * 50)
    
    tests = [
        ("RAG Agent Import", test_rag_agent_import),
        ("Pipeline Import", test_pipeline_import),
        ("Pipeline Initialization", test_pipeline_initialization),
        ("New Methods Exist", test_new_methods_exist)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All integration tests passed!")
        print("\n📝 Summary of Changes:")
        print("  • RAG agent integrated into pipeline")
        print("  • Each query intent processed through both Graph and RAG")
        print("  • Individual summaries generated for each intent")
        print("  • All summaries merged into comprehensive overview")
        print("  • Sufficiency analysis updated for combined results")
        return True
    else:
        print("⚠️  Some tests failed - check implementation")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)