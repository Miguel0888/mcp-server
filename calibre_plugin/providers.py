#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""Provider/model definitions for MCP Server Recherche."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Dict


class ProviderType(str, Enum):
    """Enum of protocol flavors the chat client understands."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


DEFAULT_MODEL_SETTINGS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "provider": "openai",
        "display_name": "OpenAI",
        "base_url": "https://api.openai.com",
        "chat_endpoint": "/v1/chat/completions",
        "provider_type": ProviderType.OPENAI.value,
        "model": "gpt-4o-mini",
        "api_key": "",
        "enabled": False,
        "temperature": 0.4,
    },
    "gemini": {
        "provider": "gemini",
        "display_name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "chat_endpoint": "/v1beta/models/{model}:generateContent",
        "provider_type": ProviderType.GEMINI.value,
        "model": "gemini-2.0-flash-exp",
        "api_key": "",
        "enabled": False,
        "temperature": 0.3,
    },
    "deepseek": {
        "provider": "deepseek",
        "display_name": "Deepseek",
        "base_url": "https://api.deepseek.com",
        "chat_endpoint": "/v1/chat/completions",
        "provider_type": ProviderType.OPENAI.value,
        "model": "deepseek-chat",
        "api_key": "",
        "enabled": False,
        "temperature": 0.4,
    },
    "grok": {
        "provider": "grok",
        "display_name": "Grok / xAI",
        "base_url": "https://api.x.ai",
        "chat_endpoint": "/v1/chat/completions",
        "provider_type": ProviderType.OPENAI.value,
        "model": "grok-beta",
        "api_key": "",
        "enabled": False,
        "temperature": 0.4,
    },
    "anthropic": {
        "provider": "anthropic",
        "display_name": "Anthropic Claude",
        "base_url": "https://api.anthropic.com",
        "chat_endpoint": "/v1/messages",
        "provider_type": ProviderType.ANTHROPIC.value,
        "model": "claude-3-5-sonnet-20241022",
        "api_key": "",
        "enabled": False,
        "temperature": 0.3,
        "max_tokens": 1024,
    },
    "nvidia": {
        "provider": "nvidia",
        "display_name": "Nvidia NIM",
        "base_url": "https://integrate.api.nvidia.com",
        "chat_endpoint": "/v1/chat/completions",
        "provider_type": ProviderType.OPENAI.value,
        "model": "meta/llama-3.1-8b-instruct",
        "api_key": "",
        "enabled": False,
        "temperature": 0.4,
    },
    "openrouter": {
        "provider": "openrouter",
        "display_name": "OpenRouter",
        "base_url": "https://openrouter.ai/api",
        "chat_endpoint": "/v1/chat/completions",
        "provider_type": ProviderType.OPENAI.value,
        "model": "openrouter/auto",
        "api_key": "",
        "enabled": False,
        "temperature": 0.4,
    },
    "ollama": {
        "provider": "ollama",
        "display_name": "Ollama (lokal)",
        "base_url": "http://127.0.0.1:11434",
        "chat_endpoint": "/v1/chat/completions",
        "provider_type": ProviderType.OPENAI.value,
        "model": "llama3.1",
        "api_key": "",
        "enabled": False,
        "temperature": 0.2,
    },
    "custom": {
        "provider": "custom",
        "display_name": "Custom Endpoint",
        "base_url": "",
        "chat_endpoint": "/v1/chat/completions",
        "provider_type": ProviderType.OPENAI.value,
        "model": "gpt-4o-mini",
        "api_key": "",
        "enabled": False,
        "temperature": 0.3,
    },
}

DEFAULT_SELECTED_MODEL = {
    "provider": "openai",
    "model": DEFAULT_MODEL_SETTINGS["openai"]["model"],
}


def get_default_models() -> Dict[str, Dict[str, Any]]:
    """Return a deep copy of default provider definitions."""

    return deepcopy(DEFAULT_MODEL_SETTINGS)


def ensure_model_prefs(prefs) -> Dict[str, Dict[str, Any]]:
    """Ensure prefs contain model definitions and a selected model entry."""

    models = prefs.get("models") or {}
    models = deepcopy(models)
    changed = False

    if not models:
        models = get_default_models()
        changed = True
    else:
        for key, definition in DEFAULT_MODEL_SETTINGS.items():
            if key not in models:
                models[key] = deepcopy(definition)
                changed = True
                continue
            for field, default_value in definition.items():
                if field not in models[key]:
                    models[key][field] = deepcopy(default_value)
                    changed = True

    if changed:
        prefs["models"] = models

    selected = prefs.get("selected_model") or {}
    provider_key = selected.get("provider")
    if not provider_key or provider_key not in models:
        selected = deepcopy(DEFAULT_SELECTED_MODEL)
    elif not selected.get("model"):
        selected["model"] = models[provider_key]["model"]

    prefs["selected_model"] = selected
    return models


def list_enabled_providers(models: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Return subset containing only enabled providers."""

    return {key: cfg for key, cfg in models.items() if cfg.get("enabled")}


def describe_provider(cfg: Dict[str, Any]) -> str:
    """Return a human readable provider label."""

    return cfg.get("display_name") or cfg.get("provider") or "Unbenannt"


def set_selected_model(prefs, provider_key: str, model_name: str) -> None:
    """Persist selected provider/model pair."""

    prefs["selected_model"] = {"provider": provider_key, "model": model_name}


def get_selected_model(prefs) -> Dict[str, str]:
    """Read selected model from prefs (ensuring defaults first)."""

    ensure_model_prefs(prefs)
    return prefs.get("selected_model") or deepcopy(DEFAULT_SELECTED_MODEL)

