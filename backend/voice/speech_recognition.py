"""Reconhecimento de fala em português brasileiro.

O microfone só é aberto quando ``start``/``listen_once`` é chamado. Todo o
processamento acontece em uma thread dedicada e o estado ``listening`` é
publicado antes de o dispositivo ser aberto, garantindo que a interface sempre
mostre quando a captura está ativa.

Motores suportados:

* ``google`` — Google Web Speech, requer internet, sem chave de API.
* ``whisper`` — faster-whisper local (opcional, mais preciso e offline).
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.events import EventBus, StateManager
from backend.core.settings_service import SettingsService
from backend.voice.wake_word import find_wake_word, strip_wake_word

logger = logging.getLogger(__name__)


class STTError(RuntimeError):
    """Erro base de reconhecimento de fala."""


class STTUnavailableError(STTError):
    """Microfone ou dependência de reconhecimento indisponível."""


class STTRecognitionError(STTError):
    """Fala não reconhecida ou serviço de reconhecimento falhou."""


@dataclass(slots=True)
class RecognitionOutcome:
    text: str
    command: str
    engine: str
    wake_word_detected: bool = False
    duration_seconds: float = 0.0
    microphone: str = ""


@dataclass(slots=True)
class MicrophoneInfo:
    index: int
    name: str
    channels: int
    sample_rate: int


@dataclass(slots=True)
class _AudioCapture:
    audio: Any
    duration: float
    microphone: str = ""


CommandCallback = Callable[[RecognitionOutcome], None]
ErrorCallback = Callable[[str], None]


def list_microphones() -> list[MicrophoneInfo]:
    """Lista microfones disponíveis sem abrir um fluxo de captura."""
    try:
        import speech_recognition as sr
    except ImportError as exc:  # pragma: no cover - dependência declarada
        raise STTUnavailableError(
            "SpeechRecognition não está instalado. Execute pip install -r requirements.txt"
        ) from exc
    microphones: list[MicrophoneInfo] = []
    try:
        names = sr.Microphone.list_microphone_names()
    except Exception as exc:  # PyAudio pode falhar sem dispositivo
        raise STTUnavailableError(f"Não foi possível enumerar microfones: {exc}") from exc
    for index, name in enumerate(names):
        channels, sample_rate = 1, 16000
        try:
            with sr.Microphone(device_index=index) as source:
                channels = source.channels
                sample_rate = source.SAMPLE_RATE
        except Exception:
            pass
        microphones.append(
            MicrophoneInfo(
                index=index,
                name=str(name),
                channels=int(channels),
                sample_rate=int(sample_rate),
            )
        )
    return microphones


class SpeechRecognizer:
    """Captura e transcrição de fala com palavra-chave opcional."""

    def __init__(
        self,
        settings: SettingsService,
        event_bus: EventBus,
        state: StateManager,
        *,
        on_command: CommandCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.state = state
        self.on_command = on_command
        self.on_error = on_error

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._active = False
        self._whisper_models: dict[str, Any] = {}
        self._recognizer: Any = None
        self._mic_name = ""

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self._active

    def status(self) -> dict[str, Any]:
        settings = self.settings.get()
        return {
            "active": self._active,
            "engine": settings.stt_engine,
            "language": settings.voice_language,
            "wake_word_enabled": settings.wake_word_enabled,
            "wake_word": settings.wake_word,
            "continuous_listening": settings.continuous_listening,
            "microphone": self._mic_name,
            "input_device_index": settings.input_device_index,
        }

    # ------------------------------------------------------------------
    # Captura
    # ------------------------------------------------------------------
    def _recognizer_instance(self) -> Any:
        try:
            import speech_recognition as sr
        except ImportError as exc:  # pragma: no cover - dependência declarada
            raise STTUnavailableError(
                "SpeechRecognition não está instalado. Execute pip install -r requirements.txt"
            ) from exc
        with self._lock:
            if self._recognizer is None:
                recognizer = sr.Recognizer()
                recognizer.dynamic_energy_threshold = True
                recognizer.dynamic_energy_ratio = 1.5
                recognizer.pause_threshold = 0.8
                recognizer.operation_timeout = 30
                self._recognizer = recognizer
            return self._recognizer

    def _microphone(self, settings: Any) -> Any:
        import speech_recognition as sr

        try:
            microphone = sr.Microphone(device_index=settings.input_device_index)
        except Exception as exc:
            raise STTUnavailableError(
                f"Microfone indisponível (índice {settings.input_device_index}): {exc}. "
                "Confira se há um microfone conectado e permitido nas configurações de privacidade do Windows."
            ) from exc
        try:
            names = sr.Microphone.list_microphone_names()
            index = settings.input_device_index
            if index is None:
                index = microphone.device_index
            if index is not None and 0 <= int(index) < len(names):
                self._mic_name = str(names[int(index)])
        except Exception:
            pass
        return microphone

    def _capture(
        self,
        *,
        timeout: float,
        phrase_limit: float,
        calibrate: bool = False,
    ) -> _AudioCapture | None:
        """Bloqueia até capturar uma frase. Retorna None em timeout."""
        import speech_recognition as sr

        settings = self.settings.get()
        recognizer = self._recognizer_instance()
        with self._microphone(settings) as source:
            if calibrate:
                try:
                    recognizer.adjust_for_ambient_noise(source, duration=0.6)
                except Exception:
                    logger.debug("Não foi possível calibrar o ruído ambiente", exc_info=True)
            started = time.monotonic()
            try:
                audio = recognizer.listen(
                    source,
                    timeout=max(0.5, timeout),
                    phrase_time_limit=max(1.0, phrase_limit),
                )
            except sr.WaitTimeoutError:
                return None
            duration = time.monotonic() - started
        return _AudioCapture(audio=audio, duration=duration, microphone=self._mic_name)

    # ------------------------------------------------------------------
    # Transcrição
    # ------------------------------------------------------------------
    def _recognize(self, audio: Any, settings: Any) -> str:
        engine = settings.stt_engine
        if engine == "whisper":
            return self._recognize_whisper(audio, settings)
        return self._recognize_google(audio, settings)

    def _recognize_google(self, audio: Any, settings: Any) -> str:
        import speech_recognition as sr

        recognizer = self._recognizer_instance()
        try:
            return recognizer.recognize_google(audio, language=settings.voice_language).strip()
        except sr.UnknownValueError as exc:
            raise STTRecognitionError("Não consegui entender a fala. Tente novamente mais perto do microfone.") from exc
        except sr.RequestError as exc:
            raise STTRecognitionError(
                f"O serviço de reconhecimento não respondeu: {exc}. Verifique a conexão com a internet "
                "ou use o motor Whisper local."
            ) from exc
        except Exception as exc:  # pragma: no cover - falha inesperada do backend
            raise STTRecognitionError(f"Falha no reconhecimento Google: {exc}") from exc

    def _whisper_model(self, name: str) -> Any:
        with self._lock:
            model = self._whisper_models.get(name)
            if model is not None:
                return model
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise STTUnavailableError(
                    "O motor Whisper requer o pacote opcional faster-whisper. "
                    "Instale com: pip install faster-whisper"
                ) from exc
            logger.info("Carregando modelo Whisper local '%s'", name)
            model = WhisperModel(name, device="cpu", compute_type="int8")
            self._whisper_models[name] = model
            return model

    def _recognize_whisper(self, audio: Any, settings: Any) -> str:
        model = self._whisper_model(settings.whisper_model)
        wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2)
        handle, path = tempfile.mkstemp(prefix="jarvis-stt-", suffix=".wav")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(wav_data)
            segments, _info = model.transcribe(
                path,
                language=settings.voice_language.split("-")[0],
                vad_filter=True,
                beam_size=5,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise STTRecognitionError(f"Falha no Whisper local: {exc}") from exc
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        if not text:
            raise STTRecognitionError("Não consegui entender a fala. Tente novamente.")
        return text

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def listen_once(
        self, *, require_wake_word: bool = False, dispatch: bool = True
    ) -> RecognitionOutcome:
        """Escuta um único comando (push-to-talk). Bloqueante — use em thread."""
        settings = self.settings.get()
        self._begin_listening()
        try:
            capture = self._capture(
                timeout=settings.stt_timeout_seconds,
                phrase_limit=settings.stt_phrase_limit_seconds,
                calibrate=True,
            )
            if capture is None:
                raise STTRecognitionError("Nenhuma fala detectada. O microfone continua disponível para uma nova tentativa.")
            text = self._recognize(capture.audio, settings)
            detected = find_wake_word(text, settings.wake_word) is not None
            if require_wake_word and not detected:
                raise STTRecognitionError(
                    f"Diga “{settings.wake_word}” seguido do comando."
                )
            command = strip_wake_word(text, settings.wake_word) if detected else text
            if not command.strip():
                raise STTRecognitionError("A palavra-chave foi detectada, mas nenhum comando foi dito.")
            outcome = RecognitionOutcome(
                text=text,
                command=command.strip(),
                engine=settings.stt_engine,
                wake_word_detected=detected,
                duration_seconds=round(capture.duration, 2),
                microphone=capture.microphone,
            )
            self._publish_result(outcome, dispatch=dispatch)
            return outcome
        finally:
            self._end_listening()

    def start_continuous(self) -> None:
        """Inicia escuta contínua por palavra-chave em thread dedicada."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._continuous_worker, name="jarvis-stt", daemon=True
            )
            self._thread.start()
        logger.info("Escuta contínua iniciada")

    def stop(self) -> None:
        """Solicita o encerramento da escuta contínua e libera o microfone."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5)
        if thread is None or not thread.is_alive():
            with self._lock:
                self._thread = None
        if self._active:
            self._end_listening()
        logger.info("Escuta contínua encerrada")

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------
    def _continuous_worker(self) -> None:
        import speech_recognition as sr

        settings = self.settings.get()
        self._begin_listening()
        waiting_followup_until: float | None = None
        calibrated = False
        try:
            while not self._stop_event.is_set():
                settings = self.settings.get()
                try:
                    followup = waiting_followup_until is not None
                    timeout = (
                        max(1.0, waiting_followup_until - time.monotonic())
                        if followup
                        else 1.0
                    )
                    capture = self._capture(
                        timeout=timeout,
                        phrase_limit=settings.stt_phrase_limit_seconds,
                        calibrate=not calibrated,
                    )
                    calibrated = True
                    if capture is None:
                        if followup:
                            waiting_followup_until = None
                            self._publish_info(
                                "Tempo para o comando esgotado; diga a palavra-chave novamente."
                            )
                        continue
                    text = self._recognize(capture.audio, settings)
                    if not text:
                        continue
                    detected = find_wake_word(text, settings.wake_word) is not None
                    command = (
                        strip_wake_word(text, settings.wake_word) if detected else text
                    ).strip()
                    if (
                        settings.wake_word_enabled
                        and not detected
                        and not followup
                        and settings.wake_word_required
                    ):
                        self._publish_info(
                            f"Ouvi “{text}”, mas aguardei a palavra-chave “{settings.wake_word}”."
                        )
                        continue
                    if not command:
                        waiting_followup_until = time.monotonic() + settings.voice_command_timeout
                        self._publish_info("Palavra-chave detectada. Pode falar o comando.")
                        continue
                    waiting_followup_until = None
                    outcome = RecognitionOutcome(
                        text=text,
                        command=command,
                        engine=settings.stt_engine,
                        wake_word_detected=detected,
                        duration_seconds=round(capture.duration, 2),
                        microphone=capture.microphone,
                    )
                    self._publish_result(outcome)
                    if not settings.continuous_listening:
                        break
                except STTRecognitionError as exc:
                    self._publish_error(str(exc))
                    if waiting_followup_until is not None:
                        waiting_followup_until = None
                    time.sleep(0.4)
                except STTUnavailableError as exc:
                    self._publish_error(str(exc))
                    break
                except sr.WaitTimeoutError:
                    continue
                except Exception as exc:  # pragma: no cover - robustez da thread
                    logger.exception("Falha inesperada na escuta contínua")
                    self._publish_error(f"Falha na escuta: {exc}")
                    time.sleep(0.8)
        finally:
            self._end_listening()
            with self._lock:
                self._thread = None
            self._publish_info("Escuta encerrada.")
            logger.info("Thread de escuta finalizada")

    def _begin_listening(self) -> None:
        if self._active:
            return
        self._active = True
        self.state.update_threadsafe(listening=True, detail="Ouvindo…", error=None)
        self.event_bus.publish_threadsafe("voice.listening", self.status())

    def _end_listening(self) -> None:
        self._active = False
        self.state.update_threadsafe(listening=False, detail="Pronto")
        self.event_bus.publish_threadsafe("voice.stopped", self.status())

    def _publish_result(self, outcome: RecognitionOutcome, *, dispatch: bool = True) -> None:
        payload = {
            "text": outcome.text,
            "command": outcome.command,
            "engine": outcome.engine,
            "wake_word_detected": outcome.wake_word_detected,
            "duration_seconds": outcome.duration_seconds,
            "microphone": outcome.microphone,
        }
        self.event_bus.publish_threadsafe("voice.recognized", payload)
        if dispatch and self.on_command is not None:
            try:
                self.on_command(outcome)
            except Exception:
                logger.exception("Falha ao encaminhar o comando reconhecido")

    def _publish_error(self, message: str) -> None:
        self.event_bus.publish_threadsafe("voice.error", {"message": message})
        self.state.update_threadsafe(error=message, detail=message)
        if self.on_error is not None:
            try:
                self.on_error(message)
            except Exception:
                logger.exception("Falha ao encaminhar o erro de voz")
