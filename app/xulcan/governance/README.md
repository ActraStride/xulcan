# Xulcan Governance — Dual-Cascade Architecture

## The Two Cascades Are Ontologically Distinct

Governance in Xulcan contains two mechanisms that must **never be conflated**.
They have different semantics, different lifecycles, and different inheritance directions.

---

# Cascade 1: Bursar (Budget)

**Nature:** Accumulative, per-run, hierarchical with MIN resolution.

**Question it answers:** Does this run still have enough resources to continue?

**When it evaluates:** Before each reasoning-loop iteration (`CHECKING_BUDGET`).

**Inheritance:** App → Agent (MIN). If the App declares `usd_limit: 2.00` and the Agent
declares `usd_limit: 5.00`, the effective limit is $2.00. The most restrictive
limit always wins. Implemented via `CompositeBursarStrategy` in #52.

**Semantics:** It is **accumulative**. The Bursar observes `cumulative_usage` — the total
amount consumed by the run up to that point. Crossing the limit permanently halts
the run (`BursarVerdict.HALT` → `BursarHaltError`).

```text
App.governance.bursar
        ↓ MIN
Agent.governance.bursar
        ↓
GovernanceResolver → CompositeBursarStrategy
        ↓
ProtoKernel.CHECKING_BUDGET (unchanged)
```

**Deferred:** Cross-run aggregation (`QuotaStore`) → v0.5.0.

---

# Cascade 2: Sentinel / HumanGate

**Nature:** Instantaneous, per-tool-call, CSS-style inheritance (the most specific rule wins).

**Question it answers:** Is this specific tool call allowed?

**When it evaluates:** Before executing each tool call (`CHECKING_POLICY`).

**Inheritance:** Three-level resolution, most specific first:

```text
1. tool_config.governance.sentinel   (explicit per-tool declaration)
        ↓ if not found
2. blueprint.default_sentinel        (per-blueprint fallback)
        ↓ always exists via default_factory
3. "passthrough" / "auto_approve"    (hardcoded — never fails)
```

**Semantics:** It is **instantaneous**. The Sentinel evaluates only the current tool call,
with no memory of previous calls. It is not accumulative.

**Difference from Bursar:** The Bursar looks at the past (how much has been consumed).
The Sentinel looks at the present (what is about to be executed).

---

# Why They Cannot Be Conflated

| Dimension       | Bursar                                 | Sentinel / HumanGate                            |
| --------------- | -------------------------------------- | ----------------------------------------------- |
| Evaluation unit | Entire run                             | Individual tool call                            |
| Nature          | Accumulative                           | Instantaneous                                   |
| Inheritance     | Hierarchical MIN                       | CSS-style (most specific wins)                  |
| Lifecycle       | Once per loop                          | Once per tool call                              |
| Result          | `BursarVerdict` (`APPROVED/WARN/HALT`) | `SentinelVerdict` (`APPROVED/BLOCKED/ESCALATE`) |
| Terminal error  | `BursarHaltError`                      | `PolicyViolation` event                         |

A system that mixes both eventually produces bugs such as:
“the agent was blocked because its accumulated budget exceeded the tool-call policy” —
a sentence that is semantically meaningless.
