#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""Simple chat-provider client inspired by Ask AI plugin."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from .providers import ProviderType

log = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str
    content: str


class ChatProviderClient:
    """Dispatch chat requests to configured providers."""

    def __init__(self, prefs):
        self.prefs = prefs

    # ------------------------------------------------------------------ API
    def send_chat(self, user_text: str) -> str:
        models = self.prefs.get("models") or {}
        selected = self.prefs.get("selected_model") or {}
        provider_key = selected.get("provider")
        if not provider_key:
            raise RuntimeError("Kein Provider ausgewaehlt. Bitte Einstellungen pruefen.")
        provider_cfg = models.get(provider_key)
        if not provider_cfg or not provider_cfg.get("enabled"):
            raise RuntimeError(f"Provider '{provider_key}' ist nicht aktiviert.")

        provider_type = ProviderType(provider_cfg["provider_type"])
        if provider_type == ProviderType.OPENAI:
            return self._send_openai_like(provider_cfg, selected, user_text)
        if provider_type == ProviderType.ANTHROPIC:
            return self._send_anthropic(provider_cfg, selected, user_text)
        if provider_type == ProviderType.GEMINI:
            return self._send_gemini(provider_cfg, selected, user_text)
        raise RuntimeError(f"Provider-Typ '{provider_type.value}' wird nicht unterstuetzt.")

    # ------------------------------------------------------------ HTTP utils
    def _build_url(self, cfg: Dict[str, Any]) -> str:
        base = (cfg.get("base_url") or "").rstrip("/")
        endpoint = cfg.get("chat_endpoint") or ""
        return f"{base}{endpoint}".replace("{model}", cfg.get("model") or "")

    def _request(self, method: str, url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
        log.debug("Posting chat request to %s", url)
        response = requests.request(method, url, headers=headers, json=payload, timeout=60)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
        try:
            return response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise RuntimeError("Antwort konnte nicht geparst werden") from exc

    # ---------------------------------------------------------- Provider impl
    def _send_openai_like(self, cfg: Dict[str, Any], selected: Dict[str, Any], user_text: str) -> str:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": "Du bist ein hilfreicher Recherche-Assistent."},
            {"role": "user", "content": user_text},
        ]
        payload = {
            "model": selected.get("model") or cfg.get("model"),
            "messages": messages,
            "temperature": cfg.get("temperature", 0.4),
        }
        api_key = cfg.get("api_key")
        if not api_key:
            raise RuntimeError("API-Key fehlt fuer den ausgewaehlten Provider.")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = self._build_url(cfg)
        data = self._request("POST", url, headers, payload)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("Antwort enthaelt keine choices.")
        return choices[0].get("message", {}).get("content", "")

    def _send_anthropic(self, cfg: Dict[str, Any], selected: Dict[str, Any], user_text: str) -> str:
        api_key = cfg.get("api_key")
        if not api_key:
            raise RuntimeError("API-Key fehlt fuer Anthropic.")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": cfg.get("anthropic_version", "2023-06-01"),
            "Content-Type": "application/json",
        }
        payload = {
            "model": selected.get("model") or cfg.get("model"),
            "max_tokens": cfg.get("max_tokens", 1024),
            "temperature": cfg.get("temperature", 0.4),
            "messages": [
                {"role": "user", "content": user_text},
            ],
        }
        url = self._build_url(cfg)
        data = self._request("POST", url, headers, payload)
        content = data.get("content") or []
        if not content:
            raise RuntimeError("Keine Antwort von Anthropic erhalten.")
        return "\n".join(part.get("text", "") for part in content)

    def _send_gemini(self, cfg: Dict[str, Any], selected: Dict[str, Any], user_text: str) -> str:
        api_key = cfg.get("api_key")
        if not api_key:
            raise RuntimeError("API-Key fehlt fuer Gemini.")
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": user_text},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": cfg.get("temperature", 0.3),
            },
        }
        url = self._build_url(cfg)
        data = self._request("POST", url, headers, payload)
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini antwortet ohne candidates.")
        return candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")

