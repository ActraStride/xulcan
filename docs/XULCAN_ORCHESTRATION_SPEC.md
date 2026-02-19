# Xulcan Orchestration Architecture (Spec)

## Purpose
Provide a minimal, composable orchestration layer that:
- Lets a **core model** plan and execute tool calls.
- Allows the core model to **spin sub‑models** (specialists) with custom prompts/tools.
- Preserves Xulcan’s API‑first architecture and clean separation of concerns.

This spec defines **interfaces, modules, and request/response shapes** for phase 1.

---

## 1) Module Layout (Proposed)

```
app/xulcan/
  core/
    llm/
      adapters/
        base.py
        openai.py
        anthropic.py
        gemini.py
      client.py           # provider SDK wrappers
    engine/
      orchestrator.py     # LLM orchestration loop
      execution.py        # tool execution & retry logic
      policies.py         # routing / cost / depth constraints
    memory/
      conversation.py
  tools/
    base.py               # BaseTool + decorator
    registry.py
    runner.py
    models.py             # ModelRegistry + ModelTool
  api/
    schemas/
      orchestrator.py     # pydantic request/response models
    routes/
      orchestrator.py
```

---

## 2) Core Interfaces

### 2.1 Tool Base
```python
class BaseTool(BaseModel):
    def run(self) -> Any: ...
```
- Typed inputs (Pydantic).
- `get_schema()` to export LLM‑friendly JSON schema.
- `tool` decorator to enforce `run()`.

### 2.2 ToolRegistry
- `register(tool_cls)`
- `get(name)`, `list()`, `export_schemas()`
- `auto_discover(module)`

### 2.3 ToolRunner
- `run_tool(name, inputs)` with typed validation.
- `run_tool_safe()` returns structured `{success,result,error}`.

---

## 3) Model Orchestration (“Spin”)

### 3.1 ModelRegistry
```python
class ModelRegistry:
    def register(self, model: ModelSpec) -> None
    def get(self, name: str) -> ModelSpec | None
```

```python
class ModelSpec(BaseModel):
    name: str
    provider: Literal["openai","openrouter","anthropic","gemini","zai"]
    model_id: str
    system_prompt: str | None = None
    tools: list[str] = []
    max_tokens: int | None = None
    temperature: float | None = None
```

### 3.2 ModelTool (Sub‑Model as Tool)
Expose each registered model as a callable tool:

```python
class ModelTool(BaseTool):
    model: str
    prompt: str
    tool_subset: list[str] | None = None
    def run(self) -> ModelResponse: ...
```

This lets the **core model** orchestrator “call a model” like any other tool.

---

## 4) Adapter Layer (Provider‑Specific)

Adapters convert tool schemas and calls to provider formats:

```python
class BaseAdapter(ABC):
    def export_tools(registry) -> list[dict]
    def convert_tool_call(tool_call) -> dict  # {tool_name, inputs}
    def format_tool_result(result, tool_call_id=None) -> dict
```

Supported providers in phase 1:
- OpenAI
- OpenRouter (OpenAI-compatible)
- Z.ai (OpenAI-compatible)
- Anthropic
- Gemini

---

## 5) Orchestrator Loop

### 5.1 Orchestrator
```python
class LLMOrchestrator:
  async def run(user_input: str) -> str
```

Loop logic:
1) Build messages (system + memory + user).
2) Call LLM with tools.
3) Parse tool calls.
4) Execute tools via `ExecutionEngine`.
5) Repeat until no tools or max iterations.

### 5.2 ExecutionEngine
- `execute_tools_parallel()` and `execute_tools_sequential()`
- Retry with exponential backoff.
- Uses adapter to convert tool calls.

---

## 6) Orchestration Policy

Define routing constraints and guardrails:

```python
class OrchestrationPolicy(BaseModel):
    max_iterations: int = 5
    max_depth: int = 2  # sub-model nesting
    max_cost_usd: float | None = None
    allow_models: list[str] | None = None
    deny_models: list[str] | None = None
```

Enforce:
- Which sub‑models can be called.
- Max tool iterations.
- Max orchestration depth.

---

## 7) API Contract (Phase 1)

### 7.1 Request Schema
```json
{
  "input": "string",
  "core_model": "gpt-4o-mini",
  "policy": { "...": "..." },
  "tools": ["Search", "Summarize", "ModelTool"],
  "metadata": { "trace_id": "..." }
}
```

### 7.2 Response Schema
```json
{
  "output": "string",
  "tool_calls": [...],
  "tool_results": [...],
  "usage": { "input_tokens": 123, "output_tokens": 456 }
}
```

Route: `POST /orchestrate`

---

## 8) Observability Hooks

Emit events for:
- `orchestration.start`
- `tool.execution.start|end|error`
- `model.call.start|end|error`

This maps to existing structured logging in Xulcan.

---

## 9) Phase 2+ (Not in scope now)
- Workflow engine (parallel/conditional steps).
- Plugin system for tools + adapters.
- Durable orchestration state (Redis/Postgres).
