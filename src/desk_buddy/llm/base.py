from abc import ABC, abstractmethod


class LLMError(Exception):
    """Raised when an LLM backend cannot be reached or returns an error."""


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        """Send a system+user prompt, return the model's text reply."""
        raise NotImplementedError
