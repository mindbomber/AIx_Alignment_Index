from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from aix_client import AIxClient, AIxClientError
from aix_client.generated import OPERATIONS


ROOT = Path(__file__).resolve().parents[1]


def test_generated_operations_match_openapi():
    document = json.loads((ROOT / "spec" / "openapi.json").read_text())
    expected = {
        operation["operationId"]: (method.upper(), path)
        for path, path_item in document["paths"].items()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert OPERATIONS == dict(sorted(expected.items()))


def test_python_client_calls_generated_operation():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.url.path == "/v1/systems"
        return httpx.Response(200, json=[{"id": "system-1"}])

    with AIxClient(
        "https://api.example.test",
        "test-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.call("list_systems_v1_systems_get") == [{"id": "system-1"}]


def test_python_client_raises_stable_error():
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            403,
            json={
                "error": {
                    "code": "forbidden",
                    "message": "Permission denied",
                    "context": {},
                }
            },
        )
    )
    with AIxClient("https://api.example.test", transport=transport) as client:
        with pytest.raises(AIxClientError) as error:
            client.call("list_systems_v1_systems_get")
    assert error.value.status_code == 403
    assert error.value.code == "forbidden"
