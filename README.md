# Xulcan


**Xulcan es un framework de backend, "API-first", para construir, gestionar y desplegar agentes de IA avanzados.**

Su misión es abstraer la complejidad de la orquestación de LLMs, la gestión de memoria y el uso de herramientas, permitiendo a los desarrolladores integrar capacidades de razonamiento complejo en sus aplicaciones a través de una configuración declarativa y una API REST robusta.

Este proyecto es de código abierto, pero se está construyendo como una plataforma personal con la ambición de convertirse en un ecosistema completo para el desarrollo agéntico.

---

## Visión y Filosofía

La inspiración central de Xulcan es la metáfora de un **compás de arquitecto con un adaptador universal**. Este símbolo representa nuestros principios de diseño:

*   **Precisión:** Transformar el lenguaje natural ambiguo en acciones estructuradas y precisas.
*   **Modularidad:** Construir agentes a partir de componentes conectables (`pluggable`) como "herramientas" y "memorias".
*   **Orquestación:** Conectar el contexto (el punto fijo) con la acción (el punto móvil) a través de un proceso de razonamiento.

Creemos en la **Configuración como Código** y en un enfoque **API-First** para garantizar sistemas de IA desacoplados, mantenibles y escalables.

## Arquitectura Conceptual

Xulcan está siendo diseñado como un servicio alojado que interactúa con las aplicaciones cliente a través de APIs.

1.  **Dashboard de Xulcan:** Una interfaz web central donde los desarrolladores definen y gestionan sus recursos:
    *   **Agentes:** Se definen con una personalidad (`system_prompt`), un modelo de LLM y un conjunto de capacidades.
    *   **Herramientas (Tools):** Se registran herramientas internas (ej. `web_search`) y externas (APIs del cliente), incluyendo su esquema y método de autenticación.
    *   **Memoria:** Se configuran las bases de conocimiento (RAG) que los agentes pueden consultar.

2.  **Núcleo Agéntico (El Motor):** El backend de Xulcan, que incluye:
    *   Un **`LLMClient` agnóstico** con adaptadores para múltiples proveedores (Gemini, OpenAI, Anthropic).
    *   Un **`ToolExecutor`** que ejecuta herramientas internas o llama de forma segura a las APIs externas configuradas.
    *   Un **`MemoryManager`** para la memoria a corto plazo (Redis) y largo plazo (Faiss).
    *   Un **`Executor`** que orquesta el ciclo de razonamiento (`Chain of Thought`).

3.  **Integración del Cliente:** El desarrollador integra su aplicación con Xulcan a través de un modelo seguro y simple, sin necesidad de escribir lógica de orquestación compleja en su propio backend.

## Roadmap del Proyecto (Hasta Mayo 2026)

Este proyecto se desarrollará en fases incrementales, centrándose en construir una base sólida.

### Trimestre 1: La Cimentación y el Primer Agente
*   **[ ] Mes 1:** Diseño del núcleo, investigación de APIs de LLMs, implementación del `AgentManager` y el primer `LLMAdapter`.
*   **[ ] Mes 2:** Implementación del sistema de **Herramientas** (`ToolRegistry`, `ToolExecutor`) y el ciclo de razonamiento de un solo paso.
*   **[ ] Mes 3:** Integración de la **memoria a corto plazo** (Redis) y el segundo `LLMAdapter`.

### Trimestre 2: Capacidades Avanzadas y Ecosistema
*   **[ ] Mes 4:** Implementación de la **memoria a largo plazo (RAG)** con Faiss y el tercer `LLMAdapter`.
*   **[ ] Mes 5:** Implementación del **razonamiento multi-paso (Chain of Thought)** y la infraestructura para tareas en segundo plano (Celery).
*   **[ ] Mes 6:** Creación del **Dashboard de Administración MVP** y "hardening" de la plataforma (seguridad, logging, documentación).

## Estado Actual

El proyecto se encuentra en la fase inicial de diseño y configuración. El repositorio está vacío, pero la planificación conceptual está completa. ¡La construcción comienza ahora!

## Cómo Contribuir (Futuro)

Este es actualmente un proyecto personal, pero con la ambición de convertirse en código abierto. La información sobre cómo contribuir se añadirá una vez que el núcleo del proyecto esté más maduro.

---

*Este documento sirve como la "Estrella Polar" para el desarrollo de Xulcan. Todas las decisiones técnicas y de producto deben alinearse con la visión y la arquitectura aquí descritas.*