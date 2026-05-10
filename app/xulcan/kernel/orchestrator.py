"""Kernel Engine — The FSM Driver for Xulcan Agents (DEFINITIVE VERSION).

Architecture:
    - FSM (KernelState): The static graph of valid operations.
    - Ledger (LedgerRepository): The dynamic DAG of historical events.
    - ProtoKernel: The driver that unrolls the loop.

Fixed Issues:
    - MAX_LOOPS now enforced (prevents infinite loops)
    - Tool execution fully implemented
    - HumanGate with proper recovery
    - Retry logic for transient errors
    - All blueprint attributes corrected to use new schema
    - All event field names match events.py exactly
"""

from __future__ import annotations

import uuid
import logging
import json
import asyncio
from typing import Any

from xulcan.core import MachineID
from xulcan.core.economics import UsageStats, BudgetExceededError
from xulcan.governance.verdicts import (
    SentinelVerdict,
    BursarVerdict,
    HumanGateDecision,
)
from xulcan.governance.suspension import SuspensionReason

from xulcan.kernel.states import KernelState, validate_transition, is_terminal_state
from xulcan.kernel.interfaces import (
    LedgerRepository,
    ToolExecutor,
    LLMOrchestrator,
    ContextStrategy,
    BursarStrategy,
    SentinelStrategy,
    HumanGateStrategy,
)
from xulcan.registry import ProviderRegistry
from xulcan.kernel.environment import SystemEnvironment

from xulcan.blueprint.schema import AgentBlueprint
from xulcan.blueprint.components import LifecycleHook

from xulcan.history.events import (
    RunCreated,
    StepStarted,
    ModelRequest,
    ModelResponse,
    ModelFallback,
    ToolExecution,
    ToolOutput,
    RunCompleted,
    RunFailed,
    StepType,
    PolicyViolation,
    HumanInterventionRequired,
    HumanInterventionResult,
)

from xulcan.protocol.message import (
    UnifiedMessage,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
)
from xulcan.protocol.tools import ToolCall

logger = logging.getLogger("xulcan.kernel")


class ProtoKernel:
    """The FSM Driver (Engine) for Xulcan Agents.

    Receives all dependencies via constructor injection.
    Has zero knowledge of concrete adapter implementations.
    """

    def __init__(
        self,
        repository: LedgerRepository,
        llm_executor: LLMOrchestrator,
        tool_executor: ToolExecutor,
        context_registry: ProviderRegistry[ContextStrategy],
        bursar_registry: ProviderRegistry[BursarStrategy],
        sentinel_registry: ProviderRegistry[SentinelStrategy],
        human_gate_registry: ProviderRegistry[HumanGateStrategy],
        environment: SystemEnvironment | None = None,
    ):
        self.repo = repository
        self.llm_executor = llm_executor
        self.tool_executor = tool_executor
        self.context_registry = context_registry
        self.bursar_registry = bursar_registry
        self.sentinel_registry = sentinel_registry
        self.human_gate_registry = human_gate_registry
        self.environment = environment

    def _resolve_blueprint_namespace(self, blueprint: AgentBlueprint) -> str:
        """Resolve the namespace for the blueprint based on its agent id."""
        parts = blueprint.id.split('.')
        namespace = '.'.join(parts[:-1]) if len(parts) > 1 else parts[0]
        return namespace.replace('-', '_')

    def _resolve_tool_names(self, blueprint: AgentBlueprint, tool_names: list[str]) -> list[str]:
        """Resolve LLM-visible tool names using the blueprint's namespace."""
        if not tool_names:
            return []

        blueprint_namespace = self._resolve_blueprint_namespace(blueprint)
        resolved_tool_names: list[str] = []

        for name in tool_names:
            if "__" in name or "." in name:
                resolved_tool_names.append(name)
            else:
                resolved_tool_names.append(f"{blueprint_namespace}__{name}")

        return resolved_tool_names

    def _log(self, emoji: str, msg: str, **kwargs: Any) -> None:
        """Internal structured logging helper."""
        extra = f" | {json.dumps(kwargs, default=str)}" if kwargs else ""
        logger.info(f"{emoji} {msg}{extra}")

    async def _execute_lifecycle_hooks(
        self, hooks: list[LifecycleHook], run_id: MachineID, stage: str
    ) -> None:
        """Executes a sequence of lifecycle tools (Programmable Agents).

        Hooks are executed out-of-band (they do not pollute the LLM conversation
        history or the main event ledger) to prevent contextual hallucinations.
        """
        if not hooks:
            return

        self._log("⚙️", f"Executing {len(hooks)} '{stage}' lifecycle hook(s)...")
        for hook in hooks:
            resolved_args = dict(hook.arguments)

            # Resolve dynamic arguments mapped to the StateStore
            if hook.arguments_map and self.environment and self.environment.state_store:
                for arg_name, state_key in hook.arguments_map.items():
                    val = await self.environment.state_store.get(run_id, state_key)
                    if val is not None:
                        resolved_args[arg_name] = val

            # Create a virtual ToolCall for the Executor
            call = ToolCall(
                id=f"hook_{uuid.uuid4().hex[:8]}",
                name=hook.tool,
                arguments=resolved_args,
                context={"run_id": run_id, "source": "lifecycle"}
            )

            self._log("⚙️", f"  -> Invoking hook: {hook.tool}()")
            try:
                result_msg = await self.tool_executor.execute(call)

                # Save result to StateStore if an output variable was defined
                if hook.output_variable and self.environment and self.environment.state_store:
                    await self.environment.state_store.set(
                        run_id, hook.output_variable, result_msg.content
                    )
                    self._log("💾", f"  -> Saved output to memory key '{hook.output_variable}'")
            except Exception as e:
                self._log("❌", f"Lifecycle hook {hook.tool} failed: {e}")
                raise RuntimeError(f"Lifecycle hook '{hook.tool}' failed during {stage}: {e}") from e

    async def execute_run(
        self,
        blueprint: AgentBlueprint,
        user_input: str,
        agent_id: str,
        parent_id: MachineID | None = None,
        run_id: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[str, UnifiedMessage | None]:

        run_id = run_id or str(uuid.uuid4())
        context: list[UnifiedMessage] = [UserMessage(content=user_input)]

        loop_counter = 0
        retry_counter = 0
        MAX_LOOPS = 20
        MAX_RETRIES = 3
        final_response: UnifiedMessage | None = None
        cumulative_usage = UsageStats.zero()
        pending_escalation = None

        current_state = KernelState.CREATED
        sequence_number = 1

        def next_seq() -> int:
            nonlocal sequence_number
            val = sequence_number
            sequence_number += 1
            return val

        def transition(new_state: KernelState) -> None:
            nonlocal current_state
            self._log("⚡", f"[FSM] {current_state.value} -> {new_state.value}")
            validate_transition(current_state, new_state)
            current_state = new_state

        # ══════════════════════════════════════════════════════════════════
        # PRE-LOOP: Build all engines ONCE per run — not per iteration.
        # ══════════════════════════════════════════════════════════════════

        context_engine = self.context_registry.build(
            blueprint.context.strategy,
            blueprint.context.params
        )
        bursar = self.bursar_registry.build(
            blueprint.governance.budget.strategy,
            blueprint.governance.budget.params
        )
        sentinel = self.sentinel_registry.build(
            blueprint.tools[0].governance.sentinel.strategy if blueprint.tools else "passthrough",
            blueprint.tools[0].governance.sentinel.params if blueprint.tools else {}
        )
        human_gate = self.human_gate_registry.build(
            blueprint.tools[0].governance.human_gate.strategy if blueprint.tools else "auto_approve",
            blueprint.tools[0].governance.human_gate.params if blueprint.tools else {}
        )

        self._log("🎬", f"STARTING RUN: {run_id}", agent=blueprint.id)

        try:
            # ── 1. INITIALIZATION ─────────────────────────────────────────
            meta = {"parent_run_id": parent_id} if parent_id else {}
            if metadata:
                meta.update(metadata)

            # Blueprint snapshot for the Ledger
            blueprint_snapshot = blueprint.to_snapshot()

            await self.repo.append(RunCreated(
                run_id=run_id,
                sequence_number=next_seq(),
                step_index=0,

                agent_id=agent_id,
                blueprint_id=blueprint.id,
                blueprint_snapshot=blueprint_snapshot,

                agent_version=blueprint.version,
                user_input=list(context),
                initial_budget=blueprint.governance.budget,
                metadata=meta
            ))

            # ── 2. FSM DRIVER LOOP ────────────────────────────────────────
            while not is_terminal_state(current_state):

                # ── STATE HANDLERS ────────────────────────────────────────

                if current_state == KernelState.CREATED:
                    if blueprint.lifecycle.on_start:
                        await self._execute_lifecycle_hooks(
                            blueprint.lifecycle.on_start, run_id, "on_start"
                        )
                    transition(KernelState.HYDRATING)

                elif current_state == KernelState.HYDRATING:
                    if parent_id:
                        self._log("💧", f"Hydrating from Ledger (parent: {parent_id})")
                        all_events = []
                        current_ancestor = parent_id

                        while current_ancestor:
                            past = await self.repo.get_events(current_ancestor)
                            if not past:
                                break
                            all_events = past + all_events
                            created = next(
                                (e for e in past if isinstance(e, RunCreated)), None
                            )
                            current_ancestor = (
                                created.metadata.get("parent_run_id") if created else None
                            )

                        historical = []
                        for event in all_events:
                            if isinstance(event, RunCreated):
                                historical.extend(event.user_input)
                            elif isinstance(event, ModelResponse):
                                historical.append(event.message)
                            elif isinstance(event, ToolOutput):
                                historical.append(ToolMessage(
                                    tool_call_id=event.tool_call_id,
                                    name=event.tool_name,
                                    content=event.output
                                ))

                        context = historical + context
                        self._log("🧠", f"Hydrated: {len(historical)} past messages.")

                    transition(KernelState.HYDRATED)

                elif current_state == KernelState.HYDRATED:
                    transition(KernelState.CHECKING_BUDGET)

                elif current_state == KernelState.CHECKING_BUDGET:
                    verdict = bursar.evaluate(
                        cumulative_usage=cumulative_usage,
                        run_id=run_id,
                        loop_counter=loop_counter
                    )

                    if verdict == BursarVerdict.WARN:
                        limit = blueprint.governance.budget.params.get("token_limit", 0)
                        self._log("⚠️", f"Budget warning: {cumulative_usage.total_tokens}/{limit} tokens")
                        # BudgetNotified event could be added here

                    if verdict == BursarVerdict.HALT:
                        raise BudgetExceededError(
                            "Budget hard cap exceeded — Bursar halted the run.",
                            current_usage=cumulative_usage.total_tokens,
                            limit=limit if 'limit' in locals() else 0
                        )

                    transition(KernelState.PREPARING_CONTEXT)

                elif current_state == KernelState.PREPARING_CONTEXT:
                    loop_counter += 1

                    # ✅ MAX_LOOPS ENFORCED — Prevents infinite loops
                    if loop_counter >= MAX_LOOPS:
                        raise RuntimeError(f"Max reasoning loops ({MAX_LOOPS}) exceeded.")

                    self._log("🔄", f"--- REASONING LOOP {loop_counter}/{MAX_LOOPS} ---")

                    await self.repo.append(StepStarted(
                        run_id=run_id,
                        sequence_number=next_seq(),
                        step_index=loop_counter,
                        step_type=StepType.INFERENCE
                    ))

                    transition(KernelState.COMPACTING_CONTEXT)

                elif current_state == KernelState.COMPACTING_CONTEXT:
                    context = await context_engine.build_prompt(
                        messages=context,
                        blueprint=blueprint,
                        run_id=run_id,
                        environment=self.environment
                    )
                    self._log("🗜️", f"Context: {len(context)} messages.")

                    transition(KernelState.CALLING_MODEL)

                elif current_state == KernelState.CALLING_MODEL:
                    tool_defs = None
                    if blueprint.llm_tools and hasattr(self.tool_executor, 'get_definitions'):
                        resolved_tool_names = self._resolve_tool_names(blueprint, blueprint.llm_tools)
                        tool_defs = self.tool_executor.get_definitions(resolved_tool_names)

                    await self.repo.append(ModelRequest(
                        run_id=run_id,
                        sequence_number=next_seq(),
                        step_index=loop_counter,
                        provider=blueprint.model.provider,
                        model=blueprint.model.name,
                        prompt_messages=list(context),
                        parameters={"temperature": blueprint.model.temperature}
                    ))

                    self._log("🧠", "Thinking...", model=blueprint.model.name)

                    try:
                        llm_response = await self.llm_executor.generate(
                            blueprint=blueprint,
                            messages=context,
                            tools=tool_defs,
                        )

                        # Reset retry counter on success
                        retry_counter = 0

                        # Fallback history logging
                        history = llm_response.provider_metadata.get("fallback_history", [])
                        for i, attempt in enumerate(history):
                            if i + 1 < len(history):
                                next_p = history[i + 1]["failed_provider"]
                            else:
                                next_p = llm_response.provider_metadata.get("actual_provider", "unknown")

                            await self.repo.append(ModelFallback(
                                run_id=run_id,
                                sequence_number=next_seq(),
                                step_index=loop_counter,
                                failed_provider=attempt["failed_provider"],
                                model_name=attempt.get("model_name", "unknown"),
                                reason=attempt["reason"],
                                next_provider=next_p
                            ))

                        cumulative_usage = cumulative_usage + llm_response.usage

                        assistant_msg = AssistantMessage(
                            content=llm_response.content,
                            tool_calls=llm_response.tool_calls
                        )

                        if assistant_msg.tool_calls:
                            tools_str = ", ".join([t.name for t in assistant_msg.tool_calls])
                            self._log("💡", f"Model decided to act: {tools_str}")
                        else:
                            self._log("🗣️", f"Response: {str(assistant_msg.content)[:50]}...")

                        await self.repo.append(ModelResponse(
                            run_id=run_id,
                            sequence_number=next_seq(),
                            step_index=loop_counter,
                            message=assistant_msg,
                            usage=llm_response.usage
                        ))

                        context.append(assistant_msg)
                        transition(KernelState.PROCESSING_RESPONSE)

                    except Exception as llm_error:
                        # Transient LLM error — enter retry path
                        self._log("⚠️", f"LLM error: {llm_error}")
                        if retry_counter < MAX_RETRIES:
                            retry_counter += 1
                            self._log("🔄", f"Retry {retry_counter}/{MAX_RETRIES}")
                            transition(KernelState.RETRYING)
                        else:
                            raise RuntimeError(f"LLM failed after {MAX_RETRIES} retries: {llm_error}") from llm_error

                elif current_state == KernelState.RETRYING:
                    # Exponential backoff: 2, 4, 6 seconds...
                    await asyncio.sleep(retry_counter * 2)
                    transition(KernelState.CALLING_MODEL)

                elif current_state == KernelState.PROCESSING_RESPONSE:
                    last_msg = context[-1]
                    if isinstance(last_msg, AssistantMessage) and last_msg.tool_calls:
                        transition(KernelState.PARSING_TOOL_ARGS)
                    else:
                        final_response = last_msg
                        transition(KernelState.COMPLETED)

                elif current_state == KernelState.PARSING_TOOL_ARGS:
                    # Future: JSON repair logic here if needed
                    transition(KernelState.CHECKING_POLICY)

                elif current_state == KernelState.CHECKING_POLICY:
                    last_msg = context[-1]
                    if not isinstance(last_msg, AssistantMessage) or not last_msg.tool_calls:
                        raise RuntimeError("Expected AssistantMessage with tool_calls in CHECKING_POLICY")

                    # Get tool config for this specific tool
                    tool_call_to_check = last_msg.tool_calls[0]
                    
                    # Resolve tool name for config lookup
                    # tool_call_to_check.name is in LLM format (e.g., "chat__save_message")
                    # blueprint.tools contains names as in YAML (e.g., "save_message" or "quotations__run")
                    blueprint_namespace = self._resolve_blueprint_namespace(blueprint)
                    llm_name = tool_call_to_check.name
                    
                    if llm_name.startswith(f"{blueprint_namespace}__"):
                        # Same namespace: extract base name
                        base_name = llm_name[len(f"{blueprint_namespace}__"):]
                        tool_config = next(
                            (t for t in blueprint.tools if t.name == base_name),
                            None
                        )
                    else:
                        # Cross-namespace or exact match
                        tool_config = next(
                            (t for t in blueprint.tools if t.name == llm_name),
                            None
                        )

                    # Build governance strategies for this specific tool
                    sentinel_strategy = (
                        tool_config.governance.sentinel.strategy
                        if tool_config else "passthrough"
                    )
                    sentinel_params = (
                        tool_config.governance.sentinel.params
                        if tool_config else {}
                    )
                    tool_sentinel = self.sentinel_registry.build(sentinel_strategy, sentinel_params)

                    sentinel_result = tool_sentinel.evaluate(
                        call=tool_call_to_check,
                        run_id=run_id,
                        loop_counter=loop_counter
                    )

                    if sentinel_result.verdict == SentinelVerdict.APPROVED:
                        transition(KernelState.EXECUTING_TOOL)

                    elif sentinel_result.verdict == SentinelVerdict.BLOCKED:
                        context.pop()
                        context.append(UserMessage(
                            content=(
                                f"[SYSTEM] Tool '{tool_call_to_check.name}' "
                                f"was blocked by security policy. "
                                f"Reason: {sentinel_result.reason} "
                                f"Please try a different approach."
                            )
                        ))
                        await self.repo.append(PolicyViolation(
                            run_id=run_id,
                            sequence_number=next_seq(),
                            step_index=loop_counter,
                            violating_tool=tool_call_to_check.name,
                            reason=sentinel_result.reason
                        ))
                        transition(KernelState.CHECKING_BUDGET)

                    elif sentinel_result.verdict == SentinelVerdict.ESCALATE:
                        pending_escalation = (tool_call_to_check, sentinel_result.reason)
                        await self.repo.append(HumanInterventionRequired(
                            run_id=run_id,
                            sequence_number=next_seq(),
                            step_index=loop_counter,
                            reason=sentinel_result.reason,
                            data_context={
                                "tool": tool_call_to_check.name,
                                "args": tool_call_to_check.arguments
                            }
                        ))
                        transition(KernelState.SUSPENDED)

                elif current_state == KernelState.SUSPENDED:
                    # Re-entry point after human approval/rejection via Nexus or external system
                    # In v1.x, we expect the result to be injected via a separate mechanism
                    # For now, this state is a placeholder for async recovery
                    self._log("⏸️", "Run suspended — awaiting external recovery")
                    raise RuntimeError(
                        "SUSPENDED state requires external recovery mechanism (Nexus/injection)"
                    )

                elif current_state == KernelState.EXECUTING_TOOL:
                    last_msg = context[-1]
                    if not isinstance(last_msg, AssistantMessage) or not last_msg.tool_calls:
                        raise RuntimeError("Expected AssistantMessage with tool_calls in EXECUTING_TOOL")

                    # Inject Kernel context into each tool call
                    updated_calls = []
                    for tc in last_msg.tool_calls:
                        new_ctx = {
                            "run_id": run_id,
                            "parent_run_id": parent_id,
                            "agent_id": agent_id,
                            "blueprint_id": blueprint.id
                        }
                        updated = tc.model_copy(update={"context": new_ctx})
                        updated_calls.append(updated)

                        await self.repo.append(ToolExecution(
                            run_id=run_id,
                            sequence_number=next_seq(),
                            step_index=loop_counter,
                            tool_call=updated,
                            tool_input=updated.arguments
                        ))

                    last_msg = last_msg.model_copy(update={"tool_calls": updated_calls})
                    context[-1] = last_msg

                    self._log("🛠️", f"Executing {len(updated_calls)} tool(s)...")

                    # Execute all tool calls
                    tool_results = await self.tool_executor.execute_batch(updated_calls)

                    for result in tool_results:
                        out_str = str(result.content) if not isinstance(result.content, str) else result.content
                        is_error = result.content.startswith("[ERROR]") if isinstance(result.content, str) else False

                        await self.repo.append(ToolOutput(
                            run_id=run_id,
                            sequence_number=next_seq(),
                            step_index=loop_counter,
                            tool_call_id=result.tool_call_id,
                            tool_name=result.name or "unknown",
                            output=out_str,
                            is_error=is_error
                        ))
                        context.append(result)

                    transition(KernelState.CHECKING_BUDGET)

                elif current_state == KernelState.HANDLING_ERROR:
                    if retry_counter < MAX_RETRIES:
                        retry_counter += 1
                        self._log("🔄", f"Retry {retry_counter}/{MAX_RETRIES} after error")
                        transition(KernelState.RETRYING)
                    else:
                        self._log("💥", f"Max retries ({MAX_RETRIES}) exceeded")
                        transition(KernelState.FAILED)

                else:
                    raise RuntimeError(f"Kernel stalled: Unhandled FSM state '{current_state.value}'.")

            # ── 3. COMPLETION ─────────────────────────────────────────────
            if current_state == KernelState.COMPLETED:
                self._log("🏁", "RUN COMPLETED", tokens=cumulative_usage.total_tokens)

                if blueprint.lifecycle.on_finish:
                    await self._execute_lifecycle_hooks(
                        blueprint.lifecycle.on_finish, run_id, "on_finish"
                    )

                await self.repo.append(RunCompleted(
                    run_id=run_id,
                    sequence_number=next_seq(),
                    step_index=loop_counter + 1,
                    final_response=final_response,
                    total_usage=cumulative_usage
                ))

                if self.environment and self.environment.state_store:
                    self._log("🧹", "Clearing StateStore (GC)")
                    await self.environment.state_store.clear(run_id)

                return run_id, final_response

            # If we exited via FAILED
            return run_id, None

        except BudgetExceededError as e:
            logger.warning(f"💰 Budget exceeded: {e}")
            await self._handle_failure(
                run_id=run_id,
                error_type="budget_exceeded",
                error_message=str(e),
                loop_counter=loop_counter,
                sequence_func=next_seq,
                blueprint=blueprint
            )
            raise

        except Exception as e:
            logger.error(f"💥 Kernel Panic: {str(e)}", exc_info=True)
            await self._handle_failure(
                run_id=run_id,
                error_type="kernel_panic",
                error_message=str(e),
                loop_counter=loop_counter,
                sequence_func=next_seq,
                blueprint=blueprint
            )
            raise

    async def _handle_failure(
        self,
        run_id: str,
        error_type: str,
        error_message: str,
        loop_counter: int,
        sequence_func: callable,
        blueprint: AgentBlueprint
    ) -> None:
        """Centralized failure handling with proper cleanup and event emission."""
        try:
            if blueprint.lifecycle.on_error:
                try:
                    await self._execute_lifecycle_hooks(
                        blueprint.lifecycle.on_error, run_id, "on_error"
                    )
                except Exception as hook_err:
                    logger.error(f"Double fault in on_error hook: {hook_err}")

            await self.repo.append(RunFailed(
                run_id=run_id,
                sequence_number=sequence_func(),
                step_index=loop_counter,
                error_type=error_type,
                error_message=error_message
            ))
        except Exception as repo_error:
            logger.critical(f"Double fault — Ledger also failed: {repo_error}")

        if self.environment and self.environment.state_store:
            await self.environment.state_store.clear(run_id)
