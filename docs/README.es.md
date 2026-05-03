# Xulcan

<p align="center">
    <a href="../README.md">English 🇬🇧</a>
    · <a href="README.es.md">Spanish 🇲🇽</a>
</p>

**El Sistema Operativo Determinista para Agentes de IA.**

Xulcan es un **Sistema Operativo Agéntico (Agentic OS)** estricto y fuertemente tipado, diseñado desde cero para entornos de ingeniería y producción. Basado en los principios del Diseño Guiado por el Dominio (DDD) y la Cibernética, trata a los Agentes como Datos, al Historial como un Ledger (Libro Mayor) inmutable, y a la Ejecución como una máquina de estados determinista.

[![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)](../LICENSE)
[![Architecture](https://img.shields.io/badge/Architecture-Event%20Sourced-purple.svg)]()
[![Core](https://img.shields.io/badge/Core-Frozen%20v1.0-green.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## El Concepto: El SO Agéntico 🖥️

Entender Xulcan es fácil si lo mapeas a la arquitectura de computadoras clásica (Von Neumann). Separamos el caos probabilístico de los LLMs de la rigurosidad de la ingeniería de software:

| Módulo del SO | Equivalente en IA | Descripción |
| :--- | :--- | :--- |
| **CPU (ALU)** | **Adaptadores LLM** | Los modelos (Gemini, Ollama). Son *stateless* (sin estado), aislados y solo procesan semántica para emitir intenciones (`ToolCalls`). |
| **Kernel / FSM** | **ProtoKernel** | El bucle de ejecución. Gestiona los presupuestos de tokens, mitiga la entropía, maneja errores de forma segura y orquesta la máquina de estados. |
| **Memoria RAM** | **StateStore (Pizarra)** | Memoria compartida efímera. Permite pasar cargas útiles gigantes (como respuestas de APIs o PDFs) por referencia en lugar de quemar tokens del LLM. |
| **Periféricos** | **Sandbox / Red** | Las "Manos". Contenedores Docker aislados y ejecutores de red que interactúan de forma segura con el mundo real. |
| **Disco Duro** | **El Ledger** | Un registro inmutable de Event Sourcing (*append-only*) de cada pensamiento y acción. Permite una auditabilidad forense perfecta. |

---

## Infraestructura como Código (IaC) para Agentes 📜

Xulcan separa drásticamente la **Ingeniería de Software** de la **Ingeniería de Prompts**. Los agentes no están programados *hardcodeados* en Python; se definen de manera declarativa en manifiestos YAML.

```yaml
# manifests/analyst_agent.yaml
name: "Analista Financiero"
model_provider: "google"
model_name: "gemini-2.5-flash"
system_prompt: "Eres un analista experto. Usa tu sandbox para calcular..."
tools:
  - name: "network_api_get"
    enabled: true
  - name: "sandbox_run_bash"
    enabled: true
```
*Simplemente carga el manifiesto y deja que el Sistema Operativo se encargue del resto.*

---

## Inicio Rápido

### Prerrequisitos
- Docker y Docker Compose
- Make (Linux/Mac/WSL2)
- Python 3.11+

### Opción A: Uso Standalone (Script de Python)
Perfecto para probar y ejecutar agentes de manera local.
```bash
# 1. Clonar e Instalar
git clone https://github.com/ActraStride/xulcan.git
cd xulcan
pip install -e .

# 2. Ejecutar el agente de prueba
python demo.py
```

### Opción B: Despliegue de Servidor (FastAPI)
Levanta la infraestructura B2B completa de Nivel 2 con PostgreSQL y Redis.
```bash
# Iniciar la API de Xulcan y las Bases de Datos
make dev

# Verificar que el SO está vivo
curl http://localhost:8000/health/live
```

---

## Estructura del Proyecto

La base de código sigue estrictamente los principios de la Arquitectura Hexagonal. Las capas superiores dependen de las inferiores, nunca al revés.

```text
xulcan/
├── app/
│   ├── xulcan/
│   │   ├── core/          # Nivel 0: Primitivas y Economía
│   │   ├── protocol/      # Nivel 1: Mensajes y Esquemas de Herramientas
│   │   ├── blueprint/     # Nivel 1: Carga YAML y Nombramiento de Agentes
│   │   ├── ledger/        # Nivel 2: Event Sourcing y Auditabilidad
│   │   ├── memory/        # Nivel 2: StateStore (Memoria RAM Compartida)
│   │   ├── llm/           # Nivel 3: Adaptadores Stateless (Gemini, Ollama)
│   │   ├── tools/         # Nivel 3: Ejecutores (Docker Sandbox, Network)
│   │   └── kernel/        # Nivel 3: Motor de Ejecución FSM
│   └── main.py            # Entrypoint de FastAPI (Capa de Envoltura)
├── manifests/             # 📜 Definiciones de Agentes IaC (YAML)
├── demo.py                # Ejemplo de Cliente Standalone
├── tests/                 # Suite de pruebas Pytest
├── docker-compose.yaml
└── Makefile
```

---

## ¿Por qué Xulcan?

1.  **Control de Entropía Estricto:** El LLM no dicta el flujo del programa. La Máquina de Estados Finitos (FSM) del Kernel atrapa los errores, previene los bucles infinitos y fuerza el determinismo.
2.  **Verdadero Aislamiento Físico:** El código generado por el agente se ejecuta en contenedores Docker efímeros de inicialización perezosa (`SandboxExecutor`), con riesgo cero para la máquina anfitriona.
3.  **Auditabilidad Forense:** El `Ledger` registra cada token, latencia y ejecución de herramienta. Nunca tendrás que preguntarte "¿Por qué el agente hizo eso?". Tienes la prueba matemática.
4.  **Enjambres Fractales:** Los agentes pueden invocar otros Blueprints como si fueran herramientas (`SubAgentExecutor`), creando equipos jerárquicos de manera nativa.

***
