# Xulcan

Available languages: [English](README.md) · [Spanish](docs/README.es.md) · [French](docs/README.fr.md) · [Russian](docs/README.ru.md) · [Arabic](docs/README.ar.md) · [Chinese (Mandarin)](docs/README.zh.md)

**Xulcan is an API-first backend framework for building, operating, and deploying advanced AI agents.**

Its mission is to abstract the complexity of LLM orchestration, memory management, and tool usage so developers can integrate complex reasoning capabilities into their applications through declarative configuration and a robust REST API.

The project is open source, yet it is being crafted as a personal platform with the ambition of growing into a complete ecosystem for agentic development.

---

## Vision and Philosophy

Xulcan draws its inspiration from the metaphor of an **architect's compass with a universal adapter**. This symbol conveys our design principles:

* **Precision:** Turning ambiguous natural language into structured, accurate actions.
* **Modularity:** Composing agents from pluggable components such as tools and memories.
* **Orchestration:** Connecting context (the fixed point) with action (the moving point) through a deliberate reasoning process.

We believe in **Configuration as Code** and an **API-first** mindset to guarantee decoupled, maintainable, and scalable AI systems.

## Conceptual Architecture

Xulcan is being designed as a managed service that interacts with client applications via APIs.

1. **Xulcan Dashboard:** Web interface where Agents, Tools, and Memories are defined.
2. **Agentic Core (The Engine):**
   * **`LLMClient`:** Agnostic adapters (Gemini, OpenAI, Anthropic).
   * **`ToolExecutor`:** Safe tool execution.
   * **`MemoryManager`:** Short-term (Redis) and long-term (Faiss) memory.
   * **`Executor`:** Reasoning orchestration (Chain of Thought).
3. **Client Integration:** Secure and simple interaction through a REST API.

---

## 🛠 Development and Contribution Flow

To preserve system stability and manage releases, we follow **Git Flow**.

### Branch Strategy
* **`main`:** 🔴 **Production.** Only stable, versioned, deployment-ready code lives here. No one commits directly to this branch.
* **`develop`:** 🟡 **Integration (Next Release).** The primary working branch where new features merge and are validated together before a release.
* **`feature/*`:** 🟢 **Development.** Temporary branches for new functionality (for example, `feature/infra-logging`).
  * Branches from: `develop`
  * Merges into: `develop`
* **`hotfix/*`:** 🚑 **Emergency Fixes.** Critical production fixes. They branch from `main` and merge back into both `main` and `develop`.

### Commit Convention
We follow [Conventional Commits](https://www.conventionalcommits.org/) to keep a semantic history:
* `feat:` New functionality.
* `fix:` Bug fix.
* `chore:` Maintenance or configuration updates.
* `refactor:` Non-functional changes to the code.

### Pull Request & Merge Policy
1. **Feature -> Develop:**
   * Use **Squash and Merge**.
   * *Goal:* Each feature appears as a single, clean commit in the `develop` history.
2. **Develop -> Main (Release):**
   * Use **Merge Commit** (Create a merge commit).
   * *Goal:* Preserve the narrative that a bundle of features shipped together as a version (for example, v0.1.0).
3. **Tests:** CI (Docker build + Pytest) must pass before any merge.

---

## Project Roadmap (Through May 2026)

### Quarter 1: Foundation and First Agent
* **[x] Base Infrastructure:** Dockerization, Postgres, Redis, and project scaffolding.
* **[ ] Month 1:** Core design, LLM API research, `AgentManager`, and the first `LLMAdapter`.
* **[ ] Month 2:** Tooling system (`ToolRegistry`, `ToolExecutor`).
* **[ ] Month 3:** Short-term memory integration (Redis) and the second `LLMAdapter`.

### Quarter 2: Advanced Capabilities and Ecosystem
* **[ ] Month 4:** Long-term memory (RAG) and a third `LLMAdapter`.
* **[ ] Month 5:** Multi-step reasoning (Chain of Thought) and Workers (Celery).
* **[ ] Month 6:** Dashboard MVP and hardening (security, observability).

## Current Status

🚀 **Active Build Phase.**
Base infrastructure (Docker, database, cache) is operational. Structured logging and observability are currently being implemented.

---

*This document is the North Star for Xulcan's development. Every technical and product decision should align with the vision and architecture described here.*