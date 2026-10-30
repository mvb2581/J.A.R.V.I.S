"""Testes de palavra-chave, limpeza de texto para fala e confirmação por voz."""

from __future__ import annotations

from backend.voice.service import _AFFIRMATIVE, _NEGATIVE, _matches
from backend.voice.text_to_speech import _chunks, clean_text_for_speech
from backend.voice.wake_word import (
    extract_command,
    find_wake_word,
    normalize_phrase,
    strip_wake_word,
)


def test_normalize_phrase_removes_accents_and_punctuation() -> None:
    assert normalize_phrase("  Járvis, você está aí?! ") == "jarvis voce esta ai"


def test_find_wake_word_simple() -> None:
    assert find_wake_word("Jarvis, abra o navegador", "jarvis") == 0
    assert find_wake_word("Ei, jarvis, toque música", "jarvis") == 1
    assert find_wake_word("abra o navegador", "jarvis") is None


def test_find_wake_word_tolerates_accents_and_typos() -> None:
    assert find_wake_word("Járvis abra o app", "jarvis") == 0
    assert find_wake_word("jarvs abra o app", "jarvis") == 0


def test_multi_word_wake_word() -> None:
    assert find_wake_word("ei jarvis, qual a hora?", "ei jarvis") == 0
    assert find_wake_word("jarvis qual a hora?", "ei jarvis") is None


def test_extract_command() -> None:
    found, command = extract_command("Jarvis, abra o Visual Studio Code", "jarvis")
    assert found is True
    assert command == "abra o Visual Studio Code"

    found, command = extract_command("qual a hora?", "jarvis")
    assert found is False
    assert command == "qual a hora?"


def test_strip_wake_word_anywhere() -> None:
    assert strip_wake_word("por favor jarvis abra", "jarvis") == "por favor abra"
    assert strip_wake_word("sem palavra", "jarvis") == "sem palavra"


def test_clean_text_for_speech_removes_markdown_and_urls() -> None:
    text = (
        "**Olá**, senhor!\n\n"
        "```python\nprint('segredo')\n```\n"
        "Veja [a documentação](https://exemplo.com) ou acesse https://outro.com.\n"
        "Use `create_file` com cuidado."
    )
    cleaned = clean_text_for_speech(text)
    assert "**" not in cleaned
    assert "```" not in cleaned
    assert "print" not in cleaned
    assert "https://" not in cleaned
    assert "documentação" in cleaned
    assert "create file" in cleaned


def test_clean_text_for_speech_respects_limit() -> None:
    assert len(clean_text_for_speech("a" * 100, limit=10)) == 10


def test_chunks_split_long_text() -> None:
    text = "Primeira frase. Segunda frase. Terceira frase."
    chunks = _chunks(text, size=20)
    assert len(chunks) > 1
    assert "".join(chunk.replace(" ", "") for chunk in chunks).startswith("Primeirafrase")


def test_voice_confirmation_matching() -> None:
    assert _matches("sim", _AFFIRMATIVE) is True
    assert _matches("Sim, pode executar", _AFFIRMATIVE) is True
    assert _matches("não", _NEGATIVE) is True
    assert _matches("não autorizo", _NEGATIVE) is True
    assert _matches("talvez", _AFFIRMATIVE) is False
    assert _matches("sim", _NEGATIVE) is False
