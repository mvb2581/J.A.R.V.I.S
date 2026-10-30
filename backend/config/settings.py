"""Configurações de infraestrutura e preferências persistentes do JARVIS.

As variáveis de ambiente definem a infraestrutura e as chaves de API. As
preferências editáveis pela interface ficam em ``RuntimeSettings`` e são
persistidas no SQLite pelo ``SettingsService``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Raiz do projeto em desenvolvimento ou pasta temporária do PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def _default_data_dir() -> Path:
    """Dados do usuário: ``./data`` em dev e ``%LOCALAPPDATA%\\JARVIS`` no executável."""
    if not getattr(sys, "frozen", False):
        return PROJECT_ROOT / "data"
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "JARVIS"


def _env_files() -> tuple[Path, ...]:
    files = [PROJECT_ROOT / ".env", Path.cwd() / ".env"]
    if getattr(sys, "frozen", False):
        files.append(Path(sys.executable).resolve().parent / ".env")
    return tuple(files)


PROJECT_ROOT = _project_root()
DEFAULT_DATA_DIR = _default_data_dir()

ProviderId = Literal["deepseek", "openai", "anthropic", "ollama", "custom"]


def default_allowed_roots() -> list[str]:
    """Diretórios que o usuário normalmente quer controlar."""
    home = Path.home()
    candidates = [
        home,
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
    ]
    seen: set[str] = set()
    roots: list[str] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            roots.append(str(resolved))
    return roots


class AppSettings(BaseSettings):
    """Configuração imutável de inicialização (ambiente / .env)."""

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field("JARVIS", validation_alias="JARVIS_APP_NAME")
    host: str = Field("127.0.0.1", validation_alias="JARVIS_HOST")
    port: int = Field(8765, validation_alias="JARVIS_PORT")
    data_dir: Path = Field(DEFAULT_DATA_DIR, validation_alias="JARVIS_DATA_DIR")
    log_level: str = Field("INFO", validation_alias="JARVIS_LOG_LEVEL")

    default_provider: ProviderId = Field("deepseek", validation_alias="JARVIS_DEFAULT_PROVIDER")
    default_model: str = Field("deepseek-chat", validation_alias="JARVIS_DEFAULT_MODEL")

    deepseek_api_key: str = Field("", validation_alias="DEEPSEEK_API_KEY")
    openai_api_key: str = Field("", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field("", validation_alias="ANTHROPIC_API_KEY")
    custom_api_key: str = Field("", validation_alias="JARVIS_CUSTOM_API_KEY")

    deepseek_base_url: str = Field(
        "https://api.deepseek.com/v1", validation_alias="JARVIS_DEEPSEEK_BASE_URL"
    )
    openai_base_url: str = Field(
        "https://api.openai.com/v1", validation_alias="JARVIS_OPENAI_BASE_URL"
    )
    anthropic_base_url: str = Field(
        "https://api.anthropic.com/v1", validation_alias="JARVIS_ANTHROPIC_BASE_URL"
    )
    ollama_base_url: str = Field(
        "http://127.0.0.1:11434", validation_alias="JARVIS_OLLAMA_BASE_URL"
    )
    ollama_num_ctx: int = Field(
        8192, validation_alias="JARVIS_OLLAMA_NUM_CTX", ge=2048, le=32768
    )
    custom_base_url: str = Field("", validation_alias="JARVIS_CUSTOM_BASE_URL")

    request_timeout: float = Field(120.0, validation_alias="JARVIS_REQUEST_TIMEOUT")
    cors_origins: str = Field(
        "http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="JARVIS_CORS_ORIGINS",
    )

    voice_language: str = Field("pt-BR", validation_alias="JARVIS_VOICE_LANGUAGE")
    stt_engine: Literal["google", "whisper"] = Field("google", validation_alias="JARVIS_STT_ENGINE")
    tts_engine: Literal["sapi", "edge"] = Field("sapi", validation_alias="JARVIS_TTS_ENGINE")
    wake_word: str = Field("jarvis", validation_alias="JARVIS_WAKE_WORD")

    @field_validator("data_dir", mode="before")
    @classmethod
    def _resolve_data_dir(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @field_validator("request_timeout")
    @classmethod
    def _timeout_range(cls, value: float) -> float:
        if not 5 <= value <= 600:
            raise ValueError("JARVIS_REQUEST_TIMEOUT deve estar entre 5 e 600 segundos")
        return value

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jarvis.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def secrets_path(self) -> Path:
        return self.data_dir / "secrets.json"

    @property
    def frontend_dist(self) -> Path:
        return PROJECT_ROOT / "frontend" / "dist"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def env_api_keys(self) -> dict[str, str]:
        return {
            "deepseek": self.deepseek_api_key.strip(),
            "openai": self.openai_api_key.strip(),
            "anthropic": self.anthropic_api_key.strip(),
            "custom": self.custom_api_key.strip(),
            "ollama": "",
        }

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.logs_dir, self.screenshots_dir):
            path.mkdir(parents=True, exist_ok=True)


class RuntimeSettings(BaseModel):
    """Preferências editáveis em tempo de execução e persistidas no banco."""

    model_config = {"extra": "forbid"}

    provider: ProviderId = "deepseek"
    model: str = Field("deepseek-chat", min_length=1, max_length=120)
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=256, le=32768)
    max_agent_steps: int = Field(12, ge=1, le=30)
    context_messages: int = Field(24, ge=4, le=200)
    max_tool_result_chars: int = Field(12000, ge=2000, le=60000)

    # Permissões
    confirm_level2: bool = True
    allow_level3: bool = True
    allowed_roots: list[str] = Field(default_factory=default_allowed_roots)
    block_sensitive_files: bool = True
    terminal_enabled: bool = True
    terminal_timeout_seconds: int = Field(60, ge=5, le=600)
    max_terminal_output_chars: int = Field(20000, ge=1000, le=100000)

    # Voz
    voice_language: str = Field("pt-BR", min_length=2, max_length=20)
    stt_engine: Literal["google", "whisper"] = "google"
    whisper_model: str = Field("small", min_length=1, max_length=60)
    input_device_index: int | None = Field(None, ge=0)
    stt_timeout_seconds: float = Field(8.0, ge=2.0, le=60.0)
    stt_phrase_limit_seconds: float = Field(15.0, ge=3.0, le=60.0)
    wake_word_required: bool = True
    tts_engine: Literal["sapi", "edge"] = "sapi"
    tts_voice: str = Field("", max_length=200)
    tts_rate: int = Field(190, ge=80, le=400)
    tts_volume: float = Field(1.0, ge=0.0, le=1.0)
    auto_speak_voice: bool = True
    auto_speak_text: bool = False
    wake_word_enabled: bool = True
    wake_word: str = Field("jarvis", min_length=2, max_length=40)
    continuous_listening: bool = False
    voice_command_timeout: float = Field(8.0, ge=2.0, le=30.0)
    voice_confirm_actions: bool = False

    # Memória
    auto_memory_search: bool = True
    temporary_memory_ttl_hours: int = Field(24, ge=1, le=720)
    system_prompt_extra: str = Field("", max_length=4000)

    @field_validator("allowed_roots")
    @classmethod
    def _normalize_roots(cls, roots: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in roots:
            raw = raw.strip()
            if not raw:
                continue
            path = Path(os.path.expandvars(raw)).expanduser()
            try:
                path = path.resolve()
            except OSError:
                path = path.absolute()
            key = os.path.normcase(str(path))
            if key not in seen:
                seen.add(key)
                normalized.append(str(path))
        if not normalized:
            raise ValueError("Informe pelo menos um diretório autorizado")
        return normalized

    @field_validator("wake_word")
    @classmethod
    def _normalize_wake_word(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("A palavra-chave não pode ser vazia")
        return cleaned

    @model_validator(mode="after")
    def _provider_model(self) -> RuntimeSettings:
        if self.provider == "custom" and not self.model.strip():
            raise ValueError("Informe o modelo para o provedor personalizado")
        return self


def build_initial_runtime_settings(app: AppSettings) -> RuntimeSettings:
    """Combina os padrões do ambiente com preferências de voz iniciais."""
    return RuntimeSettings(
        provider=app.default_provider,
        model=app.default_model,
        voice_language=app.voice_language,
        stt_engine=app.stt_engine,
        tts_engine=app.tts_engine,
        wake_word=app.wake_word,
    )
