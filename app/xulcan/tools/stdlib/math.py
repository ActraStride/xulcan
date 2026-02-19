"""Standard math tools."""

from xulcan.tools.base import BaseTool, tool


@tool
class Add(BaseTool):
    """Add two numbers."""

    a: float
    b: float

    def run(self) -> float:
        return self.a + self.b


@tool
class Multiply(BaseTool):
    """Multiply two numbers."""

    a: float
    b: float

    def run(self) -> float:
        return self.a * self.b
