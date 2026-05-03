"""Isolation Provider Interface for Sandbox Execution.

Defines the strict contract for isolation technologies (Docker, Firecracker, WASM).
Implementations must be 100% stateless: they should not store session state in
memory (self), but rather query the underlying engine as the single source of truth.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("xulcan.tools.sandbox.provider")


class IsolationProvider(ABC):
    """Abstract contract for sandboxed execution environments."""

    @abstractmethod
    async def is_active(self, session_id: str) -> bool:
        """Checks the underlying engine to see if the session's sandbox is running."""
        ...

    @abstractmethod
    async def start_session(
        self, 
        session_id: str, 
        workspace_path: str | None = None
    ) -> None:
        """Initializes or wakes up an isolated environment for the session ID."""
        ...

    @abstractmethod
    async def execute_command(
        self, 
        session_id: str, 
        command: str, 
        timeout: int = 30
    ) -> dict[str, Any]:
        """Executes a command deterministically inside the live session.
        
        Args:
            session_id: The active sandbox session identifier.
            command: The shell command to execute.
            timeout: Maximum execution time in seconds before SIGKILL.
            
        Returns:
            A dictionary representing the execution result, containing:
                - 'stdout': str (Standard output stream)
                - 'stderr': str (Standard error stream)
                - 'exit_code': int (Process exit code, e.g., 0 for success)
        """
        ...

    @abstractmethod
    async def read_file(self, session_id: str, file_path: str) -> str:
        """Reads the content of a file from the session's isolated filesystem."""
        ...

    @abstractmethod
    async def write_file(
        self, 
        session_id: str, 
        file_path: str, 
        content: str
    ) -> None:
        """Safely writes a file to the session's isolated filesystem."""
        ...

    @abstractmethod
    async def terminate_session(self, session_id: str) -> None:
        """Terminates and destroys the ephemeral environment, cleaning up resources."""
        ...