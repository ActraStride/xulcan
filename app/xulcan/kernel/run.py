"""Kernel Engine — The FSM Driver for Xulcan Agents.

Architecture:
    - FSM (KernelState): The static graph of valid operations.
    - Ledger (LedgerRepository): The dynamic DAG of historical events.
    - ProtoKernel: The driver that unrolls the loop.

The Kernel knows NOTHING about:
    - Which LLM provider is used (Gemini vs Ollama vs Groq).
    - How adapters are constructed (api_key vs host).
    - Which database stores the ledger.
    - How context is compacted (SlidingWindow vs FullHistory vs Summary).

It only knows the contracts: LLMProvider, LedgerRepository, ToolExecutor, ContextStrategy.
"""

from __future__ import annotations

import uuid
import logging
import json
from typing import Any

from xulcan.core.primitives import MachineID
from xulcan.core.economics import UsageStats, BudgetExceededError
from xulcan.governance.bursar.base import BursarVerdict
from xulcan.governance.sentinel.base import SentinelVerdict
from xulcan.governance.human.base import HumanGateDecision

from xulcan.kernel.states import KernelState, validate_transition, is_terminal_state
from xulcan.kernel.interfaces import (
    LedgerRepository, ToolExecutor, LLMProvider, ContextStrategy, 
    BursarStrategy, SentinelStrategy, HumanGateStrategy
)
from xulcan.registry import ProviderRegistry
from xulcan.kernel.environment import SystemEnvironment

from xulcan.blueprint.schema import AgentBlueprint

from xulcan.history.events import (
    RunCreated, StepStarted, ModelRequest, ModelResponse,
    ToolExecution, ToolOutput, RunCompleted, RunFailed, StepType,
    PolicyViolation, HumanInterventionRequired, HumanInterventionResult
)
from xulcan.protocol.message import (
    UnifiedMessage, SystemMessage, UserMessage,
    AssistantMessage, ToolMessage
)

logger = logging.getLogger("xulcan.kernel")


class ProtoKernel:
    """The FSM Driver (Engine) for Xulcan Agents.

    Receives all dependencies via constructor injection.
    Has zero knowledge of concrete adapter implementations.
    """

    def __init__(
        self,
        repository: LedgerRepository,
        llm_registry: ProviderRegistry[LLMProvider],
        tool_executor: ToolExecutor,
        context_registry: ProviderRegistry[ContextStrategy],
        bursar_registry: ProviderRegistry[BursarStrategy],
        sentinel_registry: ProviderRegistry[SentinelStrategy],
        human_gate_registry: ProviderRegistry[HumanGateStrategy],
        environment: SystemEnvironment | None = None,
    ):
        self.repo = repository
        self.registry = llm_registry
        self.tool_executor = tool_executor
        self.context_registry = context_registry
        self.bursar_registry = bursar_registry
        self.sentinel_registry = sentinel_registry
        self.human_gate_registry = human_gate_registry
        self.environment = environment

    def _log(self, emoji: str, msg: str, **kwargs: Any) -> None:
        """Internal structured logging helper."""
        extra = f" | {json.dumps(kwargs, default=str)}" if kwargs else ""
        logger.info(f"{emoji} {msg}{extra}")

    async def execute_run(
        self,
        blueprint: AgentBlueprint,
        user_input: str,
        parent_id: str | None = None
    ) -> tuple[str, UnifiedMessage | None]:
        
        run_id = str(uuid.uuid4())
        context: list[UnifiedMessage] =[UserMessage(content=user_input)]

        loop_counter = 0
        MAX_LOOPS = 20
        final_response: UnifiedMessage | None = None
        cumulative_usage = UsageStats.zero()
        pending_escalation = None  # (ToolCall, reason) — local per run, not shared

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
        #
        # llm_adapter:    the cognitive engine (Gemini, Ollama, Groq...)
        # context_engine: the attention mechanism (SlidingWindow, FullHistory...)
        #
        # ConfigSchema handles all construction differences transparently.
        # The Kernel never knows whether it's talking to Gemini or Ollama,
        # nor whether context is sliding or full.
        # ══════════════════════════════════════════════════════════════════
        llm_adapter = self.registry.build(
            blueprint.model_provider,
            blueprint.model_params
        )
        context_engine = self.context_registry.build(
            blueprint.context_strategy,
            blueprint.context_params
        )
        bursar = self.bursar_registry.build(
            blueprint.bursar_strategy,
            blueprint.bursar_params
        )
        sentinel = self.sentinel_registry.build(
            blueprint.sentinel_strategy,
            blueprint.sentinel_params
        )
        human_gate = self.human_gate_registry.build(
            blueprint.human_gate_strategy,
            blueprint.human_gate_params
        )

        self._log("🎬", f"STARTING RUN: {run_id}", agent=blueprint.id)

        try:
            # ── 1. INITIALIZATION ─────────────────────────────────────────
            meta = {"parent_run_id": parent_id} if parent_id else {}
            await self.repo.append(RunCreated(
                run_id=run_id,
                sequence_number=next_seq(),
                step_index=0,
                agent_id=blueprint.id,
                agent_version=blueprint.version,
                user_input=list(context),
                initial_budget=blueprint.budget,
                metadata=meta
            ))

            # ── 2. FSM DRIVER LOOP ────────────────────────────────────────
            while not is_terminal_state(current_state):

                # ── STATE HANDLERS ────────────────────────────────────────

                if current_state == KernelState.CREATED:
                    transition(KernelState.HYDRATING)

                elif current_state == KernelState.HYDRATING:
                    if parent_id:
                        self._log("💧", f"Hydrating from Ledger (parent: {parent_id})")
                        all_events =[]
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

                        historical =[]
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
                        budget=blueprint.budget,
                        run_id=run_id,
                        loop_counter=loop_counter
                    )

                    if verdict == BursarVerdict.HALT:
                        raise BudgetExceededError(
                            "Budget hard cap exceeded — Bursar halted the run.",
                            current_usage=cumulative_usage.total_tokens,
                            limit=blueprint.budget.token_limit or 0
                        )
                    # WARN → log already emitted by BaseBursarStrategy, continue
                    transition(KernelState.PREPARING_CONTEXT)

                elif current_state == KernelState.PREPARING_CONTEXT:
                    # The loop counter and StepStarted event live here —
                    # this is the logical start of each reasoning cycle.
                    loop_counter += 1
                    self._log("🔄", f"--- REASONING LOOP {loop_counter} ---")

                    await self.repo.append(StepStarted(
                        run_id=run_id,
                        sequence_number=next_seq(),
                        step_index=loop_counter,
                        step_type=StepType.INFERENCE
                    ))

                    transition(KernelState.COMPACTING_CONTEXT)

                elif current_state == KernelState.COMPACTING_CONTEXT:
                    # The context_engine handles three things transparently:
                    #   1. Strips stale SystemMessages from history
                    #   2. Applies the attention strategy (sliding, full, summary...)
                    #   3. Renders system_prompt with Jinja2 + StateStore memory
                    #      and prepends it as the fresh index-0 SystemMessage
                    context = await context_engine.build_prompt(
                        messages=context,
                        blueprint=blueprint,
                        run_id=run_id,
                        environment=self.environment
                    )
                    self._log("🗜️", f"Context compacted: {len(context)} messages.")

                    transition(KernelState.CALLING_MODEL)

                elif current_state == KernelState.CALLING_MODEL:
                    # At this point context is clean, compacted, and has the
                    # rendered SystemMessage at index 0. Just call the LLM.
                    self._log("🔍", f"Context final ({len(context)} msgs):")
                    for i, m in enumerate(context):
                        role = type(m).__name__
                        has_tools = bool(getattr(m, 'tool_calls', None))
                        is_tool = hasattr(m, 'tool_call_id')
                        self._log("🔍", f"  [{i}] {role} | tool_calls={has_tools} | is_tool_result={is_tool}")
                        
                    tool_defs = None
                    if blueprint.llm_tools and hasattr(self.tool_executor, 'get_definitions'):
                        tool_defs = self.tool_executor.get_definitions(blueprint.llm_tools)

                    await self.repo.append(ModelRequest(
                        run_id=run_id,
                        sequence_number=next_seq(),
                        step_index=loop_counter,
                        provider=blueprint.model_provider,
                        model=blueprint.model_name or "unknown",
                        prompt_messages=list(context),
                        parameters={"temperature": blueprint.temperature}
                    ))

                    self._log("🧠", "Thinking...", model=blueprint.model_name)

                    llm_response = await llm_adapter.generate(
                        messages=context,
                        tools=tool_defs,
                    )

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
                        # latency_ms removed here to match the events.py refactor
                    ))
                    
                    context.append(assistant_msg)
                    transition(KernelState.PROCESSING_RESPONSE)

                elif current_state == KernelState.PROCESSING_RESPONSE:
                    last_msg = context[-1]
                    if isinstance(last_msg, AssistantMessage) and last_msg.tool_calls:
                        transition(KernelState.PARSING_TOOL_ARGS)
                    else:
                        final_response = last_msg
                        transition(KernelState.COMPLETED)

                elif current_state == KernelState.PARSING_TOOL_ARGS:
                    # TODO: JSON repair logic
                    transition(KernelState.CHECKING_POLICY)

                elif current_state == KernelState.CHECKING_POLICY:
                    last_msg = context[-1]
                    tool_call_to_check = last_msg.tool_calls[0]

                    sentinel_result = sentinel.evaluate(
                        call=tool_call_to_check,
                        run_id=run_id,
                        loop_counter=loop_counter
                    )

                    if sentinel_result.verdict == SentinelVerdict.APPROVED:
                        transition(KernelState.EXECUTING_TOOL)

                    elif sentinel_result.verdict == SentinelVerdict.BLOCKED:
                        # Remove the AssistantMessage that tried the blocked tool —
                        # it's a failed attempt and should not pollute the history.
                        context.pop()

                        # Inject a clean UserMessage so the model understands
                        # what happened and can try a different approach.
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
                        transition(KernelState.AWAITING_HUMAN)

                elif current_state == KernelState.AWAITING_HUMAN:
                    pending_call, escalation_reason = pending_escalation
                    pending_escalation = None

                    gate_result = await human_gate.request_approval(
                        call=pending_call,
                        reason=escalation_reason,
                        run_id=run_id,
                    )

                    await self.repo.append(HumanInterventionResult(
                        run_id=run_id,
                        sequence_number=next_seq(),
                        step_index=loop_counter,
                        approved=gate_result.decision == HumanGateDecision.APPROVED,
                        feedback=gate_result.feedback or None
                    ))

                    if gate_result.decision == HumanGateDecision.APPROVED:
                        self._log("✅", f"Human approved: {pending_call.name}()")
                        transition(KernelState.EXECUTING_TOOL)
                    else:
                        # Remove the AssistantMessage that triggered the escalation
                        context.pop()

                        # Inject clean feedback so the model can try again
                        context.append(UserMessage(
                            content=(
                                f"[SYSTEM] Tool '{pending_call.name}' "
                                f"was rejected by the human operator. "
                                f"Feedback: {gate_result.feedback} "
                                f"Please try a different approach."
                            )
                        ))
                        self._log("❌", f"Human rejected: {pending_call.name}()")
                        transition(KernelState.CHECKING_BUDGET)

                elif current_state == KernelState.EXECUTING_TOOL:
                    last_msg = context[-1]

                    if loop_counter >= MAX_LOOPS:
                        raise RuntimeError(f"Max reasoning loops ({MAX_LOOPS}) exceeded.")

                    # Inject Kernel context into each tool call (immutably)
                    updated_calls =[]
                    for tc in last_msg.tool_calls:
                        new_ctx = {"run_id": run_id, "parent_run_id": parent_id}
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

                    self._log("🛠️", "Delegating to Tool Executor...")
                    tool_results = await self.tool_executor.execute_batch(last_msg.tool_calls)

                    for result in tool_results:
                        await self.repo.append(ToolOutput(
                            run_id=run_id,
                            sequence_number=next_seq(),
                            step_index=loop_counter,
                            tool_call_id=result.tool_call_id,
                            tool_name=result.name or "unknown",
                            output=result.content
                        ))
                        context.append(result)

                    transition(KernelState.CHECKING_BUDGET)

                elif current_state == KernelState.HANDLING_ERROR:
                    # TODO: Implement retry/recovery logic (governance/error_handler)
                    transition(KernelState.FAILED)

                else:
                    raise RuntimeError(
                        f"Kernel stalled: Unhandled FSM state {current_state.value}."
                    )

            # ── 3. COMPLETION ─────────────────────────────────────────────
            if current_state == KernelState.COMPLETED:
                self._log("🏁", "RUN COMPLETED", tokens=cumulative_usage.total_tokens)
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
            
            # If we exited the loop via FAILED, return None for the message
            return run_id, None

        except Exception as e:
            logger.error(f"💥 Kernel Panic: {str(e)}", exc_info=True)
            transition(KernelState.FAILED)

            try:
                await self.repo.append(RunFailed(
                    run_id=run_id,
                    sequence_number=next_seq(),
                    step_index=loop_counter,
                    error_type="kernel_panic",
                    error_message=str(e)
                ))
            except Exception as repo_error:
                logger.critical(f"Double fault — Ledger also failed: {repo_error}")

            if self.environment and self.environment.state_store:
                await self.environment.state_store.clear(run_id)

            # Re-raise the exception so the caller (API endpoint, CLI) knows the run failed violently
            raise