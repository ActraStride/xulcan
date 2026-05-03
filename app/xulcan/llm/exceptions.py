"""Domain exceptions for the LLM execution layer."""

class LLMError(Exception):
    """Base class for all LLM adapter errors."""
    pass

class TransientLLMError(LLMError):
    """Recoverable errors (Rate limits, 500s, Timeouts). Triggers fallback."""
    pass

class FatalLLMError(LLMError):
    """Non-recoverable errors (Auth failed, Bad Request). Halts execution."""
    pass