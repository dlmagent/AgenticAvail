# Architecture Comparison: Original vs ReAct

## Original Approach (Hardcoded Workflow)

```
User Message
    ↓
┌─────────────────────────────────────────┐
│      Orchestrator (agentic_loop.py)     │
│                                         │
│  Step 1: context.get                    │
│         ↓                               │
│  Step 2: extraction.parse (LLM)         │
│         ↓                               │
│  Step 3: context.upsert                 │
│         ↓                               │
│  Step 4: context.get                    │
│         ↓                               │
│  Step 5: property.resolve (conditional) │
│         ↓                               │
│  Step 6: availability.search            │
│         ↓                               │
│  Step 7: results.explain (LLM)          │
│         ↓                               │
│  Render final answer                    │
└─────────────────────────────────────────┘
    ↓
Response to User

CHARACTERISTICS:
✓ Fast (single pass)
✓ Predictable
✓ Low cost
✗ Inflexible
✗ Can't adapt to different intents
```

## ReAct Approach (LLM-Driven Tool Selection)

```
User Message
    ↓
┌──────────────────────────────────────────────────────┐
│         Orchestrator (react_loop.py)                 │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  Iteration 1                               │    │
│  │  LLM: "I need to get session state"        │    │
│  │  Action: context.get                       │    │
│  │  Observation: {state data}                 │    │
│  └────────────────────────────────────────────┘    │
│                    ↓                                │
│  ┌────────────────────────────────────────────┐    │
│  │  Iteration 2                               │    │
│  │  LLM: "I'll extract parameters"            │    │
│  │  Action: extraction.parse                  │    │
│  │  Observation: {extracted params}           │    │
│  └────────────────────────────────────────────┘    │
│                    ↓                                │
│  ┌────────────────────────────────────────────┐    │
│  │  Iteration 3                               │    │
│  │  LLM: "I need to update state"             │    │
│  │  Action: context.upsert                    │    │
│  │  Observation: {success}                    │    │
│  └────────────────────────────────────────────┘    │
│                    ↓                                │
│  ┌────────────────────────────────────────────┐    │
│  │  Iteration 4                               │    │
│  │  LLM: "Now I can search availability"      │    │
│  │  Action: availability.search               │    │
│  │  Observation: {hotel results}              │    │
│  └────────────────────────────────────────────┘    │
│                    ↓                                │
│  ┌────────────────────────────────────────────┐    │
│  │  Iteration 5                               │    │
│  │  LLM: "Let me explain the results"         │    │
│  │  Action: results.explain                   │    │
│  │  Observation: {narrative}                  │    │
│  └────────────────────────────────────────────┘    │
│                    ↓                                │
│  ┌────────────────────────────────────────────┐    │
│  │  Iteration 6                               │    │
│  │  LLM: "I have enough info to answer"       │    │
│  │  Final Answer: [response]                  │    │
│  └────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
    ↓
Response to User

CHARACTERISTICS:
✓ Flexible (adapts to any intent)
✓ Self-correcting
✓ Extensible (new tools auto-available)
✗ Slower (multiple LLM calls)
✗ Higher cost
✗ Less predictable
```

## Key Difference: Who Decides?

### Original
```python
# Orchestrator code decides the sequence
state = mcp.invoke("context.get", ...)
patch = mcp.invoke("extraction.parse", ...)
mcp.invoke("context.upsert", ...)
results = mcp.invoke("availability.search", ...)
explanation = mcp.invoke("results.explain", ...)
```

### ReAct
```python
# LLM decides the sequence via function calling
response = llm.chat(
    messages=conversation,
    tools=available_mcp_capabilities,  # LLM sees all options
    tool_choice="auto"  # LLM picks what to call
)

# LLM might choose:
# - context.get first
# - then extraction.parse
# - or skip steps if not needed
# - or call tools in different order
# - or handle "show my last search" by just calling context.get
```

## Example: Different User Intents

### Intent 1: "Hotels June 10-13"
**Original**: Runs all 7 steps (even if some unnecessary)
**ReAct**: LLM might skip property.resolve if not needed

### Intent 2: "Show me my last search"
**Original**: Still runs all 7 steps, might fail or give wrong answer
**ReAct**: LLM calls context.get → availability.search → results.explain

### Intent 3: "Change check-in to June 15"
**Original**: Runs all 7 steps
**ReAct**: LLM calls context.get → extraction.parse → context.upsert → done

## Tool Invocation Flow

### Original (Direct MCP Calls)
```
Orchestrator → MCP Server → Availability Agent
            → MCP Server → Context Agent
            → MCP Server → Explainer Agent
```

### ReAct (LLM-Mediated MCP Calls)
```
User → LLM (decides) → Orchestrator → MCP Server → Agent
                    ↓
                Observes result
                    ↓
     LLM (decides next) → Orchestrator → MCP Server → Agent
                    ↓
                Observes result
                    ↓
              LLM (final answer)
```
