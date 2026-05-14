from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    def build_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        raise NotImplementedError
