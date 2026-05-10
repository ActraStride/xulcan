# Xulcan
Deterministic agentic operating system for building, executing, and auditing AI agents with typed architecture, Event Sourcing, and explicit governance.

[![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## What is Xulcan
Xulcan clearly decouples:
- **Agent Ontology** (what it is and how it thinks): `blueprint/`, `protocol/`, `core/`
- **Infrastructure** (where it runs): `manifest/`, `registry/`, `runtime/`
- **Execution** (how it behaves): `kernel/`, `tools/`, `governance/`, `history/`, `signals/`

Result: Portable agents (YAML), deterministic execution (FSM), and full traceability (append-only ledger).

## Startup Pipeline
Current composition flow:
1. `Xulcan.from_manifest(...)` in `app/xulcan/app.py`
2. `RegistryContainer` + `bootstrap_registries(...)` in `app/xulcan/registry/`
3. `ManifestResolver` (Stage 1) materializes infrastructure from `infraprint.yml`
4. `RuntimeAssembler` (Stage 2) assembles the `SystemEnvironment`, executors, and `ProtoKernel`
5. `RuntimeContext` exposes the final execution graph
6. The `Xulcan` facade enables the DX API (`@tool`, `add_agent`, `enable_sandbox`, `run`, `get_audit`)

## Framework Ontology
### `core/`
Immutable and semantic primitives (`ImmutableRecord`, `MachineID`, `SemanticText`, etc.) for strict validation and security boundaries.

### `manifest/`
Infrastructure schema (`InfraprintManifest`): kernel infra (ledger/event_bus/state_store/vault), LLM providers, and blueprint instructions.

### `blueprint/`
Agent DNA (`AgentBlueprint`):
- Identity (`id`, `name`, `version`)
- Cognition (`model`, `fallbacks`, `system_prompt`, `context`)
- Capabilities (`tools`, `lifecycle`)
- Budget Governance (`governance.budget`)

### `protocol/`
Conversational and tool contracts:
- Typed messages (`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage`)
- Secure tool calling (`ToolCall`, `ToolDefinition`, `FunctionDef`)

### `signals/`
Signals for the event bus:
- `BroadcastEvent` (1→N, kernel→world)
- `IPCMessage` (1→1, channel-directed)

### `history/`
Immutable event ledger:
- Lifecycle (`RunCreated`, `RunCompleted`, `RunFailed`)
- Inference (`ModelRequest`, `ModelResponse`, `ModelFallback`)
- Tools (`ToolExecution`, `ToolOutput`)
- Governance (`PolicyViolation`, `HumanInterventionRequired`, `HumanInterventionResult`)

## Execution: Kernel + FSM
`ProtoKernel` (`app/xulcan/kernel/orchestrator.py`) drives the deterministic loop.
Key states (`app/xulcan/kernel/states.py`):
- Hydration: `CREATED -> HYDRATING -> HYDRATED`
- Control: `CHECKING_BUDGET`, `PREPARING_CONTEXT`, `COMPACTING_CONTEXT`
- Inference: `CALLING_MODEL`, `PROCESSING_RESPONSE`
- Tools: `PARSING_TOOL_ARGS`, `CHECKING_POLICY`, `EXECUTING_TOOL`
- Suspension: `SUSPENDED` (waits for external recovery)
- Resilience: `RETRYING`, `HANDLING_ERROR`
- Terminal: `COMPLETED`, `FAILED`

Effective Guardrails:
- `MAX_LOOPS` to prevent infinite loops
- Retries with backoff for transient failures
- `StateStore` cleanup upon completion
- Fallback mechanisms between providers/models

## Runtime, Memory, and Tools
- `runtime/`: Separation of Stage 1 (infra resolver) and Stage 2 (executable runtime assembly)
- `memory/state`: Ephemeral blackboard per `run_id`
- `memory/vault`: Secrets kept outside of prompts/blueprints
- `tools/router`: Routing by name + Jinja template resolution with memory
- `tools/executors`: Local, sub-agents, and sandbox (Docker optional)

## Governance
Components:
- **Bursar**: Budgeting (`approved`, `warn`, `halt`)
- **Sentinel**: Tool policy (`approved`, `blocked`, `escalate`)
- **HumanGate**: Human decision-making (`approved`, `rejected`)

Strategy registries are loaded in `registry/bootstrap.py` and built via `ProviderRegistry`.

## Main HTTP API (`mack.py`)
Operational entry point: `app/xulcan/mack.py`

Main endpoints:
- `GET /health/live`
- `GET /health/ready`
- `GET /v1/blueprints`
- `POST /v1/blueprints/reload`
- `POST /v1/agent/run`
- `GET /v1/runs/{run_id}/stream` (SSE firehose)
- `GET /v1/runs/{run_id}/audit`
- `POST /v1/runs/{run_id}/human-response`

## Minimal Configuration (`infraprint.yml`)
Base repository example:
- `kernel.*.driver: "memory"` for ledger, state_store, event_bus, and vault
- `providers.llm.instances`: `google`, `github`
- `blueprints.paths`: `./blueprints`
- `blueprints.autoload: true`

## Quick Start
### Prerequisites
- Python 3.10+
- Docker + Docker Compose
- Make

### Local Development
```bash
pip install -e .
make dev
```

### Verification
```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

### Testing
```bash
make test
make fuzz
make test-all
```

## Project Structure (Summary)
```text
app/xulcan/
├── app.py          # Xulcan public facade
├── mack.py         # Operational FastAPI API
├── runtime/        # Resolver + Assembler + RuntimeContext
├── registry/       # Container + bootstrap for adapters/strategies
├── kernel/         # FSM, orchestrator, environment, and interfaces
├── blueprint/      # Agent schema and components
├── manifest/       # Infraprint schema (declarative infra)
├── protocol/       # Messages and tool contracts
├── signals/        # Bus signals (broadcast/ipc)
├── history/        # Execution events (ledger)
├── tools/          # Router and executors
├── memory/         # state (blackboard) + vault (secrets)
└── governance/     # bursar, sentinel, human gate
```