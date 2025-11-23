# Xulcan

Langues disponibles: [Anglais](../README.md) · [Espagnol](README.es.md) · [Français](README.fr.md) · [Russe](README.ru.md) · [Arabe](README.ar.md) · [Chinois (mandarin)](README.zh.md)

**Xulcan est un framework backend « API-first » pour créer, exploiter et déployer des agents d'IA avancés.**

Sa mission est d'abstraire la complexité de l'orchestration des LLM, de la gestion de la mémoire et de l'utilisation des outils afin que les développeurs puissent intégrer des capacités de raisonnement avancé dans leurs applications au moyen d'une configuration déclarative et d'une API REST robuste.

Le projet est open source, mais il est développé comme une plateforme personnelle avec l'ambition de devenir un écosystème complet pour le développement agentique.

---

## Vision et philosophie

Xulcan s'inspire de la métaphore d'un **compas d'architecte doté d'un adaptateur universel**. Ce symbole reflète nos principes de conception :

* **Précision :** Transformer un langage naturel ambigu en actions structurées et précises.
* **Modularité :** Composer des agents à partir de composants enfichables, tels que des outils et des mémoires.
* **Orchestration :** Relier le contexte (point fixe) à l'action (point mobile) via un processus de raisonnement intentionnel.

Nous croyons en la **Configuration comme Code** et en une démarche **API-first** pour garantir des systèmes d'IA découplés, maintenables et évolutifs.

## Architecture conceptuelle

Xulcan est conçu comme un service managé qui interagit avec les applications clientes par l'intermédiaire d'API.

1. **Tableau de bord Xulcan :** Interface web où sont définis les Agents, Outils et Mémoires.
2. **Noyau agentique (le moteur) :**
	* **`LLMClient` :** Adaptateurs agnostiques (Gemini, OpenAI, Anthropic).
	* **`ToolExecutor` :** Exécution sûre des outils.
	* **`MemoryManager` :** Mémoire court terme (Redis) et long terme (Faiss).
	* **`Executor` :** Orchestration du raisonnement (Chain of Thought).
3. **Intégration client :** Interaction sécurisée et simple via une API REST.

---

## 🛠 Parcours de développement et de contribution

Pour préserver la stabilité du système et organiser les releases, nous suivons **Git Flow**.

### Stratégie de branches
* **`main` :** 🔴 **Production.** Seul du code stable, versionné et prêt au déploiement y est autorisé. Aucun commit direct.
* **`develop` :** 🟡 **Intégration (prochaine release).** Branche principale où les nouvelles fonctionnalités sont fusionnées et testées ensemble avant une release.
* **`feature/*` :** 🟢 **Développement.** Branches temporaires pour de nouvelles fonctionnalités (par exemple `feature/infra-logging`).
  * Naît de : `develop`
  * Fusionne dans : `develop`
* **`hotfix/*` :** 🚑 **Urgences.** Correctifs critiques pour la production. Naissent de `main` et sont fusionnés dans `main` et `develop`.

### Convention de commits
Nous suivons [Conventional Commits](https://www.conventionalcommits.org/) pour maintenir un historique sémantique :
* `feat :` Nouvelle fonctionnalité.
* `fix :` Correction de bug.
* `chore :` Tâches de maintenance ou de configuration.
* `refactor :` Modifications du code sans impact fonctionnel.

### Politique de pull requests et de merge
1. **Feature -> Develop :**
	* Utiliser **Squash and Merge**.
	* *Objectif :* Chaque fonctionnalité apparaît comme un commit unique et propre dans l'historique de `develop`.
2. **Develop -> Main (Release) :**
	* Utiliser **Merge Commit** (Create a merge commit).
	* *Objectif :* Conserver le récit d'un ensemble de fonctionnalités livré ensemble en tant que version (par exemple v0.1.0).
3. **Tests :** Le CI (Docker build + Pytest) doit réussir avant toute fusion.

---

## Feuille de route du projet (jusqu'en mai 2026)

### Trimestre 1 : Fondation et premier agent
* **[x] Infrastructure de base :** Dockerisation, Postgres, Redis et structure du projet.
* **[ ] Mois 1 :** Conception du noyau, recherche sur les API LLM, `AgentManager` et premier `LLMAdapter`.
* **[ ] Mois 2 :** Système d'outillage (`ToolRegistry`, `ToolExecutor`).
* **[ ] Mois 3 :** Intégration de la mémoire court terme (Redis) et second `LLMAdapter`.

### Trimestre 2 : Capacités avancées et écosystème
* **[ ] Mois 4 :** Mémoire long terme (RAG) et troisième `LLMAdapter`.
* **[ ] Mois 5 :** Raisonnement multi-étapes (Chain of Thought) et workers (Celery).
* **[ ] Mois 6 :** Tableau de bord MVP et durcissement (sécurité, observabilité).

## État actuel

🚀 **Phase de construction active.**
L'infrastructure de base (Docker, base de données, cache) est opérationnelle. La journalisation structurée et l'observabilité sont en cours de mise en place.

---

*Ce document sert d'étoile polaire pour le développement de Xulcan. Chaque décision technique ou produit doit s'aligner sur la vision et l'architecture décrites ici.*
