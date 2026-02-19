# Getting Started

This guide shows how to launch Xulcan and run your first orchestration request.

## Prerequisites

- Docker + Docker Compose
- Make
- An LLM API key (OpenAI, OpenRouter, Anthropic, Gemini, or Z.ai)

## 1) Launch Xulcan (Docker path)

From the repo root:

```bash
make setup
```

Set your provider key in `.env` (created by `make setup`):

```bash
# Example for OpenAI
OPENAI_API_KEY=sk-...

# Example for OpenRouter (OpenAI-compatible)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

Start the stack:

```bash
make dev
```

Verify the API is up:

```bash
curl http://localhost:8000/health/live
```

## 2) Run an orchestration example

Send a request to `POST /orchestrate`:

```bash
curl -sS http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Use the Add tool to add 19 and 23. Return only the final number.",
    "core_model": "gpt-4o-mini",
    "provider": "openai",
    "tools": ["Add"],
    "policy": {
      "max_iterations": 3
    },
    "temperature": 0
  }'
```

Typical response shape:

```json
{
  "output": "42",
  "tool_calls": [
    {
      "tool": "Add",
      "success": true,
      "result": 42.0,
      "error": null
    }
  ],
  "usage": null
}
```

OpenRouter request example:

```bash
curl -sS http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Summarize this in one sentence.",
    "core_model": "openrouter/free",
    "provider": "openrouter",
    "policy": {
      "max_iterations": 2
    }
  }'
```

Open interactive API docs at:

- http://localhost:8000/docs

## 3) Local API launch (optional, no app container)

Use this if you want to run FastAPI on your host with hot reload:

```bash
make uv-setup
cp .env.example .env
```

Update `.env` for local dependencies:

```bash
POSTGRES_SERVER=localhost
REDIS_HOST=localhost
```

Start dependencies and run API:

```bash
make deps
make local
```

Then call the same orchestration endpoint:

```bash
curl http://localhost:8000/orchestrate -H "Content-Type: application/json" -d '{...}'
```

## Notes

- Supported providers in this orchestration route: `openai`, `openrouter`, `zai`, `anthropic`, `gemini`.
- For Z.ai, set both `ZAI_API_KEY` and `ZAI_BASE_URL` in `.env`.
- For OpenRouter, set both `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL` in `.env`.
- If `/orchestrate` returns provider auth errors, confirm the correct API key is present in `.env`.
