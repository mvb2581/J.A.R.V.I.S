"""WebSocket de eventos em tempo real."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend import __version__

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket) -> None:
    container = getattr(websocket.app.state, "container", None)
    if container is None:  # pragma: no cover
        await websocket.close(code=1011)
        return
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "hello",
            "data": {
                "version": __version__,
                "runtime": container.state.snapshot(),
                "voice": container.voice.status(),
                "settings": container.settings_service.get().model_dump(),
            },
        }
    )

    async with container.event_bus.subscribe() as queue:
        async def sender() -> None:
            while True:
                event = await queue.get()
                await websocket.send_json(event)

        async def receiver() -> None:
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    continue
                kind = message.get("type")
                if kind == "ping":
                    await websocket.send_json(
                        {"type": "pong", "data": {"timestamp": message.get("data")}}
                    )
                elif kind == "cancel":
                    await container.assistant.cancel(message.get("conversation_id"))
                elif kind == "subscribe":
                    await websocket.send_json(
                        {"type": "runtime.state", "data": container.state.snapshot()}
                    )
                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "code": "unsupported_ws_message",
                                "message": f"Mensagem WebSocket não suportada: {kind}",
                            },
                        }
                    )

        sender_task = asyncio.create_task(sender(), name="ws-sender")
        receiver_task = asyncio.create_task(receiver(), name="ws-receiver")
        try:
            done, pending = await asyncio.wait(
                {sender_task, receiver_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                exception = task.exception()
                if exception and not isinstance(exception, WebSocketDisconnect):
                    logger.debug("Tarefa WebSocket encerrada: %s", exception)
        except WebSocketDisconnect:
            pass
        finally:
            for task in (sender_task, receiver_task):
                task.cancel()
            await asyncio.gather(sender_task, receiver_task, return_exceptions=True)
