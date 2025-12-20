"""Defines agent configuration types (the "Blueprint" dimension).

This module contains types for defining agent behavior, including model
selection, system prompts, tool configurations, and execution parameters.
Agents in Xulcan are data (JSON configurations), not code (classes).
"""
import re

from enum import Enum
from typing import List, Literal, Optional
from pydantic import Field, field_validator

from .base import CanonicalModel


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL ENUMS (Not exported in __init__.py)
# ═══════════════════════════════════════════════════════════════════════════

class _ModelProvider(str, Enum):
    """Internal enum for model provider validation.
    
    External APIs use string literals ("openai", "anthropic", etc.) for stability.
    This enum is used internally for validation and provider routing only.
    """
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


# ═══════════════════════════════════════════════════════════════════════════
# AGENT CONFIGURATION TYPES
# ═══════════════════════════════════════════════════════════════════════════

class AgentToolConfig(CanonicalModel):
    """Configuration for a single tool available to an agent.
    
    Tools can be enabled/disabled without removing them from the configuration.
    
    Attributes:
        name: The tool identifier (must match a registered tool).
        enabled: Whether this tool is currently available to the agent.
    
    Example:
        >>> tool = AgentToolConfig(name="web_search", enabled=True)
        >>> disabled_tool = AgentToolConfig(name="file_write", enabled=False)
    """
    name: str = Field(
        min_length=1,
        description="Tool identifier (must match a registered tool)"
    )
    
    enabled: bool = Field(
        default=True,
        description="Whether this tool is available to the agent"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure tool name is valid (no whitespace, reasonable length)."""
        if not v or not v.strip():
            raise ValueError("Tool name cannot be empty or whitespace")
        
        if len(v) > 64:
            raise ValueError("Tool name cannot exceed 64 characters")
        
        return v.strip()


class AgentBlueprint(CanonicalModel):
    """The static configuration for an agent (the "DNA").
    
    This is the Blueprint dimension of Xulcan's Trinity. It defines what
    an agent is, but not what it has done (that's History) or how it
    communicates with LLMs (that's Protocol).
    
    Design Philosophy:
        - Agents are DATA, not CODE
        - Blueprints are versioned and immutable
        - Configuration is declarative and API-first
    
    Attributes:
        id: Unique identifier (e.g., "customer-support-v1").
        name: Human-readable name for this agent.
        version: Semantic version of this configuration.
        description: What this agent does and when to use it.
        model_provider: Which LLM provider to use.
        model_name: Specific model identifier (e.g., "gpt-4", "claude-sonnet-4").
        temperature: Sampling temperature (0.0 = deterministic, 2.0 = creative).
        max_tokens: Hard limit on response length (None = provider default).
        system_prompt: Instructions that define the agent's behavior.
        tools: List of available tools with their configurations.
        timeout_seconds: Maximum execution time before forced termination.
    
    Example:
        >>> blueprint = AgentBlueprint(
        ...     id="weather-assistant",
        ...     name="Weather Assistant",
        ...     version="1.0.0",
        ...     description="Provides weather information using web search",
        ...     model_provider="openai",
        ...     model_name="gpt-4",
        ...     system_prompt="You are a helpful weather assistant.",
        ...     tools=[
        ...         AgentToolConfig(name="web_search", enabled=True)
        ...     ],
        ...     timeout_seconds=300
        ... )
    """
    id: str = Field(
        min_length=1,
        max_length=128,
        description="Unique identifier for this agent configuration"
    )
    
    name: str = Field(
        min_length=1,
        max_length=256,
        description="Human-readable agent name"
    )
    
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version (major.minor.patch)"
    )
    
    description: str = Field(
        default="",
        max_length=1024,
        description="What this agent does and when to use it"
    )
    
    # Model Configuration
    model_provider: Literal["openai", "anthropic", "google"] = Field(
        description="LLM provider to use for this agent"
    )
    
    model_name: str = Field(
        min_length=1,
        max_length=128,
        description="Specific model identifier (e.g., 'gpt-4', 'claude-sonnet-4')"
    )
    
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0=deterministic, 2.0=creative)"
    )
    
    max_tokens: Optional[int] = Field(
        default=None,
        gt=0,
        description="Hard limit on output tokens (None=provider default)"
    )
    
    # Agent Behavior
    system_prompt: str = Field(
        min_length=1,
        description="Instructions that define the agent's behavior"
    )
    
    tools: List[AgentToolConfig] = Field(
        default_factory=list,
        description="Available tools with their configurations"
    )
    
    # Execution Constraints
    timeout_seconds: int = Field(
        default=600,
        ge=1,
        le=3600,
        description="Maximum execution time before forced termination"
    )

    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Ensure agent ID is valid (alphanumeric + hyphens/underscores)."""
        if not v or not v.strip():
            raise ValueError("Agent ID cannot be empty")
        
        # Allow alphanumeric, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(
                "Agent ID must contain only alphanumeric characters, "
                "hyphens, and underscores"
            )
        
        return v.strip()

    @field_validator('system_prompt')
    @classmethod
    def validate_system_prompt(cls, v: str) -> str:
        """Ensure system prompt is not empty or just whitespace."""
        if not v or not v.strip():
            raise ValueError("System prompt cannot be empty or whitespace")
        return v

    @property
    def enabled_tools(self) -> List[str]:
        """Get a list of currently enabled tool names.
        
        Returns:
            List of tool names where enabled=True.
        
        Example:
            >>> blueprint.enabled_tools
            ['web_search', 'calculator']
        """
        return [tool.name for tool in self.tools if tool.enabled]

    @property
    def has_tools(self) -> bool:
        """Check if this agent has any enabled tools.
        
        Returns:
            True if at least one tool is enabled.
        """
        return len(self.enabled_tools) > 0