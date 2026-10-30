"""Detecção tolerante da palavra-chave de ativação."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_phrase(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", without_accents.lower())).strip()


def _similar(token: str, wake_word: str) -> bool:
    if token == wake_word:
        return True
    if len(token) < 3:
        return False
    return SequenceMatcher(None, token, wake_word).ratio() >= 0.78


def find_wake_word(transcript: str, wake_word: str) -> int | None:
    """Retorna o índice do token da palavra-chave no texto original, ou None."""
    original_tokens = re.findall(r"\S+", transcript.strip())
    normalized_tokens = [normalize_phrase(token) for token in original_tokens]
    target_tokens = normalize_phrase(wake_word).split()
    if not target_tokens or not normalized_tokens:
        return None
    if len(target_tokens) == 1:
        for index, token in enumerate(normalized_tokens):
            if _similar(token, target_tokens[0]):
                return index
        return None
    for index in range(len(normalized_tokens) - len(target_tokens) + 1):
        window = normalized_tokens[index : index + len(target_tokens)]
        if all(
            _similar(token, expected)
            for token, expected in zip(window, target_tokens, strict=False)
        ):
            return index
    return None


def extract_command(transcript: str, wake_word: str) -> tuple[bool, str]:
    """Separa a palavra-chave do comando restante.

    Retorna ``(encontrou, comando)``. Se a palavra-chave não aparecer, devolve o
    texto completo como comando (útil no modo de escuta direta).
    """
    index = find_wake_word(transcript, wake_word)
    if index is None:
        return False, transcript.strip()
    original_tokens = re.findall(r"\S+", transcript.strip())
    target_count = len(normalize_phrase(wake_word).split())
    command_tokens = original_tokens[index + target_count :]
    command = " ".join(command_tokens).strip(" ,.;:!?")
    return True, command


def strip_wake_word(transcript: str, wake_word: str) -> str:
    """Remove a palavra-chave onde ela aparecer, preservando o restante."""
    index = find_wake_word(transcript, wake_word)
    if index is None:
        return transcript.strip()
    original_tokens = re.findall(r"\S+", transcript.strip())
    target_count = len(normalize_phrase(wake_word).split())
    remaining = original_tokens[:index] + original_tokens[index + target_count :]
    return " ".join(remaining).strip(" ,.;:!?")
