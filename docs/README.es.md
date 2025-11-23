# Xulcan

Idiomas disponibles: [English](../README.md) · [Español](README.es.md) · [Francés](README.fr.md) · [Ruso](README.ru.md) · [Árabe](README.ar.md) · [Chino (Mandarín)](README.zh.md)


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

1.  **Dashboard de Xulcan:** Interfaz web donde se definen Agentes, Herramientas y Memorias.
2.  **Núcleo Agéntico (El Motor):**
    *   **`LLMClient`:** Adaptadores agnósticos (Gemini, OpenAI, Anthropic).
    *   **`ToolExecutor`:** Ejecución segura de herramientas.
    *   **`MemoryManager`:** Memoria a corto (Redis) y largo plazo (Faiss).
    *   **`Executor`:** Orquestación del razonamiento (`Chain of Thought`).
3.  **Integración del Cliente:** Modelo seguro y simple vía API REST.

---

## 🛠 Flujo de Desarrollo y Contribución

Para mantener la estabilidad del sistema y organizar las releases, utilizamos **Git Flow**.

### Estrategia de Ramas
*   **`main`:** 🔴 **Producción.** Contiene únicamente código estable, versionado y listo para despliegue. Nadie hace commit directo aquí.
*   **`develop`:** 🟡 **Integración (Next Release).** Es la rama de trabajo principal. Aquí se fusionan todas las nuevas funcionalidades para probarlas en conjunto antes de una release.
*   **`feature/*`:** 🟢 **Desarrollo.** Ramas temporales para nuevas funcionalidades (ej. `feature/infra-logging`).
    *   Nacen de: `develop`
    *   Se fusionan en: `develop`
*   **`hotfix/*`:** 🚑 **Urgencias.** Para errores críticos en producción. Nacen de `main` y se fusionan en `main` y `develop`.

### Convención de Commits
Seguimos [Conventional Commits](https://www.conventionalcommits.org/) para mantener un historial semántico:
*   `feat:` Nueva funcionalidad.
*   `fix:` Corrección de error.
*   `chore:` Mantenimiento/configuración.
*   `refactor:` Cambios de código que no alteran la funcionalidad.

### Política de Pull Requests (PR) & Merge
1.  **Feature -> Develop:**
    *   Se usa **Squash and Merge**.
    *   *Objetivo:* Que cada funcionalidad aparezca como un solo commit limpio en el historial de `develop`.
2.  **Develop -> Main (Release):**
    *   Se usa **Merge Commit** (Create a merge commit).
    *   *Objetivo:* Mantener la historia de que un grupo de funcionalidades se liberaron juntas como una versión (ej. v0.1.0).
3.  **Tests:** El CI (Docker build + Pytest) debe pasar obligatoriamente antes de cualquier merge.

---

## Roadmap del Proyecto (Hasta Mayo 2026)

### Trimestre 1: La Cimentación y el Primer Agente
*   **[x] Infraestructura Base:** Dockerización, Postgres, Redis y estructura del proyecto.
*   **[ ] Mes 1:** Diseño del núcleo, investigación de APIs de LLMs, implementación del `AgentManager` y el primer `LLMAdapter`.
*   **[ ] Mes 2:** Implementación del sistema de **Herramientas** (`ToolRegistry`, `ToolExecutor`).
*   **[ ] Mes 3:** Integración de la **memoria a corto plazo** (Redis) y el segundo `LLMAdapter`.

### Trimestre 2: Capacidades Avanzadas y Ecosistema
*   **[ ] Mes 4:** Memoria a largo plazo (RAG) y tercer `LLMAdapter`.
*   **[ ] Mes 5:** Razonamiento multi-paso (Chain of Thought) y Workers (Celery).
*   **[ ] Mes 6:** Dashboard MVP y hardening (seguridad, observabilidad).

## Estado Actual

🚀 **Fase de Construcción Activa.**
La infraestructura base (Docker, BD, Cache) está operativa. Actualmente se está implementando el sistema de **Logging Estructurado** y Observabilidad.

---

*Este documento sirve como la "Estrella Polar" para el desarrollo de Xulcan. Todas las decisiones técnicas y de producto deben alinearse con la visión y la arquitectura aquí descritas.*
