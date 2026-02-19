# Orchestration Examples

## 1) Core model with a specialist sub-model

Request:
```json
{
  "input": "Summarize this and ask the specialist to double-check: The API uses PostgreSQL and Redis.",
  "core_model": "gpt-4o-mini",
  "provider": "openai",
  "models": [
    {
      "name": "fact-checker",
      "provider": "openai",
      "model_id": "gpt-4o-mini",
      "system_prompt": "You verify technical claims and highlight discrepancies.",
      "tools": []
    }
  ],
  "policy": {
    "max_iterations": 3,
    "max_depth": 2
  }
}
```

Behavior:
- The core model can call `ModelTool` to invoke the `fact-checker` model.
- Each model gets its own system prompt and tool set.

## 1b) Z.ai GLM-4.7-Flash (OpenAI-compatible)

Set env vars:
```bash
export ZAI_API_KEY=sk-...
export ZAI_BASE_URL=https://api.z.ai/api/paas/v4
```

Request:
```json
{
  "input": "Summarize this in one sentence: Xulcan orchestrates tools and models.",
  "core_model": "GLM-4.7-Flash",
  "provider": "zai",
  "policy": {
    "max_iterations": 2
  }
}
```

## 1c) OpenRouter (OpenAI-compatible)

Set env vars:
```bash
export OPENROUTER_API_KEY=sk-or-...
export OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Request:
```json
{
  "input": "Summarize this in one sentence: Xulcan orchestrates tools and models.",
  "core_model": "openrouter/free",
  "provider": "openrouter",
  "policy": {
    "max_iterations": 2
  }
}
```

## 2) Add tool subset for a sub-model (conceptual)

```json
{
  "input": "Use the research model to draft a tool list.",
  "core_model": "gpt-4o-mini",
  "provider": "openai",
  "models": [
    {
      "name": "researcher",
      "provider": "openai",
      "model_id": "gpt-4o-mini",
      "system_prompt": "You gather information and format it in bullets.",
      "tools": ["SearchTool", "SummarizeTool"]
    }
  ]
}
```

Note: tool registration and concrete tool implementations are next‑step work.
