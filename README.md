# Xulcan
Sistema operativo agéntico determinista para construir, ejecutar y auditar agentes de IA con arquitectura tipada, Event Sourcing y gobernanza explícita.

[![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Qué es Xulcan
Xulcan separa claramente:
- **Ontología del agente** (qué es y cómo piensa): `blueprint/`, `protocol/`, `core/`
- **Infraestructura** (dónde corre): `manifest/`, `registry/`, `runtime/`
- **Ejecución** (cómo se comporta): `kernel/`, `tools/`, `governance/`, `history/`, `signals/`

Resultado: agentes portables (YAML), ejecución determinista (FSM) y trazabilidad completa (ledger append-only).

## Pipeline real de arranque
Flujo de composición actual:
1. `Xulcan.from_manifest(...)` en `app/xulcan/app.py`
2. `RegistryContainer` + `bootstrap_registries(...)` en `app/xulcan/registry/`
3. `ManifestResolver` (Stage 1) materializa infraestructura desde `infraprint.yml`
4. `RuntimeAssembler` (Stage 2) ensambla `SystemEnvironment`, ejecutores y `ProtoKernel`
5. `RuntimeContext` expone el grafo final de ejecución
6. La fachada `Xulcan` habilita API de DX (`@tool`, `add_agent`, `enable_sandbox`, `run`, `get_audit`)

## Ontología del framework
### `core/`
Primitivas inmutables y semánticas (`ImmutableRecord`, `MachineID`, `SemanticText`, etc.) para validación estricta y fronteras de seguridad.

### `manifest/`
Schema de infraestructura (`InfraprintManifest`): kernel infra (ledger/event_bus/state_store/vault), proveedores LLM e instrucciones de blueprints.

### `blueprint/`
DNA del agente (`AgentBlueprint`):
- identidad (`id`, `name`, `version`)
- cognición (`model`, `fallbacks`, `system_prompt`, `context`)
- capacidades (`tools`, `lifecycle`)
- gobernanza de presupuesto (`governance.budget`)

### `protocol/`
Contrato conversacional y de herramientas:
- mensajes tipados (`SystemMessage`, `UserMessage`, `AssistantMessage`, `ToolMessage`)
- tool calling seguro (`ToolCall`, `ToolDefinition`, `FunctionDef`)

### `signals/`
Señales para bus de eventos:
- `BroadcastEvent` (1→N, kernel→mundo)
- `IPCMessage` (1→1, dirigido por canal)

### `history/`
Ledger de eventos inmutable:
- ciclo de vida (`RunCreated`, `RunCompleted`, `RunFailed`)
- inferencia (`ModelRequest`, `ModelResponse`, `ModelFallback`)
- herramientas (`ToolExecution`, `ToolOutput`)
- gobernanza (`PolicyViolation`, `HumanInterventionRequired`, `HumanInterventionResult`)

## Ejecución: Kernel + FSM
`ProtoKernel` (`app/xulcan/kernel/orchestrator.py`) conduce el bucle determinista.
Estados clave (`app/xulcan/kernel/states.py`):
- hidratación: `CREATED -> HYDRATING -> HYDRATED`
- control: `CHECKING_BUDGET`, `PREPARING_CONTEXT`, `COMPACTING_CONTEXT`
- inferencia: `CALLING_MODEL`, `PROCESSING_RESPONSE`
- herramientas: `PARSING_TOOL_ARGS`, `CHECKING_POLICY`, `EXECUTING_TOOL`
- suspensión: `SUSPENDED` (espera recuperación externa)
- resiliencia: `RETRYING`, `HANDLING_ERROR`
- terminales: `COMPLETED`, `FAILED`

Guardrails efectivos:
- `MAX_LOOPS` anti-loop infinito
- reintentos con backoff para fallas transitorias
- limpieza de `StateStore` al finalizar
- fallback entre proveedores/modelos

## Runtime, memoria y herramientas
- `runtime/`: separación Stage 1 (resolver infra) y Stage 2 (ensamblar runtime ejecutable)
- `memory/state`: blackboard efímero por `run_id`
- `memory/vault`: secretos fuera de prompts/blueprints
- `tools/router`: enrutamiento por nombre + resolución de plantillas Jinja con memoria
- `tools/executors`: local, subagentes y sandbox (Docker opcional)

## Gobernanza
Componentes:
- **Bursar**: presupuesto (`approved`, `warn`, `halt`)
- **Sentinel**: política de tools (`approved`, `blocked`, `escalate`)
- **HumanGate**: decisión humana (`approved`, `rejected`)

Los registros de estrategias se cargan en `registry/bootstrap.py` y se construyen vía `ProviderRegistry`.

## API HTTP principal (`mack.py`)
Entrypoint operativo: `app/xulcan/mack.py`

Endpoints principales:
- `GET /health/live`
- `GET /health/ready`
- `GET /v1/blueprints`
- `POST /v1/blueprints/reload`
- `POST /v1/agent/run`
- `GET /v1/runs/{run_id}/stream` (SSE firehose)
- `GET /v1/runs/{run_id}/audit`
- `POST /v1/runs/{run_id}/human-response`

## Configuración mínima (`infraprint.yml`)
Ejemplo base del repositorio:
- `kernel.*.driver: "memory"` para ledger, state_store, event_bus, vault
- `providers.llm.instances`: `google`, `github`
- `blueprints.paths`: `./blueprints`
- `blueprints.autoload: true`

## Inicio rápido
### Prerrequisitos
- Python 3.10+
- Docker + Docker Compose
- Make

### Desarrollo local
```bash
pip install -e .
make dev
```

### Verificación
```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

### Pruebas
```bash
make test
make fuzz
make test-all
```

## Estructura de proyecto (resumen)
```text
app/xulcan/
├── app.py          # Fachada pública Xulcan
├── mack.py         # API FastAPI operativa
├── runtime/        # Resolver + Assembler + RuntimeContext
├── registry/       # Container + bootstrap de adapters/strategies
├── kernel/         # FSM, orquestador, entorno e interfaces
├── blueprint/      # Esquema y componentes del agente
├── manifest/       # Esquema infraprint (infra declarativa)
├── protocol/       # Mensajes y contrato de herramientas
├── signals/        # Señales de bus (broadcast/ipc)
├── history/        # Eventos de ejecución (ledger)
├── tools/          # Router y ejecutores
├── memory/         # state (blackboard) + vault (secretos)
└── governance/     # bursar, sentinel, human gate
```
