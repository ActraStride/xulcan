"""Standard text tools."""

from xulcan.tools.base import BaseTool, tool


@tool
class Echo(BaseTool):
    """Echo back the provided text."""

    text: str

    def run(self) -> str:
        return self.text


@tool
class Uppercase(BaseTool):
    """Uppercase the provided text."""

    text: str

    def run(self) -> str:
        return self.text.upper()


@tool
class WordCount(BaseTool):
    """Count words in the provided text."""

    text: str

    def run(self) -> int:
        return len(self.text.split())
