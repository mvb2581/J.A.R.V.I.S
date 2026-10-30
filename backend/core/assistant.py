"""Orquestração de conversas, confirmações, cancelamento e fala."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from backend.ai.types import ToolCall
from backend.core.agent import Agent, AgentResult, action_to_dict, message_to_dict
from backend.core.errors import (
    JarvisError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from backend.core.events import EventBus, StateManager
from backend.core.planner import TaskPlanner
from backend.core.settings_service import SettingsService
from backend.core.utils import new_id, truncate
from backend.database.models import ConversationRecord, MessageRecord
from backend.database.repositories import (
    ActionRepository,
    ConversationRepository,
    MessageRepository,
)
from backend.tools.base import ToolResult
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class RunManager:
    """Permite cancelar a execução corrente de uma conversa."""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def start(self, conversation_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._events[conversation_id] = event
        return event

    def cancel(self, conversation_id: str) -> bool:
        event = self._events.get(conversation_id)
        if event is None:
            return False
        event.set()
        return True

    def finish(self, conversation_id: str, event: asyncio.Event) -> None:
        if self._events.get(conversation_id) is event:
            self._events.pop(conversation_id, None)


class AssistantService:
    def __init__(
        self,
        *,
        agent: Agent,
        conversations: ConversationRepository,
        messages: MessageRepository,
        actions: ActionRepository,
        settings: SettingsService,
        planner: TaskPlanner,
        registry: ToolRegistry,
        event_bus: EventBus,
        state: StateManager,
        tts: Any = None,
    ) -> None:
        self.agent = agent
        self.conversations = conversations
        self.messages = messages
        self.actions = actions
        self.settings = settings
        self.planner = planner
        self.registry = registry
        self.event_bus = event_bus
        self.state = state
        self.tts = tts
        self.runs = RunManager()
        self._locks: dict[str, asyncio.Lock] = {}
        self._active_conversation_id: str | None = None

    @property
    def active_conversation_id(self) -> str | None:
        return self._active_conversation_id

    @asynccontextmanager
    async def _lock(self, conversation_id: str):
        lock = self._locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            yield

    async def chat(
        self,
        text: str,
        *,
        conversation_id: str | None = None,
        source: str = "text",
        speak: bool | None = None,
    ) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValidationError("A mensagem não pode ser vazia")
        if len(text) > 8000:
            raise ValidationError("A mensagem excede o limite de 8000 caracteres")
        if source not in {"text", "voice"}:
            source = "text"
        conversation = (
            self.conversations.get(conversation_id) if conversation_id else None
        )
        if conversation is None:
            conversation = self.conversations.create()
        conversation_id = conversation.id
        async with self._lock(conversation_id):
            conversation = self.conversations.get(conversation_id)
            if conversation is None:
                raise NotFoundError("Conversa não encontrada")
            pending = self.actions.pending(conversation_id)
            if pending:
                raise ValidationError(
                    "Há uma confirmação pendente nesta conversa. Aprove ou recuse a ação antes de enviar outra mensagem."
                )
            if self.messages.count(conversation_id) == 0 and conversation.title == "Nova conversa":
                title = truncate(text.replace("\n", " "), 60)
                self.conversations.update_title(conversation_id, title or "Nova conversa")
            user_message = self.messages.add(conversation_id, "user", text, metadata={"source": source})
            await self.event_bus.publish(
                "message.created",
                {"conversation_id": conversation_id, "message": message_to_dict(user_message)},
            )
            await self.event_bus.publish(
                "conversation.updated",
                {"conversation": conversation_to_dict(self.conversations.get(conversation_id))},
            )
            self._active_conversation_id = conversation_id
            run_event = self.runs.start(conversation_id)
            await self.state.update(
                thinking=True,
                executing=False,
                speaking=False,
                error=None,
                detail="Processando sua mensagem…",
                active_conversation_id=conversation_id,
                active_tool=None,
            )
            try:
                result = await self.agent.run(
                    conversation_id, voice_mode=source == "voice", cancel_event=run_event
                )
            except JarvisError as exc:
                await self.state.update(
                    thinking=False,
                    executing=False,
                    error=exc.message,
                    detail=exc.message,
                )
                await self.event_bus.publish("assistant.error", exc.to_dict())
                raise
            except Exception as exc:
                logger.exception("Erro inesperado ao processar mensagem")
                await self.state.update(
                    thinking=False, executing=False, error=str(exc), detail="Erro interno"
                )
                await self.event_bus.publish(
                    "assistant.error",
                    {"code": "internal_error", "message": f"Erro interno: {exc}"},
                )
                raise JarvisError("Erro interno ao processar a mensagem") from exc
            finally:
                self.runs.finish(conversation_id, run_event)
            await self.state.update(
                thinking=False,
                executing=False,
                speaking=False,
                active_tool=None,
                detail="Pronto",
            )
            should_speak = (
                speak
                if speak is not None
                else (
                    self.settings.get().auto_speak_voice
                    if source == "voice"
                    else self.settings.get().auto_speak_text
                )
            )
            if should_speak and result.final_text:
                await self._speak(result.final_text)
            return self._response(conversation_id, user_message, result)

    async def approve_action(
        self,
        action_id: str,
        *,
        approve: bool,
        speak: bool | None = None,
    ) -> dict[str, Any]:
        action = self.actions.get(action_id)
        if action is None:
            raise NotFoundError("Ação não encontrada")
        if not action.conversation_id:
            raise ValidationError("A ação não está vinculada a uma conversa")
        conversation_id = action.conversation_id
        async with self._lock(conversation_id):
            action = self.actions.get(action_id)
            if action is None:
                raise NotFoundError("Ação não encontrada")
            if action.status != "pending":
                raise ValidationError(f"A ação não está pendente (status: {action.status})")
            settings = self.settings.get()
            if action.permission_level >= 3 and not settings.allow_level3:
                raise PermissionDeniedError("Ações críticas estão desativadas nas configurações")
            self._active_conversation_id = conversation_id
            run_event = self.runs.start(conversation_id)
            tool = self.registry.get(action.tool_name)
            call = ToolCall(
                id=action.tool_call_id or new_id("call"),
                name=action.tool_name,
                arguments=action.arguments,
                raw_arguments=json.dumps(action.arguments, ensure_ascii=False),
            )
            if approve:
                await self.state.update(
                    thinking=False,
                    executing=True,
                    active_tool=action.tool_name,
                    detail=action.summary,
                    active_conversation_id=conversation_id,
                )
                self.actions.update(action.id, status="executing")
                action = self.actions.get(action.id) or action
                await self.event_bus.publish(
                    "tool.started",
                    {"conversation_id": conversation_id, "action": action_to_dict(action)},
                )
                if tool is None:
                    result = ToolResult.fail(f"Ferramenta indisponível: {action.tool_name}")
                else:
                    try:
                        tool.validate_arguments(action.arguments)
                    except Exception as exc:
                        result = ToolResult.fail(f"Argumentos inválidos: {exc}")
                    else:
                        result = await self.agent._execute_tool(
                            tool, action.arguments, settings, conversation_id
                        )
                status = "executed" if result.success else "failed"
                action = self.actions.update(
                    action.id,
                    status=status,
                    result=result.to_dict(),
                    error=result.error,
                ) or action
            else:
                result = ToolResult.fail("O usuário negou a execução desta ação.")
                action = self.actions.update(
                    action.id,
                    status="denied",
                    result=result.to_dict(),
                    error="Negada pelo usuário",
                ) or action
            await self.event_bus.publish(
                "tool.finished",
                {
                    "conversation_id": conversation_id,
                    "action": action_to_dict(action),
                    "result": result.to_dict(),
                },
            )
            tool_message = await self.agent._save_tool_result(
                conversation_id, call, result, settings
            )
            try:
                agent_result = await self.agent.resume(
                    conversation_id, voice_mode=False, cancel_event=run_event
                )
            except JarvisError as exc:
                await self.state.update(
                    thinking=False, executing=False, error=exc.message, detail=exc.message
                )
                await self.event_bus.publish("assistant.error", exc.to_dict())
                raise
            finally:
                self.runs.finish(conversation_id, run_event)
            await self.state.update(
                thinking=False,
                executing=False,
                speaking=False,
                active_tool=None,
                detail="Pronto",
            )
            should_speak = speak if speak is not None else self.settings.get().auto_speak_text
            if should_speak and agent_result.final_text:
                await self._speak(agent_result.final_text)
            agent_result.messages.insert(0, tool_message)
            response = self._response(conversation_id, None, agent_result)
            response["action"] = action_to_dict(action)
            return response

    async def cancel(self, conversation_id: str | None = None) -> dict[str, Any]:
        target = conversation_id or self._active_conversation_id
        cancelled = self.runs.cancel(target) if target else False
        await self._stop_speaking()
        await self.state.update(
            listening=False,
            thinking=False,
            executing=False,
            speaking=False,
            active_tool=None,
            detail="Interrompido",
        )
        return {"cancelled": cancelled, "conversation_id": target}

    async def _speak(self, text: str) -> None:
        if self.tts is None:
            return
        try:
            await self.tts.speak(text)
        except Exception:
            logger.exception("Falha ao sintetizar a resposta em voz")

    async def _stop_speaking(self) -> None:
        if self.tts is None:
            return
        try:
            await self.tts.stop()
        except Exception:
            logger.exception("Falha ao interromper a fala")

    def pending_actions(self, conversation_id: str | None = None) -> list[dict[str, Any]]:
        return [action_to_dict(action) for action in self.actions.pending(conversation_id)]

    def _response(
        self,
        conversation_id: str,
        user_message: MessageRecord | None,
        result: AgentResult,
    ) -> dict[str, Any]:
        conversation = self.conversations.get(conversation_id)
        assistant_messages = [
            message for message in result.messages if message.role == "assistant"
        ]
        assistant_message = assistant_messages[-1] if assistant_messages else None
        return {
            "conversation_id": conversation_id,
            "conversation": conversation_to_dict(conversation) if conversation else None,
            "user_message": message_to_dict(user_message) if user_message else None,
            "messages": [message_to_dict(message) for message in result.messages],
            "assistant_message": (
                message_to_dict(assistant_message) if assistant_message else None
            ),
            "pending_actions": [action_to_dict(action) for action in result.pending_actions],
            "plan": self.planner.get_plan(conversation_id),
            "cancelled": result.cancelled,
            "steps": result.steps,
            "usage": result.usage,
        }


def conversation_to_dict(conversation: ConversationRecord | None) -> dict[str, Any] | None:
    if conversation is None:
        return None
    data = asdict(conversation)
    return data
