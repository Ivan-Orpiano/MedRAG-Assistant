"""Thin async client over the FastAPI backend. The JWT lives in NiceGUI's
per-user storage; every helper reads it from there so pages stay simple."""
import json
from collections.abc import AsyncIterator

import httpx
from nicegui import app

from app.settings import API_BASE_URL


def _headers() -> dict:
    token = app.storage.user.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


async def login(email: str, password: str) -> dict:
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30) as client:
        response = await client.post(
            "/api/v1/auth/login", data={"username": email, "password": password}
        )
        response.raise_for_status()
        return response.json()


async def get_json(path: str, params: dict | None = None):
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=60) as client:
        response = await client.get(path, headers=_headers(), params=params)
        response.raise_for_status()
        return response.json()


async def post_json(path: str, payload: dict):
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=60) as client:
        response = await client.post(path, headers=_headers(), json=payload)
        response.raise_for_status()
        return response.json() if response.content else None


async def patch_json(path: str, payload: dict, params: dict | None = None):
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=60) as client:
        response = await client.patch(path, headers=_headers(), json=payload, params=params)
        response.raise_for_status()
        return response.json() if response.content else None


async def delete(path: str):
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=60) as client:
        response = await client.delete(path, headers=_headers())
        response.raise_for_status()


async def upload_document(fields: dict, filename: str, content: bytes, mime: str, path: str = "/api/v1/documents"):
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=300) as client:
        response = await client.post(
            path, headers=_headers(), data=fields, files={"file": (filename, content, mime)}
        )
        response.raise_for_status()
        return response.json()


async def chat_stream(payload: dict) -> AsyncIterator[tuple[str, str]]:
    """Yield (event, data) tuples from the backend SSE stream."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=None) as client:
        async with client.stream(
            "POST", "/api/v1/chat/stream", headers=_headers(), json=payload
        ) as response:
            response.raise_for_status()
            event = "message"
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:"):].lstrip())
                elif line == "":
                    if data_lines:
                        yield event, "\n".join(data_lines)
                    event, data_lines = "message", []


def api_error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        return exc.response.json().get("detail", str(exc))
    except (json.JSONDecodeError, AttributeError):
        return str(exc)
