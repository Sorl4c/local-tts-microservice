from utils.chunker import chunk_text


def test_chunk_text_respects_limit() -> None:
    text = (
        "Esta es la primera frase de prueba. "
        "Esta es la segunda frase con mas contenido para validar el algoritmo. "
        "Y esta es la tercera."
    )
    chunks = chunk_text(text=text, max_chars=50, language="es")
    assert chunks
    assert all(len(chunk) <= 50 for chunk in chunks)
    rebuilt = " ".join(chunks)
    assert "primera frase" in rebuilt
    assert "tercera" in rebuilt


def test_chunk_text_handles_long_words() -> None:
    text = "superhipermegapalabralargasinseparadores " * 2
    chunks = chunk_text(text=text, max_chars=10, language="es")
    assert chunks
    assert all(len(chunk) <= 10 for chunk in chunks)

