# ReAct Pattern Implementation

## What Changed

### Original Approach (agentic_loop.py)
**Hardcoded workflow** - Fixed sequence of MCP capability calls:
1. context.get
2. extraction.parse
3. context.upsert
4. context.get (again)
5. property.resolve (conditional)
6. availability.search
7. results.explain

The orchestrator acts as a **deterministic state machine**. The LLM is only used within specific capabilities (extraction.parse and results.explain), not for deciding which tools to invoke.

### ReAct Approach (react_loop.py)
**LLM-driven tool selection** - The LLM decides which capabilities to call and when:

```
Thought: I need to get the current session state first
Action: context.get
Observation: [tool result]

Thought: Now I'll extract parameters from the user's message
Action: extraction.parse
Observation: [tool result]

Thought: I have dates, let me search for availability
Action: availability.search
Observation: [tool result]

Thought: I have results, let me explain them
Action: results.explain
Observation: [tool result]

Thought: I have enough information to answer
Final Answer: [response to user]
```

## Key Differences

| Aspect | Original | ReAct |
|--------|----------|-------|
| **Tool Selection** | Hardcoded sequence | LLM decides dynamically |
| **Flexibility** | Fixed workflow only | Can adapt to different intents |
| **LLM Role** | Component within tools | Orchestrator itself |
| **Iterations** | Single pass | Multiple reasoning loops (max 10) |
| **Error Recovery** | Predefined fallbacks | LLM can reason about errors |
| **Extensibility** | Requires code changes | New tools auto-available |

## How ReAct Works

### 1. System Prompt
Defines available tools and reasoning pattern:
```python
REACT_SYSTEM_PROMPT = """You are a hotel search assistant using ReAct pattern.
Available capabilities: context.get, extraction.parse, availability.search...
Think step-by-step: Thought → Action → Observation → repeat"""
```

### 2. Tool Definitions
MCP capabilities converted to OpenAI function calling format:
```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "context.get",
            "description": "Retrieve current session state",
            "parameters": {...}
        }
    },
    ...
]
```

### 3. Iterative Loop
```python
for iteration in range(max_iterations):
    # LLM reasons about what to do
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    
    # If no tool calls, LLM has final answer
    if not response.choices[0].message.tool_calls:
        return final_answer
    
    # Execute tool calls chosen by LLM
    for tool_call in response.choices[0].message.tool_calls:
        result = mcp.invoke(tool_call.function.name, arguments)
        messages.append({"role": "tool", "content": result})
    
    # Loop continues - LLM observes results and decides next action
```

## Benefits of ReAct

1. **Handles diverse intents**: "Show me my last search", "What's the weather?", "Cancel booking"
2. **Dynamic adaptation**: Can skip unnecessary steps or add new ones
3. **Error recovery**: LLM can reason about failures and try alternatives
4. **Extensibility**: Add new MCP capabilities without changing orchestrator code
5. **Transparency**: Trace shows LLM's reasoning process

## Usage

### Original endpoint (hardcoded):
```bash
POST http://127.0.0.1:8000/chat
{
  "session_id": "demo-1",
  "message": "Hotels near Centennial Park June 10-13"
}
```

### ReAct endpoint (LLM-driven):
```bash
POST http://127.0.0.1:8000/chat/react
{
  "session_id": "demo-1",
  "message": "Hotels near Centennial Park June 10-13"
}
```

## Trade-offs

### ReAct Advantages
- More flexible and adaptable
- Can handle unexpected user requests
- Self-correcting on errors
- Easier to extend with new capabilities

### ReAct Disadvantages
- Higher latency (multiple LLM calls)
- Higher cost (more tokens)
- Less predictable behavior
- Requires careful prompt engineering

## When to Use Each

**Use Original (Hardcoded)** when:
- Workflow is well-defined and stable
- Performance/cost is critical
- Predictability is required
- Single-purpose application

**Use ReAct** when:
- User intents are diverse
- Flexibility is more important than speed
- You want to add capabilities frequently
- Building a general-purpose assistant
