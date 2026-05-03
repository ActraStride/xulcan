#!/usr/bin/env python3
"""
Xulcan Agent Debugger
─────────────────────
Uso:  python debugger.py agents/mi_agente.yml
      python debugger.py agents/mi_agente.yml --session mi-sesion

Muestra en tiempo real:
  · Transiciones del FSM (KernelState)
  · Stream de eventos del Ledger
  · Contabilidad económica acumulada (tokens / loops / latencia)
  · Contenido del StateStore al finalizar cada turno
"""

import os
import re
import sys
import uuid
import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog, Static, Label, Rule
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from rich.text import Text

from xulcan import Xulcan


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES DE ESTILO
# ═══════════════════════════════════════════════════════════════════════════

# Colores por categoría de KernelState
STATE_COLORS = {
    # Inicialización
    "IDLE":                "#4A4A6A",
    "CREATED":             "#6B3FA0",
    # Hidratación
    "HYDRATING":           "#8B5FD0",
    "HYDRATED":            "#9D6FE8",
    # Governance
    "CHECKING_BUDGET":     "#FFB830",
    "CHECKING_POLICY":     "#FF8C00",
    # Contexto
    "PREPARING_CONTEXT":   "#00BFFF",
    "COMPACTING_CONTEXT":  "#0090CC",
    # LLM
    "CALLING_MODEL":       "#BF00FF",
    "PROCESSING_RESPONSE": "#9400D3",
    # Herramientas
    "PARSING_TOOL_ARGS":   "#00CED1",
    "EXECUTING_TOOL":      "#00FFCC",
    # Human-in-the-loop
    "AWAITING_HUMAN":      "#FF69B4",
    # Error
    "HANDLING_ERROR":      "#FF4500",
    # Terminal
    "COMPLETED":           "#00FF87",
    "FAILED":              "#FF2D6B",
}

# Colores por tipo de evento
EVENT_COLORS = {
    "run_created":                  "#6B3FA0",
    "run_completed":                "#00FF87",
    "run_failed":                   "#FF2D6B",
    "step_started":                 "#4A4A6A",
    "model_request":                "#8B5FD0",
    "model_response":               "#BF00FF",
    "tool_execution":               "#00CED1",
    "tool_output":                  "#00FFCC",
    "policy_violation":             "#FF4500",
    "human_intervention_required":  "#FF69B4",
    "human_intervention_result":    "#FFB830",
}

EVENT_ICONS = {
    "run_created":                  "🚀",
    "run_completed":                "✅",
    "run_failed":                   "💥",
    "step_started":                 "🔄",
    "model_request":                "📤",
    "model_response":               "📥",
    "tool_execution":               "⚙️ ",
    "tool_output":                  "📦",
    "policy_violation":             "🚫",
    "human_intervention_required":  "🙋",
    "human_intervention_result":    "✋",
}

FSM_GRAPH = {
    "IDLE":                ["CREATED"],
    "CREATED":             ["HYDRATING"],
    "HYDRATING":           ["HYDRATED"],
    "HYDRATED":            ["CHECKING_BUDGET"],
    "CHECKING_BUDGET":     ["PREPARING_CONTEXT"],
    "PREPARING_CONTEXT":   ["COMPACTING_CONTEXT"],
    "COMPACTING_CONTEXT":  ["CALLING_MODEL"],
    "CALLING_MODEL":       ["PROCESSING_RESPONSE"],
    "PROCESSING_RESPONSE": ["COMPLETED", "PARSING_TOOL_ARGS"],
    "PARSING_TOOL_ARGS":   ["CHECKING_POLICY"],
    "CHECKING_POLICY":     ["EXECUTING_TOOL", "AWAITING_HUMAN", "CHECKING_BUDGET"],
    "AWAITING_HUMAN":      ["EXECUTING_TOOL", "CHECKING_BUDGET"],
    "EXECUTING_TOOL":      ["CHECKING_BUDGET"],
    "HANDLING_ERROR":      ["CHECKING_BUDGET", "FAILED"],
    "COMPLETED":           [],
    "FAILED":              [],
}

SEPARATOR = "─" * 36


# ═══════════════════════════════════════════════════════════════════════════
# LOG INTERCEPTOR — fuente de todos los datos en tiempo real
# ═══════════════════════════════════════════════════════════════════════════

class DebugLogInterceptor(logging.Handler):
    """
    Parsea los logs del Kernel en tiempo real y despacha callbacks
    a los paneles del debugger.
    """
    # Patterns extraídos de runtime.py y base_ledger.py
    _FSM_RE    = re.compile(r'\[FSM\]\s+(\w+)\s+->\s+(\w+)')
    _EVENT_RE  = re.compile(r'Guardando evento\s+([\w_]+)\s+\[Seq:\s*(\d+)\]')
    _STORE_RE  = re.compile(r'StateStore\[([^\]]+)\]:\s+Setting key \'([^\']+)\'')
    _CLEAR_RE  = re.compile(r'StateStore\[([^\]]+)\]:\s+Clearing')

    def __init__(self, app: "XulcanDebugger"):
        super().__init__()
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        # El Kernel corre como coroutine en el mismo event loop de Textual.
        # Los logs se emiten desde el thread principal — call_from_thread
        # solo sirve para threads secundarios, aquí usamos llamadas directas.
        msg = record.getMessage()

        # 1. Transición de FSM
        m = self._FSM_RE.search(msg)
        if m:
            self._app.on_fsm_transition(m.group(1), m.group(2))
            return

        # 2. Evento del Ledger
        m = self._EVENT_RE.search(msg)
        if m:
            self._app.on_ledger_event(m.group(1), int(m.group(2)))
            return

        # 3. Escritura en StateStore
        m = self._STORE_RE.search(msg)
        if m:
            self._app.on_store_set(m.group(1), m.group(2))
            return

        # 4. GC del StateStore al terminar el run
        m = self._CLEAR_RE.search(msg)
        if m:
            self._app.on_store_clear(m.group(1))
            return

        # 5. Todo lo demás → panel raw de logs
        level = record.levelname
        if "ERROR" in level or "CRITICAL" in level:
            color = "#FF2D6B"
            prefix = "✖"
        elif "WARNING" in level:
            color = "#FFB830"
            prefix = "⚡"
        else:
            color = "#4A4A6A"
            prefix = "·"

        self._app.on_raw_log(f"[{color}]{prefix} {msg}[/]")


# ═══════════════════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════════════════

CSS = """
Screen {
    background: #08000F;
    color: #E0D0FF;
}
Header {
    background: #0D0018;
    color: #BF00FF;
    border-bottom: solid #2A0050;
}
Footer {
    background: #0D0018;
    color: #4A3A6A;
    border-top: solid #2A0050;
}

/* ── Layout ───────────────────────────────────── */
#root {
    height: 1fr;
}

/* ── Panel Chat (izquierda) ───────────────────── */
#chat-col {
    width: 1fr;
    border-right: solid #2A0050;
}
#chat-header {
    height: 1;
    background: #100020;
    color: #BF00FF;
    padding: 0 2;
    border-bottom: solid #2A0050;
}
#chat-log {
    background: #08000F;
    padding: 1 2;
    scrollbar-color: #2A0050;
    scrollbar-color-hover: #4A0090;
}
#input-area {
    height: 3;
    background: #0D0018;
    border-top: solid #2A0050;
    padding: 0 1;
}
Input {
    background: #120025;
    color: #E0D0FF;
    border: solid #2A0050;
}
Input:focus {
    border: solid #BF00FF;
    background: #180030;
}
Input.-disabled {
    color: #2A0050;
    border: solid #180030;
}

/* ── Panel Derecho ────────────────────────────── */
#right-col {
    width: 42;
    background: #06000D;
}

/* ── FSM Panel ────────────────────────────────── */
#fsm-panel {
    height: auto;
    border-bottom: solid #2A0050;
    padding: 0 1;
}
#fsm-header {
    height: 1;
    background: #0D0018;
    color: #FF00FF;
    padding: 0 1;
    border-bottom: solid #2A0050;
}
#fsm-state {
    height: 3;
    padding: 1 2;
    background: #06000D;
    color: #BF00FF;
}
#fsm-trail {
    height: 3;
    background: #06000D;
    color: #4A3A6A;
    padding: 0 2;
}

/* ── Economics Panel ──────────────────────────── */
#econ-panel {
    height: 8;
    border-bottom: solid #2A0050;
    padding: 0 1;
}
#econ-header {
    height: 1;
    background: #0D0018;
    color: #FFB830;
    padding: 0 1;
    border-bottom: solid #2A0050;
}
#econ-body {
    background: #06000D;
    padding: 0 2;
}

/* ── Events Panel ─────────────────────────────── */
#events-panel {
    height: 1fr;
    border-bottom: solid #2A0050;
}
#events-header {
    height: 1;
    background: #0D0018;
    color: #00FFCC;
    padding: 0 1;
    border-bottom: solid #2A0050;
}
#events-log {
    background: #06000D;
    padding: 0 1;
    scrollbar-color: #2A0050;
}

/* ── StateStore Panel ─────────────────────────── */
#store-panel {
    height: 8;
}
#store-header {
    height: 1;
    background: #0D0018;
    color: #00CED1;
    padding: 0 1;
    border-bottom: solid #2A0050;
}
#store-log {
    background: #06000D;
    padding: 0 1;
}
"""


# ═══════════════════════════════════════════════════════════════════════════
# WIDGETS REACTIVOS
# ═══════════════════════════════════════════════════════════════════════════

class FSMStateWidget(Static):
    current: reactive[str] = reactive("IDLE")
    trail:   reactive[list] = reactive([])

    def render(self) -> Text:
        color = STATE_COLORS.get(self.current, "#FFFFFF")
        return Text.from_markup(
            f"  [bold {color}]● {self.current}[/]"
        )


class FSMTrailWidget(Static):
    trail: reactive[list] = reactive([])

    def render(self) -> Text:
        if not self.trail:
            return Text.from_markup("[#2A0050]  sin transiciones aún[/]")
        parts = []
        for i, s in enumerate(self.trail[-6:]):  # últimas 6
            color = STATE_COLORS.get(s, "#4A4A6A")
            parts.append(f"[{color}]{s}[/]")
        return Text.from_markup("  " + " [#2A0050]→[/] ".join(parts))


class EconomicsWidget(Static):
    tokens:  reactive[int]   = reactive(0)
    budget:  reactive[int]   = reactive(0)      # 0 = sin límite
    latency: reactive[float] = reactive(0.0)
    loops:   reactive[int]   = reactive(0)

    def render(self) -> Text:
        token_color = "#00FF87"
        if self.budget > 0:
            pct = self.tokens / self.budget
            if pct > 0.9:   token_color = "#FF2D6B"
            elif pct > 0.7: token_color = "#FFB830"

        budget_str = f"/ {self.budget:,}" if self.budget > 0 else "/ ∞"
        loop_color = "#FF2D6B" if self.loops >= 18 else "#00FF87"

        return Text.from_markup(
            f"  [#4A3A6A]tokens  [/][bold {token_color}]{self.tokens:,}[/]"
            f" [#2A0050]{budget_str}[/]\n"
            f"  [#4A3A6A]latency [/][bold #9D6FE8]{self.latency:,.0f} ms[/]\n"
            f"  [#4A3A6A]loops   [/][bold {loop_color}]{self.loops}[/]"
            f" [#2A0050]/ 20[/]"
        )


# ═══════════════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════════════

class XulcanDebugger(App):
    CSS      = CSS
    BINDINGS = [
        ("ctrl+c", "quit",         "Salir"),
        ("ctrl+l", "clear_chat",   "Limpiar chat"),
        ("ctrl+e", "clear_events", "Limpiar eventos"),
        ("ctrl+r", "new_session",  "Nueva sesión"),
    ]

    def __init__(self, yml_path: str, session_key: Optional[str] = None):
        super().__init__()
        self._yml_path    = yml_path
        self._session_key = session_key or f"debug-{uuid.uuid4().hex[:12]}"
        self._run_count   = 0
        self._total_tokens  = 0
        self._total_latency = 0.0
        self._loop_count    = 0
        self._store_keys: dict = {}   # run_id → set of keys written

        # Inicializar Xulcan
        self.engine = Xulcan(
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            groq_api_key=os.getenv("GROQ_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )

        # Cargar agente
        self.blueprint = self.engine.load_agent(yml_path)
        self.TITLE = f"⬡ XULCAN DEBUGGER  ·  {self.blueprint.name}"
        self.SUB_TITLE = f"{self.blueprint.model_provider} / {self.blueprint.model_name or '?'}  ·  {yml_path}"

    # ── Composición ─────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="root"):

            # ── Columna izquierda: Chat ──────────────────────────────────
            with Vertical(id="chat-col"):
                yield Label(
                    f"  💬 CHAT  ·  sesión: {self._session_key}",
                    id="chat-header"
                )
                with VerticalScroll():
                    yield RichLog(id="chat-log", markup=True, highlight=True)
                with Vertical(id="input-area"):
                    yield Input(
                        placeholder="Escribe tu mensaje y presiona Enter…",
                        id="prompt-input"
                    )

            # ── Columna derecha: Debug panels ────────────────────────────
            with Vertical(id="right-col"):

                # FSM
                with Vertical(id="fsm-panel"):
                    yield Label("  ⚡ FSM STATE", id="fsm-header")
                    yield FSMStateWidget(id="fsm-state")
                    yield FSMTrailWidget(id="fsm-trail")

                # Economics
                with Vertical(id="econ-panel"):
                    yield Label("  💰 ECONOMICS", id="econ-header")
                    yield EconomicsWidget(id="econ-body")

                # Event stream
                with Vertical(id="events-panel"):
                    yield Label("  📋 EVENT STREAM", id="events-header")
                    yield RichLog(id="events-log", markup=True, highlight=True)

                # StateStore
                with Vertical(id="store-panel"):
                    yield Label("  🗄  STATESTORE", id="store-header")
                    yield RichLog(id="store-log", markup=True, highlight=True)

        yield Footer()

    # ── Montaje ─────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        chat   = self.query_one("#chat-log", RichLog)
        events = self.query_one("#events-log", RichLog)
        store  = self.query_one("#store-log", RichLog)
        econ   = self.query_one("#econ-body", EconomicsWidget)

        # Configurar budget display
        if self.blueprint.budget and self.blueprint.budget.token_limit:
            econ.budget = self.blueprint.budget.token_limit

        # Redirigir todos los logs de xulcan al interceptor
        logging.basicConfig(level=logging.DEBUG)
        root_logger = logging.getLogger("xulcan")
        root_logger.setLevel(logging.DEBUG)
        root_logger.handlers = []
        root_logger.addHandler(DebugLogInterceptor(self))
        root_logger.propagate = False

        # Bienvenida en el chat
        chat.write(Text.from_markup(
            f"[bold #BF00FF]⬡ XULCAN DEBUGGER[/]\n"
            f"[#4A3A6A]agente    [/][#E0D0FF]{self.blueprint.name}[/] "
            f"[#4A3A6A]({self.blueprint.id} v{self.blueprint.version})[/]\n"
            f"[#4A3A6A]modelo    [/][#E0D0FF]{self.blueprint.model_provider} / {self.blueprint.model_name or '?'}[/]\n"
            f"[#4A3A6A]sesión    [/][#BF00FF]{self._session_key}[/]\n"
            f"[#4A3A6A]bursar    [/][#E0D0FF]{self.blueprint.bursar_strategy}[/]   "
            f"[#4A3A6A]sentinel  [/][#E0D0FF]{self.blueprint.sentinel_strategy}[/]\n"
            f"[#4A3A6A]contexto  [/][#E0D0FF]{self.blueprint.context_strategy}[/]   "
            f"[#4A3A6A]tools     [/][#E0D0FF]{', '.join(self.blueprint.llm_tools) or 'ninguna'}[/]\n"
            f"[#2A0050]{'─' * 50}[/]\n"
        ))

        # Bienvenida en el panel de eventos
        events.write(Text.from_markup(
            f"[#4A3A6A]esperando primer run…[/]"
        ))

        store.write(Text.from_markup("[#4A3A6A](vacío)[/]"))

        self.query_one("#prompt-input", Input).focus()

    # ── Callbacks del interceptor ────────────────────────────────────────────

    def on_fsm_transition(self, from_state: str, to_state: str) -> None:
        """Actualiza el FSM tracker con la nueva transición."""
        state_widget = self.query_one("#fsm-state", FSMStateWidget)
        trail_widget = self.query_one("#fsm-trail", FSMTrailWidget)

        state_widget.current = to_state

        new_trail = list(trail_widget.trail) + [to_state]
        trail_widget.trail = new_trail[-8:]  # últimas 8 transiciones

        # Contar loops: cada PREPARING_CONTEXT es un nuevo ciclo
        if to_state == "PREPARING_CONTEXT":
            econ = self.query_one("#econ-body", EconomicsWidget)
            self._loop_count += 1
            econ.loops = self._loop_count

    def on_ledger_event(self, event_type: str, seq: int) -> None:
        """Añade el evento al panel de stream."""
        events = self.query_one("#events-log", RichLog)
        color  = EVENT_COLORS.get(event_type, "#9D6FE8")
        icon   = EVENT_ICONS.get(event_type, "·")
        ts     = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        events.write(Text.from_markup(
            f"[#2A0050]{seq:>3}[/] [#4A3A6A]{ts}[/] "
            f"{icon} [{color}]{event_type}[/]"
        ))

        # Actualizar economics si es model_response (buscamos en el log)
        # La latencia y tokens los capturamos del log raw del Bursar
        if event_type in ("run_completed", "run_failed"):
            fsm = self.query_one("#fsm-state", FSMStateWidget)
            fsm.current = "COMPLETED" if event_type == "run_completed" else "FAILED"

    def on_store_set(self, run_id: str, key: str) -> None:
        """Registra una escritura en el StateStore."""
        store_log = self.query_one("#store-log", RichLog)
        ts = datetime.now().strftime("%H:%M:%S")
        store_log.write(Text.from_markup(
            f"[#4A3A6A]{ts}[/] [#00CED1]SET[/] [#E0D0FF]{key}[/]"
        ))

    def on_store_clear(self, run_id: str) -> None:
        """GC: el Kernel limpió el StateStore al terminar el run."""
        store_log = self.query_one("#store-log", RichLog)
        store_log.write(Text.from_markup(
            f"[#4A3A6A]────[/] [#FF4500]GC clear()[/] [#4A3A6A]{run_id[:16]}…[/]"
        ))

    def on_raw_log(self, markup: str) -> None:
        """Log genérico que no matcheó ningún pattern específico."""
        # Parseamos tokens y latencia del log del Bursar
        # "· tokens: 1,247, latency: 2,341ms"
        token_match   = re.search(r'tokens:\s*([\d,]+)', markup)
        latency_match = re.search(r'latency:\s*([\d,.]+)\s*ms', markup)

        econ = self.query_one("#econ-body", EconomicsWidget)
        if token_match:
            try:
                econ.tokens = int(token_match.group(1).replace(",", ""))
                self._total_tokens = econ.tokens
            except ValueError:
                pass
        if latency_match:
            try:
                econ.latency = float(latency_match.group(1).replace(",", ""))
            except ValueError:
                pass

    # ── Input del usuario ────────────────────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        if not user_text:
            return

        inp   = self.query_one("#prompt-input", Input)
        chat  = self.query_one("#chat-log", RichLog)
        fsm   = self.query_one("#fsm-state", FSMStateWidget)
        trail = self.query_one("#fsm-trail", FSMTrailWidget)
        econ  = self.query_one("#econ-body", EconomicsWidget)

        inp.value    = ""
        inp.disabled = True

        # Resetear trail visual del FSM para el nuevo run
        trail.trail = []
        self._loop_count = 0
        econ.loops   = 0
        fsm.current  = "CREATED"

        ts = datetime.now().strftime("%H:%M:%S")
        chat.write(Text.from_markup(
            f"[#2A0050]┌── [/][bold #9D6FE8]TÚ[/] [#4A3A6A]{ts}[/]\n"
            f"[#2A0050]│[/]  {user_text}\n"
            f"[#2A0050]└──[/]\n"
        ))

        try:
            t0 = time.monotonic()

            respuesta: str = await self.engine.run(
                prompt=user_text,
                blueprint=self.blueprint,
                session_key=self._session_key,
            )

            elapsed = time.monotonic() - t0
            self._run_count += 1
            econ.latency = elapsed * 1000

            ts2 = datetime.now().strftime("%H:%M:%S")
            chat.write(Text.from_markup(
                f"[#2A0050]┌── [/][bold #BF00FF]✦ {self.blueprint.name}[/] "
                f"[#4A3A6A]{ts2} · {elapsed:.2f}s[/]\n"
            ))
            for line in respuesta.split("\n"):
                chat.write(Text.from_markup(
                    f"[#2A0050]│[/]  [#E0D0FF]{line}[/]"
                ))
            chat.write(Text.from_markup(
                f"[#2A0050]└── [/][#4A3A6A]run #{self._run_count}[/]\n"
            ))

            # Mostrar resumen del run en events panel
            events = self.query_one("#events-log", RichLog)
            events.write(Text.from_markup(
                f"[#2A0050]─── [/][#00FF87]run completado[/] "
                f"[#4A3A6A]{elapsed:.2f}s  tokens≈{econ.tokens:,}[/]"
            ))

        except Exception as e:
            fsm.current = "FAILED"
            chat.write(Text.from_markup(
                f"[bold #FF2D6B]✖  {type(e).__name__}: {e}[/]\n"
            ))

        finally:
            inp.disabled = False
            inp.focus()

    # ── Acciones ─────────────────────────────────────────────────────────────

    def action_clear_chat(self) -> None:
        self.query_one("#chat-log", RichLog).clear()

    def action_clear_events(self) -> None:
        self.query_one("#events-log", RichLog).clear()
        self.query_one("#store-log", RichLog).clear()
        self.query_one("#store-log", RichLog).write(
            Text.from_markup("[#4A3A6A](vacío)[/]")
        )

    def action_new_session(self) -> None:
        """Ctrl+R: nueva session_key manteniendo el mismo agente."""
        self._session_key = f"debug-{uuid.uuid4().hex[:12]}"
        self._run_count   = 0
        self._total_tokens  = 0
        self._total_latency = 0.0
        self._loop_count    = 0

        econ = self.query_one("#econ-body", EconomicsWidget)
        econ.tokens  = 0
        econ.latency = 0.0
        econ.loops   = 0

        fsm = self.query_one("#fsm-state", FSMStateWidget)
        fsm.current = "IDLE"
        self.query_one("#fsm-trail", FSMTrailWidget).trail = []

        self.query_one("#chat-log", RichLog).write(Text.from_markup(
            f"\n[#2A0050]{'─' * 50}[/]\n"
            f"[bold #BF00FF]⬡ NUEVA SESIÓN[/] [#BF00FF]{self._session_key}[/]\n"
            f"[#2A0050]{'─' * 50}[/]\n"
        ))
        self.query_one("#events-log", RichLog).clear()
        self.query_one("#store-log", RichLog).clear()
        self.query_one("#store-log", RichLog).write(
            Text.from_markup("[#4A3A6A](vacío)[/]")
        )
        self.query_one("#prompt-input", Input).focus()


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Xulcan Agent Debugger — TUI para depuración de agentes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python debugger.py agents/tech_lead.yml
  python debugger.py agents/dev.yml --session mi-sesion-de-prueba

Variables de entorno requeridas según proveedor:
  GEMINI_API_KEY     → model_provider: google
  GROQ_API_KEY       → model_provider: groq
  ANTHROPIC_API_KEY  → model_provider: anthropic
  OLLAMA_HOST        → model_provider: ollama  (default: http://localhost:11434)

Atajos de teclado:
  Ctrl+L  Limpiar chat
  Ctrl+E  Limpiar panel de eventos
  Ctrl+R  Nueva sesión (mismo agente, historial limpio)
  Ctrl+C  Salir
        """
    )
    parser.add_argument("yml", help="Ruta al manifiesto YAML del agente")
    parser.add_argument(
        "--session", "-s",
        default=None,
        help="Clave de sesión personalizada (default: debug-<uuid>)"
    )
    args = parser.parse_args()

    if not os.path.exists(args.yml):
        print(f"✖  No se encontró el archivo: {args.yml}", file=sys.stderr)
        sys.exit(1)

    app = XulcanDebugger(yml_path=args.yml, session_key=args.session)
    app.run()


if __name__ == "__main__":
    main()