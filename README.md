<div align="center">

# 🌋 Xulcan OS

### Event-Sourced, Governance-First Runtime for AI Agent Systems

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Architecture: Event Sourcing](https://img.shields.io/badge/Architecture-Event%20Sourcing-orange.svg)]()
[![License: AGPLv3](https://img.shields.io/badge/license-AGPLv3-green.svg)](https://www.gnu.org/licenses/agpl-3.0.en.html)

Declarative agents, deterministic orchestration, and resumable execution.

[Overview](#-overview) •
[Architecture](#-architectural-model) •
[Features](#-core-features) •
[Quickstart](#-quickstart) •
[Project Structure](#-project-structure)

</div>

---

# 📖 Overview

Most modern AI frameworks treat agents as application code tightly coupled to:
- prompts,
- infrastructure,
- provider clients,
- execution state,
- persistence,
- and runtime orchestration.

This makes systems difficult to:
- audit,
- migrate,
- scale,
- suspend,
- resume,
- or govern safely.

**Xulcan** approaches the problem differently.

Agents are treated as **declarative runtime entities** rather than imperative code objects.

The system is built around:
- finite-state orchestration,
- event sourcing,
- hierarchical governance,
- runtime assembly,
- and distributed suspension/resume semantics.

The result is a runtime capable of executing long-running AI workflows with:
- deterministic behavior,
- infrastructure portability,
- auditability,
- and governance boundaries.

---

# 🏛️ Architectural Model

Xulcan is structured around three isolated architectural domains.

---

## 🧠 Blueprint — Cognition

Defines:
- what an agent is,
- how it behaves,
- which model it uses,
- what tools it can access,
- and how governance applies to it.

Blueprints are fully declarative (`YAML`) and portable across environments.

They contain:
- prompts,
- tool declarations,
- context strategies,
- fallback chains,
- governance rules,
- lifecycle hooks.

Blueprints contain no infrastructure configuration.

---

## 📜 Ledger — Time

Xulcan uses an event-sourced execution model.

Instead of storing only final state, the system records every runtime event:
- `RunCreated`
- `ModelResponse`
- `ToolExecuted`
- `RunSuspended`
- `RunFailed`
- etc.

This enables:
- full auditability,
- deterministic replay,
- runtime introspection,
- and debugging through execution history.

Events are strongly typed using Pydantic polymorphism.

---

## 🏗️ Infraprint — Infrastructure

Defines where and how the system runs.

Infrastructure concerns are isolated from agent cognition:
- secret management,
- event buses,
- state stores,
- ledgers,
- provider configuration,
- persistence drivers.

An agent can move from:
- local memory,
- to Redis/Postgres,
- to distributed cloud infrastructure

without modifying the Blueprint itself.

---

# 🚀 Core Features

## 🛡️ Governance System

Governance is a first-class runtime concern.

### Sentinel — Policy Enforcement

Inspects tool calls before execution.

Supports:
- allowlists,
- blocklists,
- recursive payload inspection,
- escalation flows,
- policy-based execution control.

---

### HumanGate — Human-in-the-Loop Execution

When a tool call requires approval:
1. the Kernel suspends execution,
2. serializes FSM state,
3. releases the worker,
4. waits for external approval,
5. rehydrates execution through `resume_run()`.

Long-running approval flows do not block compute resources.

---

### Bursar — Capacity Governance

Controls runtime consumption through:
- token budgets,
- latency budgets,
- hierarchical limits.

Supports:
- warnings,
- hard halts,
- app-level ceilings,
- agent-level limits,
- compiled governance resolution.

---

## 🧠 LLM Orchestration

### Automatic Fallback Chains

If a provider fails due to:
- rate limits,
- transient failures,
- provider instability,

Xulcan can automatically transition to fallback providers.

---

### Local Model Compatibility

Supports adaptive tool calling strategies for providers lacking native function calling support.

Includes:
- structured JSON coercion,
- prompt-injected tool protocols,
- reasoning sanitization.

---

## 🌐 Multi-Agent Runtime

### Sub-Agent Composition

Agents can invoke other agents as tools.

Supports:
- nested execution,
- isolated governance,
- shared runtime infrastructure,
- contextual memory transfer.

---

### Ephemeral Sandboxes

Tool execution can run inside isolated environments with:
- CPU quotas,
- memory limits,
- session teardown,
- runtime isolation.

---

## 📡 Event Bus

All runtime events can be emitted into:
- IPC channels,
- firehose streams,
- reactive monitoring systems.

Supports real-time telemetry and distributed orchestration.

---

# ⚡ Quickstart

## 1. Define an Agent Blueprint

```yaml
# app/blueprints/support_agent.xul.yml

xulcan_version: "2.0"

id: "support_agent"
name: "Alice"

description: "Refund support agent"

model: "openai/gpt-4o"

fallbacks:
  - "groq/llama3-70b-8192"

system_prompt: |
  You are a support agent.
  User profile:
  {{ user_profile }}

tools:
  - "search_docs"

  - name: "issue_refund"
    governance:
      human_gate: "terminal"
      sentinel: "blocklist"
      side_effects: "write"

governance:
  budget:
    enforced:
      token_limit: 10000
      warn_at_percent: 0.8

lifecycle:
  on_start:
    - "fetch_user_db -> user_profile"
````

---

## 2. Configure Infrastructure

```yaml
# Xulcanfile

version: "1.0.0"

kernel:
  vault:
    driver: "env"

  state_store:
    driver: "memory"

  ledger:
    driver: "memory"

providers:
  llm:
    default: "openai"

    instances:
      openai:
        driver: "openai"
        model: "gpt-4o"
```

---

## 3. Run the System

```python
import asyncio

from xulcan.app import Xulcan


async def main():
    os = await Xulcan.from_manifest("Xulcanfile")

    @os.tool(description="Fetch user profile")
    async def fetch_user_db(user_id: str, state_store, run_id):
        return {
            "name": "Juan",
            "plan": "Premium"
        }

    blueprint = os.agent_registry["support_agent"]

    run_id, response = await os.run(
        prompt="I want to cancel my account and request a refund.",
        agent_id="user-123",
        blueprint=blueprint
    )

    print(response)

    audit = await os.get_audit(run_id)

    print(
        audit["summary"]["total_usage"]["total_tokens"]
    )


if __name__ == "__main__":
    asyncio.run(main())
```

---

# 📂 Project Structure

```text
xulcan/
├── core/         # Immutable primitives and usage metrics
├── protocol/     # Universal IO contracts and message schemas
├── blueprint/    # Declarative agent schemas and YAML parsing
├── manifest/     # Infrastructure topology definitions
├── runtime/      # Runtime assembly and dependency injection
├── kernel/       # FSM orchestration and execution engine
├── governance/   # Bursar, Sentinel, HumanGate
├── context/      # Context windowing and sanitization
├── llm/          # Provider adapters and fallback orchestration
├── tools/        # Tool router, sandboxes, sub-agents
├── memory/       # StateStore and Vault implementations
├── ledger/       # Event sourcing and projections
└── signals/      # IPC and firehose event streams
```

---

# 🛡️ Security & Isolation

* Secrets are injected through infrastructure drivers, never exposed to models.
* Governance policies execute before side-effectful tool calls.
* Suspended runs release workers completely.
* FSM state can be rehydrated across distributed nodes.
* Recursive payload inspection prevents deeply nested injection patterns.
* Runtime execution can be isolated through ephemeral sandboxes.

---

# 📜 License

Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

Xulcan is free software designed for transparent, auditable,
and governable AI infrastructure.
