from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class AdapterError(RuntimeError):
    pass


@dataclass
class SynthesisResult:
    audio: bytes
    media_type: str
    response_format: str


@dataclass
class HealthStatus:
    healthy: bool
    detail: str


class BackendAdapter(ABC):
    name: str

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        model: str,
        voice: str,
        lang_code: str | None,
        response_format: str,
        speed: float,
    ) -> SynthesisResult:
        raise NotImplementedError

    @abstractmethod
    async def list_models(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        raise NotImplementedError
