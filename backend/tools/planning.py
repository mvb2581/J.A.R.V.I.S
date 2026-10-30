"""Ferramenta que torna o plano de execução visível e persistente."""

from __future__ import annotations

from typing import Any

from backend.tools.base import BaseTool, ToolContext, ToolResult


class UpdatePlanTool(BaseTool):
    name = "update_plan"
    description = (
        "Cria ou atualiza o plano visível de uma tarefa complexa. Use antes de executar vários passos "
        "e atualize o status de cada etapa (pending, in_progress, done, blocked) durante a execução."
    )
    permission_level = 1
    category = "planning"
    blocking = False
    parameters = {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "minLength": 2, "maxLength": 240},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "done", "blocked"],
                            "default": "pending",
                        },
                        "note": {"type": "string", "maxLength": 300},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["steps"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        planner = context.extras.get("planner")
        if planner is None or not context.conversation_id:
            return ToolResult.fail("Planejador indisponível nesta execução")
        plan = await planner.set_plan(context.conversation_id, arguments["steps"])
        done = sum(1 for step in plan if step["status"] == "done")
        return ToolResult.ok(
            {"plan": plan},
            display=f"Plano atualizado ({done}/{len(plan)} etapas concluídas)",
        )
