import pytest
from pydantic import ValidationError

from schemas import SpeechRequest


def test_speech_request_defaults() -> None:
    req = SpeechRequest(input="Hola")
    assert req.model == "tts-1"
    assert req.response_format == "mp3"
    assert req.speed == 1.0


def test_speech_request_rejects_empty_input() -> None:
    with pytest.raises(ValidationError):
        SpeechRequest(input="   ")

