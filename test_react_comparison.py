"""
Test script to compare Original vs ReAct approaches.

Run after starting all services:
python test_react_comparison.py
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_original():
    """Test the original hardcoded workflow."""
    print("\n" + "="*60)
    print("TESTING ORIGINAL APPROACH (Hardcoded Workflow)")
    print("="*60)
    
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "session_id": "test-original",
            "message": "I need a hotel with a pool near Centennial Park, June 10-13, 2026"
        }
    )
    
    result = response.json()
    print(f"\nAssistant Response:\n{result['assistant_message']}\n")
    print(f"Trace Steps: {len(result['trace'])} steps")
    for step in result['trace']:
        print(f"  - {step.get('step', 'unknown')}")


def test_react():
    """Test the ReAct LLM-driven approach."""
    print("\n" + "="*60)
    print("TESTING REACT APPROACH (LLM-Driven Tool Selection)")
    print("="*60)
    
    response = requests.post(
        f"{BASE_URL}/chat/react",
        json={
            "session_id": "test-react",
            "message": "I need a hotel with a pool near Centennial Park, June 10-13, 2026"
        }
    )
    
    result = response.json()
    print(f"\nAssistant Response:\n{result['assistant_message']}\n")
    print(f"Trace Steps: {len(result['trace'])} steps")
    for step in result['trace']:
        print(f"  - {step.get('step', 'unknown')}: {step.get('capability', '')}")


def test_edge_case():
    """Test an edge case that shows ReAct flexibility."""
    print("\n" + "="*60)
    print("TESTING EDGE CASE: 'Show me my last search'")
    print("="*60)
    
    # First, do a search
    requests.post(
        f"{BASE_URL}/chat/react",
        json={
            "session_id": "test-edge",
            "message": "Hotels June 10-13, 2026"
        }
    )
    
    # Now ask to see last search (ReAct should handle this)
    response = requests.post(
        f"{BASE_URL}/chat/react",
        json={
            "session_id": "test-edge",
            "message": "Show me my last search again"
        }
    )
    
    result = response.json()
    print(f"\nReAct Response:\n{result['assistant_message']}\n")
    print("ReAct can adapt to this request by calling context.get and availability.search")
    print("The original hardcoded approach would always follow the same sequence.")


if __name__ == "__main__":
    print("\n🚀 Comparing Original vs ReAct Approaches")
    print("Make sure all services are running first!\n")
    
    try:
        # Check if services are up
        health = requests.get(f"{BASE_URL}/health")
        print(f"✓ Orchestrator is running (model: {health.json()['model']})\n")
        
        test_original()
        test_react()
        test_edge_case()
        
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print("Original: Fast, predictable, but inflexible")
        print("ReAct: Flexible, adaptive, but slower and more expensive")
        print("="*60 + "\n")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to orchestrator at", BASE_URL)
        print("Make sure to start the orchestrator first:")
        print("  cd orchestrator && uvicorn app:app --host 127.0.0.1 --port 8000")
