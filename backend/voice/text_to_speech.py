"""Síntese de voz com SAPI5 (pyttsx3) e Edge TTS opcional, em thread própria."""

from __future__ import annotations

import asyncio
import logging
import queue
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.events import EventBus, StateManager
from backend.core.settings_service import SettingsService

logger = logging.getLogger(__name__)

EDGE_VOICES_PT = [
    {"id": "pt-BR-FranciscaNeural", "name": "Francisca (Edge, feminina)"},
    {"id": "pt-BR-AntonioNeural", "name": "Antônio (Edge, masculina)"},
    {"id": "pt-BR-ThalitaNeural", "name": "Thalita (Edge, feminina)"},
    {"id": "pt-BR-BrendaNeural", "name": "Brenda (Edge, feminina)"},
    {"id": "pt-BR-DonatoNeural", "name": "Donato (Edge, masculina)"},
]


def clean_text_for_speech(text: str, limit: int = 6000) -> str:
    value = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"https?://\S+", "link", value)
    value = re.sub(r"[*_#>~|]", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = value.strip()
    return value[:limit]


def _chunks(text: str, size: int = 450) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= size:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence[:size]
    if current:
        chunks.append(current)
    return chunks


class TTSService:
    def __init__(
        self,
        settings: SettingsService,
        event_bus: EventBus,
        state: StateManager,
        data_dir: Path,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.state = state
        self.data_dir = data_dir
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=10)
        self._stop_event = threading.Event()
        self._shutdown = threading.Event()
        self._engine_lock = threading.RLock()
        self._engine: Any = None
        self._thread = threading.Thread(target=self._worker, name="jarvis-tts", daemon=True)
        self._thread.start()

    async def speak(self, text: str) -> None:
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            return
        self._stop_event.clear()
        try:
            self._queue.put_nowait(cleaned)
        except queue.Full:
            self._drain_queue()
            self._queue.put_nowait(cleaned)

    async def stop(self) -> None:
        self._stop_event.set()
        self._drain_queue()
        with self._engine_lock:
            if self._engine is not None:
                try:
                    self._engine.stop()
                except Exception:
                    logger.debug("Falha ao interromper pyttsx3", exc_info=True)
        try:
            import pygame

            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        await self.state.update(speaking=False, detail="Fala interrompida")

    async def wait_until_done(self, timeout: float = 180.0) -> None:
        """Aguarda a fila e a fala atual terminarem (usado para não ouvir a si mesmo)."""
        deadline = time.monotonic() + timeout
        await asyncio.sleep(0.25)
        while time.monotonic() < deadline:
            if not self.state.state.speaking and self._queue.empty():
                return
            await asyncio.sleep(0.15)

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _worker(self) -> None:
        while not self._shutdown.is_set():
            try:
                text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if text is None:
                break
            if self._stop_event.is_set():
                continue
            try:
                self.state.update_threadsafe(speaking=True, detail="Falando…", error=None)
                self.event_bus.publish_threadsafe("tts.started", {"characters": len(text)})
                settings = self.settings.get()
                if settings.tts_engine == "edge":
                    self._speak_edge(text, settings)
                else:
                    self._speak_sapi(text, settings)
            except Exception as exc:
                logger.exception("Falha na síntese de voz")
                self.event_bus.publish_threadsafe(
                    "voice.error", {"message": f"Falha na síntese de voz: {exc}"}
                )
            finally:
                if self._queue.empty() and not self._stop_event.is_set():
                    self.state.update_threadsafe(speaking=False, detail="Pronto")
                    self.event_bus.publish_threadsafe("tts.finished", {})

    def _speak_sapi(self, text: str, settings: Any) -> None:
        import pyttsx3

        with self._engine_lock:
            if self._engine is None:
                self._engine = pyttsx3.init()
            engine = self._engine
            try:
                engine.setProperty("rate", int(settings.tts_rate))
                engine.setProperty("volume", float(settings.tts_volume))
                self._select_sapi_voice(engine, settings.tts_voice)
            except Exception:
                logger.debug("Não foi possível ajustar voz/rate", exc_info=True)
            for chunk in _chunks(text):
                if self._stop_event.is_set():
                    break
                engine.say(chunk)
                engine.runAndWait()
            if self._stop_event.is_set():
                try:
                    engine.stop()
                except Exception:
                    pass

    def _select_sapi_voice(self, engine: Any, preferred: str) -> None:
        voices = engine.getProperty("voices") or []
        if preferred:
            for voice in voices:
                if preferred.lower() in (voice.id or "").lower() or preferred.lower() in (voice.name or "").lower():
                    engine.setProperty("voice", voice.id)
                    return
        for voice in voices:
            languages = " ".join(str(item) for item in (voice.languages or []))
            haystack = f"{voice.id} {voice.name} {languages}".lower()
            if any(token in haystack for token in ("pt-br", "portuguese", "brazil", "brasil")):
                engine.setProperty("voice", voice.id)
                return

    def _speak_edge(self, text: str, settings: Any) -> None:
        try:
            import edge_tts
            import pygame
        except ImportError as exc:
            raise RuntimeError(
                "Edge TTS requer os pacotes edge-tts e pygame. Instale requirements.txt."
            ) from exc
        voice = settings.tts_voice or "pt-BR-FranciscaNeural"
        if not voice.startswith("pt-"):
            voice = "pt-BR-FranciscaNeural"
        rate_percent = int(max(-50, min(50, (settings.tts_rate - 180) / 180 * 100)))
        volume_percent = int(max(-100, min(100, (settings.tts_volume - 1.0) * 100)))
        rate = f"{rate_percent:+d}%"
        volume = f"{volume_percent:+d}%"
        self.data_dir.joinpath("tts").mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix="jarvis-tts-", suffix=".mp3", dir=str(self.data_dir / "tts"), delete=False
        ) as handle:
            path = Path(handle.name)
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            asyncio.run(communicate.save(str(path)))
            if self._stop_event.is_set():
                return
            pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.1)
        finally:
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            path.unlink(missing_ok=True)

    def voices(self) -> list[dict[str, str]]:
        voices: list[dict[str, str]] = []
        try:
            import pyttsx3

            engine = pyttsx3.init()
            for voice in engine.getProperty("voices") or []:
                languages = ", ".join(str(item) for item in (voice.languages or []))
                voices.append(
                    {
                        "id": voice.id,
                        "name": f"{voice.name} ({languages})" if languages else voice.name,
                        "engine": "sapi",
                    }
                )
            engine.stop()
        except Exception:
            logger.debug("Não foi possível listar vozes SAPI", exc_info=True)
        voices.extend([{**voice, "engine": "edge"} for voice in EDGE_VOICES_PT])
        return voices

    def status(self) -> dict[str, Any]:
        return {
            "engines": ["sapi", "edge"],
            "voices": self.voices(),
            "queue_size": self._queue.qsize(),
        }

    def shutdown(self) -> None:
        self._shutdown.set()
        self._stop_event.set()
        self._drain_queue()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=3)
