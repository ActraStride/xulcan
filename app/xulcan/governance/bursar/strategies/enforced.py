"""Enforced Bursar — budget enforcement real contra límites declarados.

Estrategia autónoma: recibe sus límites via self.config en la instanciación,
no como argumentos en cada llamada. El Kernel nunca inspecciona BursarConfig
internals — solo reacciona al BursarVerdict.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from xulcan.core.primitives import ImmutableRecord, FinitePositiveFloat
from xulcan.core.economics import UsageStats
from xulcan.governance.bursar.base import BaseBursarConfig, BaseBursarStrategy
from xulcan.governance.verdicts import BursarVerdict
from xulcan.governance.errors import BursarHaltError


class EnforcedBursarConfig(BaseBursarConfig):
    """Configuración para el Bursar con enforcement real.

    Requiere al menos uno de token_limit o time_limit_ms.
    Instanciar sin ninguno de los dos lanza ValueError inmediatamente
    en tiempo de parseo del YAML — el error aparece donde corresponde,
    no en runtime.

    Attributes:
        token_limit: Límite de tokens totales del run. None = sin límite de tokens.
        time_limit_ms: Límite de latencia acumulada en ms. None = sin límite de tiempo.
        warn_at_percent: Si se define (0.0-1.0), emite WARN cuando el consumo
                         supera este porcentaje del límite antes de llegar al HALT.
                         None = sin warning previo, va directo a HALT.
    """
    token_limit: int | None = Field(
        default=None,
        gt=0,
        description="Límite de tokens totales. None = sin límite de tokens."
    )
    time_limit_ms: FinitePositiveFloat | None = Field(
        default=None,
        description="Límite de latencia acumulada en ms. None = sin límite de tiempo."
    )
    warn_at_percent: float | None = Field(
        default=None,
        ge=0.0,
        lt=1.0,
        description=(
            "Porcentaje del límite (0.0–1.0) en el que emitir WARN antes de HALT. "
            "e.g. 0.8 = WARN al 80% del límite. None = sin warning previo."
        )
    )

    @model_validator(mode='after')
    def require_at_least_one_limit(self) -> EnforcedBursarConfig:
        """Garantiza que EnforcedBursarConfig no sea instanciable sin límites.

        Un Enforced sin límites es semánticamente idéntico a Unlimited
        pero sin decirlo — ese estado de mentira no debe existir.
        """
        if self.token_limit is None and self.time_limit_ms is None:
            raise ValueError(
                "EnforcedBursarConfig requiere al menos un límite: "
                "token_limit o time_limit_ms. "
                "Para runs sin límite, usa UnlimitedBursarStrategy."
            )
        return self


class EnforcedBursarStrategy(BaseBursarStrategy):
    """Enforces real budget limits against cumulative UsageStats.

    Evaluation order (tokens primero, luego tiempo):
        1. Si token_limit está definido y total_tokens > límite → HALT
        2. Si time_limit_ms está definido y latency_ms > límite → HALT
        3. Si warn_at_percent está definido y cualquier dimensión > umbral → WARN
        4. Otherwise → APPROVED

    El HALT levanta BursarHaltError desde el Kernel — la estrategia
    retorna el veredicto puro; es el Kernel quien decide cómo reaccionar.

    YAML:
        governance:
          budget:
            enforced:
              token_limit: 50000
              warn_at_percent: 0.8
    """

    ConfigSchema = EnforcedBursarConfig

    def _raise_halt(self, cumulative_usage: UsageStats) -> None:
        """Levanta BursarHaltError con el límite preciso de esta config."""
        config: EnforcedBursarConfig = self.config  # type: ignore[assignment]

        # Determinar qué límite fue excedido y por cuánto
        if config.token_limit is not None and cumulative_usage.total_tokens >= config.token_limit:
            raise BursarHaltError(
                "Token limit exceeded.",
                current_usage=float(cumulative_usage.total_tokens),
                limit=float(config.token_limit),
                limit_type="tokens",
            )
        if config.time_limit_ms is not None and cumulative_usage.latency_ms >= config.time_limit_ms:
            raise BursarHaltError(
                "Time limit exceeded.",
                current_usage=float(cumulative_usage.latency_ms),
                limit=float(config.time_limit_ms),
                limit_type="time_ms",
            )
        # Fallback — no debería llegar aquí si _check() retornó HALT
        raise BursarHaltError(
            "Bursar halted the run (unknown limit).",
            current_usage=float(cumulative_usage.total_tokens),
            limit=0.0,
            limit_type="unknown",
        )

    def _check(self, cumulative_usage: UsageStats) -> BursarVerdict:
        config: EnforcedBursarConfig = self.config  # type: ignore[assignment]

        # ── 1. HALT checks (hard limits) ──────────────────────────────────
        if config.token_limit is not None:
            if cumulative_usage.total_tokens >= config.token_limit:
                return BursarVerdict.HALT

        if config.time_limit_ms is not None:
            if cumulative_usage.latency_ms >= config.time_limit_ms:
                return BursarVerdict.HALT

        # ── 2. WARN checks (soft threshold) ───────────────────────────────
        if config.warn_at_percent is not None:
            if config.token_limit is not None:
                token_threshold = config.token_limit * config.warn_at_percent
                if cumulative_usage.total_tokens >= token_threshold:
                    return BursarVerdict.WARN

            if config.time_limit_ms is not None:
                time_threshold = config.time_limit_ms * config.warn_at_percent
                if cumulative_usage.latency_ms >= time_threshold:
                    return BursarVerdict.WARN

        return BursarVerdict.APPROVED