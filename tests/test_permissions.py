"""Testes da política de permissões em três níveis."""

from __future__ import annotations

from backend.core.permissions import PermissionManager
from backend.tools.filesystem import CreateFileTool, DeleteFileTool, ReadFileTool


def test_level1_is_always_allowed(settings_service) -> None:
    permissions = PermissionManager(settings_service)
    decision = permissions.evaluate(ReadFileTool(), {"path": "qualquer.txt"})
    assert decision.allowed is True
    assert decision.requires_confirmation is False
    assert decision.level == 1


def test_level2_requires_confirmation_by_default(settings_service) -> None:
    permissions = PermissionManager(settings_service)
    decision = permissions.evaluate(CreateFileTool(), {"path": "x.txt", "content": "oi"})
    assert decision.allowed is False
    assert decision.requires_confirmation is True
    assert decision.level == 2


def test_level2_can_be_authorized_in_settings(settings_service) -> None:
    settings_service.update({"confirm_level2": False})
    permissions = PermissionManager(settings_service)
    decision = permissions.evaluate(CreateFileTool(), {"path": "x.txt", "content": "oi"})
    assert decision.allowed is True
    assert decision.requires_confirmation is False


def test_level3_always_requires_confirmation(settings_service) -> None:
    permissions = PermissionManager(settings_service)
    decision = permissions.evaluate(DeleteFileTool(), {"path": "x.txt"})
    assert decision.allowed is False
    assert decision.requires_confirmation is True
    assert decision.blocked is False
    assert decision.level == 3


def test_level3_blocked_when_disabled(settings_service) -> None:
    settings_service.update({"allow_level3": False})
    permissions = PermissionManager(settings_service)
    decision = permissions.evaluate(DeleteFileTool(), {"path": "x.txt"})
    assert decision.allowed is False
    assert decision.requires_confirmation is False
    assert decision.blocked is True
    assert "desativadas" in decision.reason


def test_evaluate_level_clamps_out_of_range(settings_service) -> None:
    permissions = PermissionManager(settings_service)
    assert permissions.evaluate_level(0).level == 1
    assert permissions.evaluate_level(99).level == 3
