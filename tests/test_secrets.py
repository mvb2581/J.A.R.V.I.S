"""Testes do cofre DPAPI e da precedência de chaves de ambiente."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.ai.factory import ProviderFactory
from backend.config.settings import AppSettings
from backend.security.secrets import SecretStore, SecretStoreError

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI é exclusivo do Windows"
)


@pytest.fixture
def store(tmp_path: Path) -> SecretStore:
    return SecretStore(tmp_path / "data" / "secrets.json")


def test_dpapi_roundtrip_does_not_store_plaintext(store: SecretStore) -> None:
    secret = "sk-teste-1234567890abcdef"
    store.set("deepseek", secret)

    assert store.get("deepseek") == secret
    assert store.configured()["deepseek"] is True
    assert "deepseek" in store.describe()

    raw = store.path.read_text(encoding="utf-8")
    assert secret not in raw
    payload = json.loads(raw)
    assert payload["secrets"]["deepseek"]["blob"]


def test_delete_and_empty_value(store: SecretStore) -> None:
    store.set("openai", "sk-outra-chave-123456")
    store.delete("openai")
    assert store.get("openai") == ""
    assert store.configured()["openai"] is False

    store.set("anthropic", "sk-ant-1234567890")
    store.set("anthropic", "")
    assert store.get("anthropic") == ""


def test_invalid_provider_is_rejected(store: SecretStore) -> None:
    with pytest.raises(SecretStoreError):
        store.set("provedor_invalido", "x")


def test_corrupted_store_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    path.write_text("não é json", encoding="utf-8")
    store = SecretStore(path)
    with pytest.raises(SecretStoreError):
        store.configured()


def test_environment_key_takes_precedence(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path / "data",
        deepseek_api_key="chave-do-ambiente",
    )
    store = SecretStore(tmp_path / "data" / "secrets.json")
    store.set("deepseek", "chave-do-cofre")
    factory = ProviderFactory(settings, store)

    key, origin = factory.key_for("deepseek")
    assert key == "chave-do-ambiente"
    assert origin == "env"


def test_describe_never_exposes_key(tmp_path: Path) -> None:
    settings = AppSettings(
        data_dir=tmp_path / "data",
        deepseek_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        custom_api_key="",
    )
    store = SecretStore(tmp_path / "data" / "secrets.json")
    store.set("openai", "sk-segredo-1234567890")
    factory = ProviderFactory(settings, store)
    from backend.config.settings import RuntimeSettings

    descriptions = factory.describe(RuntimeSettings(provider="openai", model="gpt-4o-mini"))
    openai = next(item for item in descriptions if item["id"] == "openai")
    assert openai["key_source"] == "store"
    assert openai["key_configured_in_store"] is True
    assert "sk-segredo" not in json.dumps(descriptions)
