from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .generated import OPERATIONS


class AIxClientError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class AIxClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AIxClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def call(
        self,
        operation_id: str,
        *,
        path: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        json: Any = None,
        files: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            method, route = OPERATIONS[operation_id]
        except KeyError as exc:
            raise ValueError(f"Unknown AIx operation: {operation_id}") from exc
        for name, value in (path or {}).items():
            route = route.replace("{" + name + "}", str(value))
        if "{" in route:
            raise ValueError(f"Missing path parameter for {route}")
        response = self._client.request(
            method,
            route,
            params=query,
            json=json if files is None else None,
            files=files,
            data=data,
        )
        if response.is_error:
            payload = response.json()
            error = payload.get("error", {})
            raise AIxClientError(
                response.status_code,
                error.get("code", "request_failed"),
                error.get("message", f"Request failed ({response.status_code})"),
            )
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        return response.json() if "json" in content_type else response.content
