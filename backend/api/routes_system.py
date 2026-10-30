"""Rotas de status, configurações, provedores e voz."""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend import __version__
from backend.api.deps import get_container
from backend.api.schemas import (
    ProviderKeyRequest,
    SettingsUpdateRequest,
    SpeakRequest,
    VoiceStartRequest,
)
from backend.core.errors import JarvisError
from backend.security.secrets import SecretStoreError
from backend.tools.system import collect_resource_usage
from backend.voice.speech_recognition import STTError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sistema"])

_STARTED_AT = time.monotonic()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    container = get_container(request)
    return {
        "status": "ok",
        "app": container.app_settings.app_name,
        "version": __version__,
        "database": container.database.health(),
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    container = get_container(request)
    resources = await asyncio.to_thread(collect_resource_usage)
    settings = container.settings_service.get()
    return {
        "runtime": container.state.snapshot(),
        "resources": resources,
        "database": {"healthy": container.database.health(), "path": str(container.database.path)},
        "provider": {
            "id": settings.provider,
            "model": settings.model,
            "configured": any(
                item["configured"] for item in container.provider_factory.describe(settings)
                if item["current"]
            ),
        },
        "voice": container.voice.status(),
        "tools": len(container.registry.all()),
        "version": __version__,
    }


@router.get("/tools")
async def list_tools(request: Request) -> dict[str, Any]:
    container = get_container(request)
    return {"tools": container.registry.describe()}


@router.get("/providers")
async def list_providers(request: Request) -> dict[str, Any]:
    container = get_container(request)
    settings = container.settings_service.get()
    return {"providers": container.provider_factory.describe(settings)}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    if provider_id not in {"deepseek", "openai", "anthropic", "ollama", "custom"}:
        raise HTTPException(status_code=404, detail="Provedor desconhecido")
    try:
        result = await container.provider_factory.test_connection(provider_id)
    except JarvisError as exc:
        return {"ok": False, "message": exc.message, "models": []}
    return {
        "ok": result.reachable,
        "message": result.message,
        "models": result.models,
        "provider": result.provider,
    }


@router.get("/providers/{provider_id}/models")
async def provider_models(provider_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        models = await container.provider_factory.list_models(provider_id)
    except JarvisError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc
    return {"models": models}


@router.put("/providers/{provider_id}/key")
async def set_provider_key(
    provider_id: str, payload: ProviderKeyRequest, request: Request
) -> dict[str, Any]:
    container = get_container(request)
    try:
        container.secret_store.set(provider_id, payload.api_key)
    except SecretStoreError as exc:
        raise HTTPException(
            status_code=500, detail={"code": "secret_store_error", "message": str(exc)}
        ) from exc
    await container.event_bus.publish("providers.updated", {"provider": provider_id})
    return {"ok": True, "provider": provider_id}


@router.delete("/providers/{provider_id}/key")
async def delete_provider_key(provider_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        container.secret_store.delete(provider_id)
    except SecretStoreError as exc:
        raise HTTPException(
            status_code=500, detail={"code": "secret_store_error", "message": str(exc)}
        ) from exc
    await container.event_bus.publish("providers.updated", {"provider": provider_id})
    return {"ok": True, "provider": provider_id}


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    container = get_container(request)
    settings = container.settings_service.get()
    return {"settings": settings.model_dump()}


@router.put("/settings")
async def update_settings(payload: SettingsUpdateRequest, request: Request) -> dict[str, Any]:
    container = get_container(request)
    settings = container.settings_service.update(payload.values)
    await container.event_bus.publish("settings.updated", {"settings": settings.model_dump()})
    return {"settings": settings.model_dump()}


@router.post("/settings/reset")
async def reset_settings(request: Request) -> dict[str, Any]:
    container = get_container(request)
    settings = container.settings_service.reset()
    await container.event_bus.publish("settings.updated", {"settings": settings.model_dump()})
    return {"settings": settings.model_dump()}


# ----------------------------------------------------------------------
# Voz
# ----------------------------------------------------------------------
@router.get("/voice/status")
async def voice_status(request: Request) -> dict[str, Any]:
    return {"voice": get_container(request).voice.status()}


@router.get("/voice/microphones")
async def voice_microphones(request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        microphones = await asyncio.to_thread(container.voice.microphones)
    except STTError as exc:
        raise HTTPException(
            status_code=503, detail={"code": "stt_unavailable", "message": str(exc)}
        ) from exc
    return {"microphones": microphones}


@router.post("/voice/start")
async def voice_start(payload: VoiceStartRequest, request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        result = await container.voice.start(continuous=payload.continuous)
    except STTError as exc:
        raise HTTPException(
            status_code=503, detail={"code": "stt_unavailable", "message": str(exc)}
        ) from exc
    return {"voice": result}


@router.post("/voice/stop")
async def voice_stop(request: Request) -> dict[str, Any]:
    container = get_container(request)
    return {"voice": await container.voice.stop()}


@router.post("/voice/listen")
async def voice_listen(request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        result = await container.voice.listen_once()
    except STTError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "stt_error", "message": str(exc)}
        ) from exc
    return result


@router.post("/voice/speak")
async def voice_speak(payload: SpeakRequest, request: Request) -> dict[str, Any]:
    container = get_container(request)
    await container.voice.speak(payload.text)
    return {"ok": True}


@router.post("/voice/stop-speaking")
async def voice_stop_speaking(request: Request) -> dict[str, Any]:
    container = get_container(request)
    await container.voice.stop_speaking()
    return {"ok": True}
