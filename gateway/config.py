from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


EngineName = Literal["kokoro", "chatterbox"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    default_engine: EngineName = Field(default="kokoro", alias="DEFAULT_ENGINE")
    kokoro_url: str = Field(default="http://kokoro:8880", alias="KOKORO_URL")
    chatterbox_url: str = Field(default="http://chatterbox:8000", alias="CHATTERBOX_URL")
    default_voice_kokoro: str = Field(default="ef_dora", alias="DEFAULT_VOICE_KOKORO")
    default_voice_chatterbox: str = Field(default="alloy", alias="DEFAULT_VOICE_CHATTERBOX")
    default_lang_code: str = Field(default="es", alias="DEFAULT_LANG_CODE")
    output_format: str = Field(default="mp3", alias="OUTPUT_FORMAT")
    request_timeout_seconds: float = Field(default=120.0, alias="REQUEST_TIMEOUT_SECONDS")
    chunk_max_chars: int = Field(default=500, alias="CHUNK_MAX_CHARS")
    chunk_language: str = Field(default="es", alias="CHUNK_LANGUAGE")
    max_input_chars: int = Field(default=12000, alias="MAX_INPUT_CHARS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
