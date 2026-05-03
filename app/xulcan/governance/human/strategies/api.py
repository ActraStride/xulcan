import asyncio
from typing import Dict
from xulcan.core import MachineID
from xulcan.governance.human.base import (
    BaseHumanGateStrategy, BaseHumanGateConfig,
    HumanGateResult, HumanGateDecision
)
from xulcan.protocol.tools import ToolCall

# Diccionario global en memoria para pausar y reanudar los Runs
PENDING_DECISIONS: Dict[str, asyncio.Future] = {}

class ApiHumanGateConfig(BaseHumanGateConfig):
    timeout_seconds: float = 300.0  # 5 minutos para que el humano responda en la web

class ApiHumanGateStrategy(BaseHumanGateStrategy):
    """Pausa el FSM y espera a que un endpoint de FastAPI resuelva el futuro."""
    
    ConfigSchema = ApiHumanGateConfig

    async def _obtain_decision(
        self, call: ToolCall, reason: str, run_id: MachineID
    ) -> HumanGateResult:
        
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        # Guardamos el futuro en memoria para que FastAPI lo pueda "tocar"
        PENDING_DECISIONS[run_id] = future

        # ⚡ Nota: El Kernel ya emitió el evento 'human_intervention_required'
        # por el Firehose, así que tu Frontend Web ya sabe que debe mostrar los botones.

        try:
            # El Kernel se queda "dormido" aquí sin bloquear el CPU
            result = await asyncio.wait_for(future, timeout=self.config.timeout_seconds)
            return result
        except asyncio.TimeoutError:
            return HumanGateResult(
                decision=HumanGateDecision.REJECTED,
                feedback=f"Auto-rechazado: El operador no respondió en la interfaz web tras {self.config.timeout_seconds}s."
            )
        finally:
            PENDING_DECISIONS.pop(run_id, None)