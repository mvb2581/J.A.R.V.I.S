"""Loop do agente: LLM → ferramentas → resultados → resposta final."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from backend.ai.factory import ProviderFactory
from backend.ai.types import ToolCall
from backend.config.settings import AppSettings, RuntimeSettings
from backend.core.errors import JarvisError, ProviderError
from backend.core.events import EventBus, StateManager
from backend.core.memory import MemoryManager
from backend.core.permissions import PermissionManager
from backend.core.planner import TaskPlanner
from backend.core.prompts import build_system_prompt
from backend.core.settings_service import SettingsService
from backend.core.utils import truncate
from backend.database.models import ActionRecord, MessageRecord
from backend.database.repositories import (
    ActionRepository,
    ConversationRepository,
    MessageRepository,
)
from backend.tools.base import BaseTool, ToolContext, ToolResult, ToolValidationError
from backend.tools.path_guard import PathGuard
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentResult:
    conversation_id: str
    messages: list[MessageRecord] = field(default_factory=list)
    pending_actions: list[ActionRecord] = field(default_factory=list)
    final_text: str = ""
    cancelled: bool = False
    steps: int = 0
    usage: dict[str, Any] = field(default_factory=dict)


def message_to_dict(message: MessageRecord) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "tool_calls": message.tool_calls,
        "tool_call_id": message.tool_call_id,
        "name": message.name,
        "metadata": message.metadata,
        "created_at": message.created_at,
    }


def action_to_dict(action: ActionRecord) -> dict[str, Any]:
    return {
        "id": action.id,
        "conversation_id": action.conversation_id,
        "tool_call_id": action.tool_call_id,
        "tool_name": action.tool_name,
        "arguments": action.arguments,
        "permission_level": action.permission_level,
        "status": action.status,
        "summary": action.summary,
        "result": action.result,
        "error": action.error,
        "created_at": action.created_at,
        "completed_at": action.completed_at,
    }


def _merge_usage(total: dict[str, Any], usage: dict[str, Any]) -> None:
    for key, value in (usage or {}).items():
        if isinstance(value, (int, float)) and isinstance(total.get(key, 0), (int, float)):
            total[key] = total.get(key, 0) + value
        else:
            total[key] = value


class Agent:
    def __init__(
        self,
        *,
        app_settings: AppSettings,
        settings: SettingsService,
        provider_factory: ProviderFactory,
        registry: ToolRegistry,
        permissions: PermissionManager,
        conversations: ConversationRepository,
        messages: MessageRepository,
        actions: ActionRepository,
        memory: MemoryManager,
        planner: TaskPlanner,
        event_bus: EventBus,
        state: StateManager,
    ) -> None:
        self.app_settings = app_settings
        self.settings = settings
        self.provider_factory = provider_factory
        self.registry = registry
        self.permissions = permissions
        self.conversations = conversations
        self.messages = messages
        self.actions = actions
        self.memory = memory
        self.planner = planner
        self.event_bus = event_bus
        self.state = state

    async def run(
        self,
        conversation_id: str,
        *,
        voice_mode: bool = False,
        cancel_event: asyncio.Event | None = None,
    ) -> AgentResult:
        return await self._run_loop(
            conversation_id, voice_mode=voice_mode, cancel_event=cancel_event
        )

    async def resume(
        self,
        conversation_id: str,
        *,
        voice_mode: bool = False,
        cancel_event: asyncio.Event | None = None,
    ) -> AgentResult:
        return await self._run_loop(
            conversation_id, voice_mode=voice_mode, cancel_event=cancel_event
        )

    async def _run_loop(
        self,
        conversation_id: str,
        *,
        voice_mode: bool,
        cancel_event: asyncio.Event | None,
    ) -> AgentResult:
        settings = self.settings.get()
        new_messages: list[MessageRecord] = []
        usage: dict[str, Any] = {}
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            raise ValueError("Conversa não encontrada")

        for step in range(1, settings.max_agent_steps + 1):
            if cancel_event is not None and cancel_event.is_set():
                return await self._cancelled(conversation_id, new_messages, step, usage)

            context = self._build_context(conversation_id, settings, voice_mode=voice_mode)
            await self.state.update(
                thinking=True,
                executing=False,
                speaking=False,
                error=None,
                detail="Pensando…",
                active_conversation_id=conversation_id,
                active_tool=None,
            )
            provider = self.provider_factory.create(settings)
            try:
                response = await provider.chat(
                    context,
                    self.registry.definitions(),
                    model=settings.model,
                    temperature=settings.temperature,
                    max_tokens=settings.max_tokens,
                )
            except JarvisError:
                raise
            except Exception as exc:  # protege o loop de falhas inesperadas do provedor
                logger.exception("Falha inesperada no provedor %s", settings.provider)
                raise ProviderError(f"Falha inesperada no provedor: {exc}") from exc
            _merge_usage(usage, response.usage)

            if cancel_event is not None and cancel_event.is_set():
                return await self._cancelled(conversation_id, new_messages, step, usage)

            if not response.tool_calls:
                text = response.content.strip() or "Não consegui gerar uma resposta para essa solicitação."
                assistant = await self._save_assistant(
                    conversation_id,
                    text,
                    metadata={
                        "provider": response.provider,
                        "model": response.model,
                        "usage": response.usage,
                    },
                )
                new_messages.append(assistant)
                return AgentResult(
                    conversation_id=conversation_id,
                    messages=new_messages,
                    final_text=text,
                    steps=step,
                    usage=usage,
                )

            for index, call in enumerate(response.tool_calls[:10]):
                if cancel_event is not None and cancel_event.is_set():
                    return await self._cancelled(conversation_id, new_messages, step, usage)
                tool = self.registry.get(call.name)
                validation_error: str | None = None
                if tool is not None and tool.enabled and not call.parse_error:
                    try:
                        normalized = tool.validate_arguments(call.arguments)
                    except ToolValidationError as exc:
                        validation_error = str(exc)
                    else:
                        call.arguments = normalized
                        call.raw_arguments = json.dumps(normalized, ensure_ascii=False)

                content = response.content if index == 0 else ""
                assistant = await self._save_assistant(
                    conversation_id,
                    content,
                    tool_calls=[call.to_openai()],
                    metadata={
                        "provider": response.provider,
                        "model": response.model,
                        "tool_call": call.name,
                    },
                )
                new_messages.append(assistant)

                if tool is None or not tool.enabled:
                    result = ToolResult.fail(f"Ferramenta desconhecida ou desativada: {call.name}")
                    new_messages.append(
                        await self._save_tool_result(conversation_id, call, result, settings)
                    )
                    continue
                if call.parse_error:
                    result = ToolResult.fail(call.parse_error)
                    new_messages.append(
                        await self._save_tool_result(conversation_id, call, result, settings)
                    )
                    continue
                if validation_error is not None:
                    result = ToolResult.fail(f"Argumentos inválidos: {validation_error}")
                    new_messages.append(
                        await self._save_tool_result(conversation_id, call, result, settings)
                    )
                    continue

                decision = self.permissions.evaluate(tool, call.arguments)
                summary = tool.summarize(call.arguments)
                if decision.blocked:
                    action = self.actions.create(
                        tool_name=tool.name,
                        arguments=call.arguments,
                        permission_level=decision.level,
                        summary=summary,
                        status="blocked",
                        conversation_id=conversation_id,
                        tool_call_id=call.id,
                    )
                    result = ToolResult.fail(decision.reason)
                    action = self.actions.update(
                        action.id, status="blocked", result=result.to_dict(), error=decision.reason
                    ) or action
                    new_messages.append(
                        await self._save_tool_result(conversation_id, call, result, settings)
                    )
                    await self.event_bus.publish(
                        "action.blocked",
                        {"conversation_id": conversation_id, "action": action_to_dict(action)},
                    )
                    continue

                if decision.requires_confirmation:
                    action = self.actions.create(
                        tool_name=tool.name,
                        arguments=call.arguments,
                        permission_level=decision.level,
                        summary=summary,
                        status="pending",
                        conversation_id=conversation_id,
                        tool_call_id=call.id,
                    )
                    confirmation_text = (
                        f"Preciso da sua confirmação para executar uma ação de nível {decision.level}.\n\n"
                        f"**{summary}**\n\n"
                        "Deseja aprovar? A ação só será executada depois da sua confirmação."
                    )
                    confirmation = await self._save_assistant(
                        conversation_id,
                        confirmation_text,
                        metadata={
                            "kind": "confirmation",
                            "pending_action_id": action.id,
                            "permission_level": decision.level,
                            "tool_name": tool.name,
                            "summary": summary,
                        },
                    )
                    new_messages.append(confirmation)
                    await self.event_bus.publish(
                        "confirmation.required",
                        {
                            "conversation_id": conversation_id,
                            "action": action_to_dict(action),
                            "message": message_to_dict(confirmation),
                        },
                    )
                    return AgentResult(
                        conversation_id=conversation_id,
                        messages=new_messages,
                        pending_actions=[action],
                        final_text=confirmation_text,
                        steps=step,
                        usage=usage,
                    )

                action = self.actions.create(
                    tool_name=tool.name,
                    arguments=call.arguments,
                    permission_level=decision.level,
                    summary=summary,
                    status="executing",
                    conversation_id=conversation_id,
                    tool_call_id=call.id,
                )
                await self.event_bus.publish(
                    "tool.started",
                    {"conversation_id": conversation_id, "action": action_to_dict(action)},
                )
                await self.state.update(
                    thinking=False,
                    executing=True,
                    active_tool=tool.name,
                    detail=summary,
                    active_conversation_id=conversation_id,
                )
                result = await self._execute_tool(tool, call.arguments, settings, conversation_id)
                status = "executed" if result.success else "failed"
                action = self.actions.update(
                    action.id,
                    status=status,
                    result=result.to_dict(),
                    error=result.error,
                ) or action
                new_messages.append(
                    await self._save_tool_result(conversation_id, call, result, settings)
                )
                await self.event_bus.publish(
                    "tool.finished",
                    {
                        "conversation_id": conversation_id,
                        "action": action_to_dict(action),
                        "result": result.to_dict(),
                    },
                )
                await self.state.update(
                    executing=False,
                    thinking=True,
                    active_tool=None,
                    detail="Analisando o resultado…",
                )

        text = (
            f"Atingi o limite de {settings.max_agent_steps} etapas sem concluir a tarefa. "
            "Posso continuar se você pedir, ou você pode dividir a solicitação em partes menores."
        )
        assistant = await self._save_assistant(
            conversation_id, text, metadata={"kind": "max_steps"}
        )
        new_messages.append(assistant)
        return AgentResult(
            conversation_id=conversation_id,
            messages=new_messages,
            final_text=text,
            steps=settings.max_agent_steps,
            usage=usage,
        )

    def _build_context(
        self, conversation_id: str, settings: RuntimeSettings, *, voice_mode: bool
    ) -> list[dict[str, Any]]:
        records = self.messages.list(conversation_id)
        trimmed = _sanitize_history(records, settings.context_messages)
        last_user = next(
            (record.content for record in reversed(records) if record.role == "user"), ""
        )
        memories = self.memory.retrieve_context(last_user, conversation_id)
        memory_text = self.memory.as_prompt(memories)
        plan = self.planner.get_plan(conversation_id)
        system = build_system_prompt(
            settings, memories=memory_text, plan=plan, voice_mode=voice_mode
        )
        return [{"role": "system", "content": system}] + [
            record.to_llm() for record in trimmed
        ]

    async def _execute_tool(
        self,
        tool: BaseTool,
        arguments: dict[str, Any],
        settings: RuntimeSettings,
        conversation_id: str,
    ) -> ToolResult:
        path_guard = PathGuard(
            settings.allowed_roots,
            data_dir=self.app_settings.data_dir,
            block_sensitive=settings.block_sensitive_files,
        )
        context = ToolContext(
            app_settings=self.app_settings,
            runtime_settings=settings,
            path_guard=path_guard,
            data_dir=self.app_settings.data_dir,
            event_bus=self.event_bus,
            state=self.state,
            user_home=Path.home(),
            process_id=os.getpid(),
            memory_repo=self.memory.repository,
            conversation_id=conversation_id,
            extras={"planner": self.planner},
        )
        if tool.blocking:
            return await asyncio.to_thread(_run_tool_sync, tool, arguments, context)
        return await tool.run(arguments, context)

    async def _save_assistant(
        self,
        conversation_id: str,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MessageRecord:
        message = self.messages.add(
            conversation_id,
            "assistant",
            content,
            tool_calls=tool_calls,
            metadata=metadata,
        )
        await self.event_bus.publish(
            "message.created",
            {"conversation_id": conversation_id, "message": message_to_dict(message)},
        )
        return message

    async def _save_tool_result(
        self,
        conversation_id: str,
        call: ToolCall,
        result: ToolResult,
        settings: RuntimeSettings,
    ) -> MessageRecord:
        payload = json.dumps(result.to_dict(), ensure_ascii=False, default=str)
        if len(payload) > settings.max_tool_result_chars:
            payload = truncate(payload, settings.max_tool_result_chars)
        message = self.messages.add(
            conversation_id,
            "tool",
            payload,
            tool_call_id=call.id,
            name=call.name,
            metadata={"kind": "tool_result", "success": result.success},
        )
        await self.event_bus.publish(
            "message.created",
            {"conversation_id": conversation_id, "message": message_to_dict(message)},
        )
        return message

    async def _cancelled(
        self,
        conversation_id: str,
        new_messages: list[MessageRecord],
        step: int,
        usage: dict[str, Any],
    ) -> AgentResult:
        text = "Operação interrompida pelo usuário."
        message = await self._save_assistant(
            conversation_id, text, metadata={"kind": "cancelled"}
        )
        new_messages.append(message)
        await self.state.update(
            thinking=False, executing=False, active_tool=None, detail="Interrompido"
        )
        return AgentResult(
            conversation_id=conversation_id,
            messages=new_messages,
            final_text=text,
            cancelled=True,
            steps=step,
            usage=usage,
        )


def _run_tool_sync(tool: BaseTool, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    """Executa ferramentas bloqueantes fora do event loop do servidor."""
    return asyncio.run(tool.run(arguments, context))


def _sanitize_history(records: list[MessageRecord], max_messages: int) -> list[MessageRecord]:
    if max_messages > 0:
        records = records[-max_messages:]
    while records and records[0].role == "tool":
        records.pop(0)
    valid: list[MessageRecord] = []
    for index, record in enumerate(records):
        if record.role == "assistant" and record.tool_calls:
            ids = {
                str(call.get("id"))
                for call in record.tool_calls
                if isinstance(call, dict) and call.get("id")
            }
            answered = {
                candidate.tool_call_id
                for candidate in records[index + 1 :]
                if candidate.role == "tool"
            }
            if ids - answered:
                if record.content:
                    valid.append(replace(record, tool_calls=None))
                continue
        if record.role == "tool":
            answered = any(
                candidate.role == "assistant"
                and candidate.tool_calls
                and any(
                    isinstance(call, dict) and str(call.get("id")) == record.tool_call_id
                    for call in candidate.tool_calls
                )
                for candidate in valid
            )
            if not answered:
                continue
        valid.append(record)
    return valid
