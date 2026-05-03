import os
import sys
import uuid
import logging
import time
from datetime import datetime

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Input, RichLog, DirectoryTree, Static, Label
)
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual import work
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from rich.console import Console
from rich.style import Style

from xulcan import Xulcan

# ═══════════════════════════════════════════════════════════════════════════
# INTERCEPTOR DE LOGS
# ═══════════════════════════════════════════════════════════════════════════

class TextualLogHandler(logging.Handler):
    """Redirige el logger de xulcan al panel de telemetría."""
    def __init__(self, log_widget: RichLog):
        super().__init__()
        self.log_widget = log_widget
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname

            if "ERROR" in level or "CRITICAL" in level:
                self.log_widget.write(Text.from_markup(f"[bold #FF2D6B]✖ {msg}[/]"))
            elif "WARNING" in level:
                self.log_widget.write(Text.from_markup(f"[bold #FFB830]⚡ {msg}[/]"))
            elif "tool" in msg.lower() or "herramienta" in msg.lower():
                self.log_widget.write(Text.from_markup(f"[bold #00FFCC]⚙  {msg}[/]"))
            elif "llm" in msg.lower() or "model" in msg.lower() or "gemini" in msg.lower() or "groq" in msg.lower():
                self.log_widget.write(Text.from_markup(f"[bold #BF00FF]◈  {msg}[/]"))
            else:
                self.log_widget.write(Text.from_markup(f"[#9D6FE8]·  {msg}[/]"))
        except Exception as e:
            self.log_widget.write(f"[LOG ERROR]: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════
# WIDGETS PERSONALIZADOS
# ═══════════════════════════════════════════════════════════════════════════

LOGO = """[bold #BF00FF]
 ██╗  ██╗██╗   ██╗██╗      ██████╗ █████╗ ███╗  ██╗
 ╚██╗██╔╝██║   ██║██║     ██╔════╝██╔══██╗████╗ ██║
  ╚███╔╝ ██║   ██║██║     ██║     ███████║██╔██╗██║
  ██╔██╗ ██║   ██║██║     ██║     ██╔══██║██║╚████║
 ██╔╝╚██╗╚██████╔╝███████╗╚██████╗██║  ██║██║ ╚███║
 ╚═╝  ╚═╝ ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚══╝[/]
[#6B3FA0] Agent OS  ·  Orquestación Determinista  ·  v1.0[/]"""

SEPARATOR = "[#3D1F6B]" + "─" * 60 + "[/]"


class LogoWidget(Static):
    def render(self):
        return Text.from_markup(LOGO)


class StatusBar(Static):
    agent_name: reactive[str] = reactive("Sin agente")
    run_count:  reactive[int] = reactive(0)
    status:     reactive[str] = reactive("IDLE")

    def render(self):
        now = datetime.now().strftime("%H:%M:%S")
        status_color = {
            "IDLE":      "#6B3FA0",
            "RUNNING":   "#BF00FF",
            "THINKING":  "#FF00FF",
            "ERROR":     "#FF2D6B",
            "READY":     "#00FFCC",
        }.get(self.status, "#6B3FA0")

        return Text.from_markup(
            f"[#3D1F6B]│[/] "
            f"[#9D6FE8]AGENTE[/] [bold #E8D5FF]{self.agent_name}[/]   "
            f"[#9D6FE8]RUNS[/] [bold #E8D5FF]{self.run_count}[/]   "
            f"[#9D6FE8]ESTADO[/] [bold {status_color}]{self.status}[/]   "
            f"[#9D6FE8]HORA[/] [bold #6B3FA0]{now}[/]"
        )


# ═══════════════════════════════════════════════════════════════════════════
# CSS  —  CYBERPUNK NEON PURPLE
# ═══════════════════════════════════════════════════════════════════════════

CSS = """
/* ── Base ─────────────────────────────────────── */
Screen {
    background: #050008;
    color: #E8D5FF;
}

/* ── Header ───────────────────────────────────── */
Header {
    background: #0A000F;
    color: #BF00FF;
    text-style: bold;
    border-bottom: solid #3D1F6B;
}

/* ── Footer ───────────────────────────────────── */
Footer {
    background: #0A000F;
    color: #6B3FA0;
    border-top: solid #3D1F6B;
}

/* ── Layout principal ─────────────────────────── */
#main-layout {
    height: 1fr;
}

/* ── Columna 1: Árbol de archivos ─────────────── */
#tree-panel {
    width: 22;
    background: #070010;
    border-right: solid #3D1F6B;
    padding: 0 1;
}

#tree-label {
    background: #0D0020;
    color: #BF00FF;
    text-style: bold;
    padding: 0 1;
    border-bottom: solid #3D1F6B;
}

DirectoryTree {
    background: #070010;
    color: #9D6FE8;
    scrollbar-color: #3D1F6B;
    scrollbar-color-hover: #6B3FA0;
    scrollbar-color-active: #BF00FF;
}

DirectoryTree > .tree--cursor {
    background: #1A0035;
    color: #FF00FF;
    text-style: bold;
}

DirectoryTree > .tree--highlight {
    background: #120025;
}

/* ── Columna 2: Chat ──────────────────────────── */
#chat-panel {
    width: 1fr;
    background: #050008;
    border-right: solid #3D1F6B;
}

#logo-area {
    height: 8;
    background: #070010;
    border-bottom: solid #3D1F6B;
    padding: 0 2;
}

#status-bar {
    height: 1;
    background: #0A000F;
    padding: 0 2;
    border-bottom: solid #3D1F6B;
}

#chat-scroll {
    background: #050008;
    scrollbar-color: #3D1F6B;
    scrollbar-color-hover: #6B3FA0;
    scrollbar-color-active: #BF00FF;
}

#chat-log {
    background: #050008;
    color: #E8D5FF;
    padding: 1 2;
    scrollbar-color: #3D1F6B;
}

/* ── Input ────────────────────────────────────── */
#input-area {
    height: 3;
    background: #070010;
    border-top: solid #3D1F6B;
    padding: 0 1;
}

Input {
    background: #0D0020;
    color: #E8D5FF;
    border: solid #3D1F6B;
    margin: 0;
}

Input:focus {
    border: solid #BF00FF;
    background: #120025;
    color: #FFFFFF;
}

Input.-disabled {
    border: solid #1F0040;
    color: #3D1F6B;
}

/* ── Columna 3: Kernel log ────────────────────── */
#kernel-panel {
    width: 32;
    background: #030007;
    border-left: solid #3D1F6B;
}

#kernel-label {
    background: #0A000F;
    color: #FF00FF;
    text-style: bold;
    padding: 0 1;
    border-bottom: solid #3D1F6B;
}

#kernel-log {
    background: #030007;
    color: #9D6FE8;
    padding: 0 1;
    scrollbar-color: #3D1F6B;
    scrollbar-color-hover: #6B3FA0;
}
"""


# ═══════════════════════════════════════════════════════════════════════════
# APP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

class XulcanStudioApp(App):
    """Xulcan Studio — Centro de Comando Visual."""

    CSS        = CSS
    TITLE      = "✦ XULCAN STUDIO"
    SUB_TITLE  = "Agent OS v1.0"
    BINDINGS   = [
        ("ctrl+c", "quit",         "Salir"),
        ("ctrl+l", "clear_chat",   "Limpiar chat"),
        ("ctrl+k", "clear_kernel", "Limpiar kernel"),
        ("f5",     "reload_agent", "Recargar agente"),
    ]

    def __init__(self):
        super().__init__()
        self.xulcan_engine = Xulcan(
            gemini_api_key="AIzaSyAn1zDKKL5y9txvujUODgxZooyzimBLJtQ",
            groq_api_key=os.getenv("GROQ_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
        self.xulcan_engine.enable_sandbox()

        self.agent        = None
        self._session_key = None   # Clave de sesión — gestiona la continuidad multi-turno
        self._last_yml    = None

    # ── Composición ────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="main-layout"):

            # ── Col 1: Árbol de archivos ──────────────────────────────────
            with Vertical(id="tree-panel"):
                yield Label("◈  WORKSPACE", id="tree-label")
                yield DirectoryTree("./", id="tree-view")

            # ── Col 2: Chat + Logo + Input ────────────────────────────────
            with Vertical(id="chat-panel"):
                yield LogoWidget(id="logo-area")
                yield StatusBar(id="status-bar")
                with VerticalScroll(id="chat-scroll"):
                    yield RichLog(id="chat-log", markup=True, highlight=True)
                with Vertical(id="input-area"):
                    yield Input(
                        placeholder="← Selecciona un manifiesto .yml para activar un agente",
                        id="prompt-input",
                        disabled=True
                    )

            # ── Col 3: Telemetría del kernel ──────────────────────────────
            with Vertical(id="kernel-panel"):
                yield Label("⚡  TELEMETRÍA DEL KERNEL", id="kernel-label")
                yield RichLog(id="kernel-log", markup=True, highlight=True)

        yield Footer()

    # ── Montaje ─────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        chat = self.query_one("#chat-log", RichLog)
        kern = self.query_one("#kernel-log", RichLog)

        # Bienvenida en el chat
        chat.write(Text.from_markup(SEPARATOR))
        chat.write(Text.from_markup(
            "\n[bold #BF00FF]  XULCAN STUDIO[/] [#6B3FA0]— Centro de Comando Visual[/]\n"
        ))
        chat.write(Text.from_markup(
            "[#9D6FE8]  Navega el árbol de la izquierda y selecciona un archivo[/] "
            "[bold #FF00FF].yml[/] [#9D6FE8]para activar un agente.[/]\n"
        ))
        chat.write(Text.from_markup(SEPARATOR + "\n"))

        # Telemetría inicial
        kern.write(Text.from_markup(
            "[bold #FF00FF]◈ XULCAN KERNEL[/] [#6B3FA0]inicializando...[/]"
        ))
        kern.write(Text.from_markup(
            f"[#6B3FA0]· Sandbox Docker:[/] [#00FFCC]habilitado[/]"
        ))
        kern.write(Text.from_markup(
            f"[#6B3FA0]· Gemini:[/] "
            f"{'[#00FFCC]configurado[/]' if os.getenv('GEMINI_API_KEY') else '[#FF2D6B]sin clave[/]'}"
        ))
        kern.write(Text.from_markup(
            f"[#6B3FA0]· Groq:[/] "
            f"{'[#00FFCC]configurado[/]' if os.getenv('GROQ_API_KEY') else '[#FF2D6B]sin clave[/]'}"
        ))
        kern.write(Text.from_markup(
            f"[#6B3FA0]· Anthropic:[/] "
            f"{'[#00FFCC]configurado[/]' if os.getenv('ANTHROPIC_API_KEY') else '[#FF2D6B]sin clave[/]'}"
        ))
        kern.write(Text.from_markup(
            f"[#6B3FA0]· Event Sourcing Ledger:[/] [#00FFCC]activo[/]\n"
        ))

        # Redirigir logs de xulcan al panel de kernel
        logging.basicConfig(level=logging.INFO)
        xulcan_logger = logging.getLogger("xulcan")
        xulcan_logger.setLevel(logging.INFO)
        xulcan_logger.handlers = []
        xulcan_logger.addHandler(TextualLogHandler(kern))
        xulcan_logger.propagate = False

        # Actualizar el status bar cada segundo
        self.set_interval(1, self._tick_status)

    def _tick_status(self) -> None:
        self.query_one(StatusBar).refresh()

    # ── Eventos de árbol ────────────────────────────────────────────────────

    async def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        path = str(event.path)
        chat = self.query_one("#chat-log", RichLog)
        kern = self.query_one("#kernel-log", RichLog)

        if not path.endswith((".yml", ".yaml")):
            chat.write(Text.from_markup(
                f"[bold #FF2D6B]✖  '{path}' no es un manifiesto YAML.[/]"
            ))
            return

        kern.write(Text.from_markup(
            f"\n[#6B3FA0]──────────────────────────────[/]"
        ))
        kern.write(Text.from_markup(
            f"[bold #BF00FF]◈ Cargando manifiesto:[/] [#E8D5FF]{path}[/]"
        ))

        try:
            self.agent     = self.xulcan_engine.load_agent(path)
            self._last_yml = path

            # Cada carga de agente inicia una sesión nueva e independiente.
            # La session_key vincula todos los turnos de esta conversación en el Ledger.
            self._session_key = f"studio-{self.agent.id}-{uuid.uuid4().hex[:8]}"

            status = self.query_one(StatusBar)
            status.agent_name = self.agent.name
            status.run_count  = 0
            status.status     = "READY"

            inp = self.query_one(Input)
            inp.disabled    = False
            inp.placeholder = f"Ordena algo a {self.agent.name}…"
            inp.focus()

            chat.write(Text.from_markup(SEPARATOR))
            chat.write(Text.from_markup(
                f"\n[bold #00FFCC]✦  {self.agent.name}[/] [#9D6FE8]está en línea y esperando órdenes.[/]\n"
            ))
            chat.write(Text.from_markup(SEPARATOR + "\n"))

            kern.write(Text.from_markup(
                f"[bold #00FFCC]✔  Agente '{self.agent.name}' activado.[/]"
            ))
            kern.write(Text.from_markup(
                f"[#6B3FA0]· session_key:[/] [#BF00FF]{self._session_key}[/]\n"
            ))

            self.title = f"✦ XULCAN STUDIO  ·  {self.agent.name}"

        except Exception as e:
            self.query_one(StatusBar).status = "ERROR"
            chat.write(Text.from_markup(
                f"[bold #FF2D6B]✖  Error al cargar el manifiesto:[/]\n"
                f"[#FF2D6B]{str(e)}[/]\n"
            ))
            kern.write(Text.from_markup(
                f"[bold #FF2D6B]✖  FALLO EN CARGA: {str(e)}[/]\n"
            ))

    # ── Envío de prompt ─────────────────────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        if not user_text or not self.agent:
            return

        inp  = self.query_one(Input)
        chat = self.query_one("#chat-log", RichLog)
        kern = self.query_one("#kernel-log", RichLog)
        sb   = self.query_one(StatusBar)

        inp.value    = ""
        inp.disabled = True
        sb.status    = "THINKING"

        ts = datetime.now().strftime("%H:%M:%S")

        chat.write(Text.from_markup(
            f"[#3D1F6B]┌── [/][bold #9D6FE8]TÚ[/] [#3D1F6B]{ts}[/]"
        ))
        chat.write(Text.from_markup(f"[#3D1F6B]│[/]  {user_text}"))
        chat.write(Text.from_markup(f"[#3D1F6B]└──[/]\n"))

        kern.write(Text.from_markup(
            f"[#6B3FA0]· turno iniciado — session:[/] "
            f"[#BF00FF]{self._session_key}[/]"
        ))

        try:
            t0 = time.monotonic()

            # app.run() gestiona la continuidad multi-turno internamente
            # a través de session_key — no es necesario rastrear run_id manualmente.
            respuesta: str = await self.xulcan_engine.run(
                prompt=user_text,
                blueprint=self.agent,
                session_key=self._session_key,
            )

            elapsed = time.monotonic() - t0
            sb.run_count += 1
            sb.status = "READY"

            ts2 = datetime.now().strftime("%H:%M:%S")
            chat.write(Text.from_markup(
                f"[#3D1F6B]┌── [/][bold #BF00FF]✦ {self.agent.name}[/] "
                f"[#3D1F6B]{ts2} · {elapsed:.1f}s[/]"
            ))
            for line in respuesta.split("\n"):
                chat.write(Text.from_markup(
                    f"[#3D1F6B]│[/]  [#E8D5FF]{line}[/]"
                ))
            chat.write(Text.from_markup(f"[#3D1F6B]└──[/]\n"))

            kern.write(Text.from_markup(
                f"[#00FFCC]✔  turno completado en {elapsed:.2f}s[/]\n"
            ))

        except Exception as e:
            sb.status = "ERROR"
            chat.write(Text.from_markup(
                f"[bold #FF2D6B]✖  Error en la ejecución:[/]\n"
                f"[#FF2D6B]{str(e)}[/]\n"
            ))
            kern.write(Text.from_markup(
                f"[bold #FF2D6B]✖  KERNEL PANIC: {str(e)}[/]\n"
            ))
        finally:
            inp.disabled = False
            inp.focus()

    # ── Acciones de teclas ──────────────────────────────────────────────────

    def action_clear_chat(self) -> None:
        self.query_one("#chat-log", RichLog).clear()
        self.query_one("#chat-log", RichLog).write(
            Text.from_markup("[#3D1F6B]Chat limpiado.[/]\n")
        )

    def action_clear_kernel(self) -> None:
        self.query_one("#kernel-log", RichLog).clear()

    def action_reload_agent(self) -> None:
        if self._last_yml:
            self.run_in_worker(self._reload())

    async def _reload(self) -> None:
        if not self._last_yml:
            return
        kern = self.query_one("#kernel-log", RichLog)
        kern.write(Text.from_markup(
            f"[bold #FFB830]⚡ Recargando {self._last_yml}…[/]"
        ))
        try:
            self.agent = self.xulcan_engine.load_agent(self._last_yml)

            # Nueva session al recargar — historial anterior queda en el Ledger
            # pero la conversación activa empieza limpia.
            self._session_key = f"studio-{self.agent.id}-{uuid.uuid4().hex[:8]}"

            self.query_one(StatusBar).status = "READY"
            kern.write(Text.from_markup(
                f"[#00FFCC]✔  Recarga exitosa.[/] "
                f"[#6B3FA0]session: {self._session_key}[/]\n"
            ))
        except Exception as e:
            kern.write(Text.from_markup(
                f"[#FF2D6B]✖  Fallo en recarga: {e}[/]\n"
            ))


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    XulcanStudioApp().run()