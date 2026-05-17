"""Errores de dominio del sistema de gobernanza de Xulcan.

Separados de core/ porque son errores de política (governance),
no de física (core). Un error de budget no es una primitiva del
framework — es una consecuencia de una decisión del Bursar.
"""

from __future__ import annotations


class BursarHaltError(RuntimeError):
    """Raised by the Kernel when the Bursar returns BursarVerdict.HALT.

    Lleva el límite y el consumo actual para que el Ledger pueda
    registrar un RunFailed con datos precisos — sin que el Kernel
    tenga que inspeccionar los internals del BursarConfig.

    Attributes:
        current_usage: Valor de consumo en el momento del halt.
        limit: El límite declarado que fue excedido.
        limit_type: Qué tipo de límite se excedió ('tokens', 'time_ms', 'usd', etc.)
    """

    def __init__(
        self,
        message: str,
        current_usage: float,
        limit: float,
        limit_type: str = "tokens",
    ):
        self.current_usage = current_usage
        self.limit = limit
        self.limit_type = limit_type
        super().__init__(
            f"{message} "
            f"(usage: {current_usage} > limit: {limit} [{limit_type}])"
        )


class RunNotSuspendedError(RuntimeError):
    """Raised when resume_run() is called on a run that is not suspended.

    This prevents corrupting the run state if resume_run() is called
    on a completed, failed, or non-existent run.

    Attributes:
        run_id: The run ID that was not suspended.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(
            f"Run '{run_id}' is not suspended. "
            f"Cannot resume. The run may be completed, failed, or never existed."
        )