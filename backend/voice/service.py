"""Serviço que conecta reconhecimento de voz, assistente e síntese de voz."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from backend.core.assistant import AssistantService
from backend.core.events import EventBus, StateManager
from backend.core.settings_service import SettingsService
from backend.core.utils import normalize_text
from backend.voice.speech_recognition import (
    RecognitionOutcome,
    SpeechRecognizer,
    STTError,
    list_microphones,
)
from backend.voice.text_to_speech import TTSService

logger = logging.getLogger(__name__)

_AFFIRMATIVE = {
    "sim",
    "aprovar",
    "aprovado",
    "aprovo",
    "confirmar",
    "confirmo",
    "confirmado",
    "pode",
    "pode executar",
    "execute",
    "executar",
    "autorizo",
    "autorizado",
    "prossiga",
}
_NEGATIVE = {
    "nao",
    "negar",
    "nego",
    "recusar",
    "recuso",
    "cancelar",
    "cancele",
    "cancelado",
    "nao autorizo",
    "nao execute",
    "pare",
}


def _matches(text: str, options: set[str]) -> bool:
    normalized = normalize_text(text)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in options:
        return True
    first = normalized.split(" ", 1)[0]
    return first in options


class VoiceService:
    """Orquestra microfone, transcrição, agente e fala.

    O microfone nunca é aberto sem uma chamada explícita a ``start`` ou
    ``listen_once``. O estado é publicado em ``voice.listening`` /
    ``voice.stopped`` para a interface exibir o indicador.
    """

    def __init__(
        self,
        *,
        assistant: AssistantService,
        settings: SettingsService,
        event_bus: EventBus,
        state: StateManager,
        tts: TTSService,
    ) -> None:
        self.assistant = assistant
        self.settings = settings
        self.event_bus = event_bus
        self.state = state
        self.tts = tts
        self._loop: asyncio.AbstractEventLoop | None = None
        self._busy = False
        self._wake_mode_active = False
        self._restart_after_command = False
        self._processing_lock = asyncio.Lock()
        self.recognizer = SpeechRecognizer(
            settings,
            event_bus,
            state,
            on_command=self._on_command_threadsafe,
            on_error=self._on_error_threadsafe,
        )

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ------------------------------------------------------------------
    # Controle
    # ------------------------------------------------------------------
    async def start(self, *, continuous: bool | None = None) -> dict[str, Any]:
        """Ativa a escuta por palavra-chave."""
        current = self.settings.get()
        if not current.wake_word_enabled:
            raise STTError("A palavra-chave está desativada nas configurações")
        continuous = current.continuous_listening if continuous is None else bool(continuous)
        if continuous != current.continuous_listening:
            self.settings.update({"continuous_listening": continuous})
        self._wake_mode_active = True
        self._restart_after_command = continuous
        self.recognizer.start_continuous()
        await self.event_bus.publish(
            "voice.started",
            {
                "continuous": continuous,
                "wake_word": current.wake_word,
                "engine": current.stt_engine,
            },
        )
        return self.status()

    async def stop(self) -> dict[str, Any]:
        """Encerra a escuta e libera o microfone."""
        self._wake_mode_active = False
        self._restart_after_command = False
        await asyncio.to_thread(self.recognizer.stop)
        await self.state.update(listening=False, detail="Microfone desativado")
        return self.status()

    async def listen_once(self) -> dict[str, Any]:
        """Push-to-talk: captura um comando único sem palavra-chave."""
        if self.recognizer.active:
            await self.stop()
        try:
            outcome = await asyncio.to_thread(
                self.recognizer.listen_once,
                require_wake_word=False,
                dispatch=False,
            )
        except STTError:
            raise
        except Exception as exc:  # pragma: no cover - falha de dispositivo
            logger.exception("Falha inesperada na captura de voz")
            raise STTError(f"Falha na captura de voz: {exc}") from exc
        response = await self._handle_command(outcome.command, outcome)
        return {"recognized": outcome.text, "response": response}

    async def speak(self, text: str) -> None:
        await self.tts.speak(text)

    async def stop_speaking(self) -> None:
        await self.tts.stop()

    def status(self) -> dict[str, Any]:
        settings = self.settings.get()
        return {
            **self.recognizer.status(),
            "busy": self._busy,
            "wake_mode_active": self._wake_mode_active,
            "voice_confirm_actions": settings.voice_confirm_actions,
        }

    def microphones(self) -> list[dict[str, Any]]:
        return [
            {
                "index": info.index,
                "name": info.name,
                "channels": info.channels,
                "sample_rate": info.sample_rate,
            }
            for info in list_microphones()
        ]

    # ------------------------------------------------------------------
    # Callbacks das threads
    # ------------------------------------------------------------------
    def _on_command_threadsafe(self, outcome: RecognitionOutcome) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.warning("Comando de voz recebido sem loop ativo; descartado")
            return
        asyncio.run_coroutine_threadsafe(
            self._handle_command(outcome.command, outcome), loop
        )

    def _on_error_threadsafe(self, message: str) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            self.event_bus.publish("voice.error", {"message": message}), loop
        )

    # ------------------------------------------------------------------
    # Processamento
    # ------------------------------------------------------------------
    async def _handle_command(
        self, text: str, outcome: RecognitionOutcome | None = None
    ) -> dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        if self._busy:
            await self.event_bus.publish(
                "voice.busy",
                {"message": "Ainda estou processando o comando anterior. Aguarde a resposta."},
            )
            return None
        async with self._processing_lock:
            if self._busy:
                return None
            self._busy = True
            try:
                return await self._process(text, outcome)
            finally:
                self._busy = False

    async def _process(
        self, text: str, outcome: RecognitionOutcome | None
    ) -> dict[str, Any] | None:
        settings = self.settings.get()
        await self.event_bus.publish(
            "voice.command",
            {
                "text": text,
                "wake_word_detected": bool(outcome.wake_word_detected) if outcome else False,
                "engine": outcome.engine if outcome else settings.stt_engine,
            },
        )
        should_restart = self._wake_mode_active and self._restart_after_command
        if self._wake_mode_active:
            # Evita que o microfone capte a própria voz do JARVIS.
            await asyncio.to_thread(self.recognizer.stop)
        try:
            if settings.voice_confirm_actions:
                handled = await self._try_voice_confirmation(text)
                if handled is not None:
                    return handled
            response = await self.assistant.chat(
                text,
                source="voice",
                speak=False,
            )
            final_text = ""
            assistant_message = response.get("assistant_message") or {}
            if isinstance(assistant_message, dict):
                final_text = str(assistant_message.get("content") or "")
            if final_text and settings.auto_speak_voice:
                await self.tts.speak(final_text)
                await self.tts.wait_until_done()
        finally:
            if should_restart and self._wake_mode_active:
                self.recognizer.start_continuous()
        return response

    async def _try_voice_confirmation(self, text: str) -> dict[str, Any] | None:
        conversation_id = self.assistant.active_conversation_id
        if not conversation_id:
            return None
        pending = self.assistant.actions.pending(conversation_id)
        if len(pending) != 1:
            return None
        normalized = normalize_text(text)
        if _matches(normalized, _AFFIRMATIVE):
            approve = True
        elif _matches(normalized, _NEGATIVE):
            approve = False
        else:
            return None
        await self.event_bus.publish(
            "voice.confirmation",
            {"action_id": pending[0].id, "approve": approve, "text": text},
        )
        response = await self.assistant.approve_action(
            pending[0].id, approve=approve, speak=False
        )
        final_text = ""
        assistant_message = response.get("assistant_message") or {}
        if isinstance(assistant_message, dict):
            final_text = str(assistant_message.get("content") or "")
        if final_text and self.settings.get().auto_speak_voice:
            await self.tts.speak(final_text)
            await self.tts.wait_until_done()
        return response
