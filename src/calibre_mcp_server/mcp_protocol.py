#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""Minimal MCP protocol helpers for the WebSocket server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class MCPRequest:
    request_id: str
    method: str
    params: Optional[Dict[str, Any]] = None


@dataclass
class MCPResponse:
    request_id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


@dataclass
class MCPToolDescription:
    name: str
    description: str
    input_schema: Dict[str, Any]


def make_error_response(request_id: str, message: str, code: str = "internal_error") -> Dict[str, Any]:
    return {
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def make_result_response(request_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": request_id,
        "result": result,
    }

