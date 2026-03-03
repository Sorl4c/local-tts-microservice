from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SupportedFormat = Literal["mp3", "wav", "flac", "aac", "opus"]
EngineName = Literal["kokoro", "chatterbox"]


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = "tts-1"
    input: str = Field(min_length=1)
    voice: str | None = None
    lang_code: str | None = None
    response_format: SupportedFormat = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    engine: EngineName | None = None
    stream: bool = False

    @field_validator("input")
    @classmethod
    def validate_input_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("`input` cannot be empty")
        return normalized


class ModelEntry(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "local"
    engine: EngineName
    metadata: dict[str, Any] | None = None


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelEntry]


class BackendHealth(BaseModel):
    engine: EngineName
    healthy: bool
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    backends: list[BackendHealth]
