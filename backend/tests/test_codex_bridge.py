import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.app.config import settings
from src.app.services.codex_bridge.client import CodexAppServerClient


class _FakeRpc:
    def __init__(self, client: CodexAppServerClient) -> None:
        self.client = client
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = params or {}
        self.requests.append((method, payload))
        if method == "thread/start":
            return {"thread": {"id": "thread_1"}}
        if method == "turn/start":
            self.client._handle_notification(
                {
                    "method": "item/agentMessage/delta",
                    "params": {"turnId": "turn_1", "delta": "fast answer"},
                }
            )
            self.client._handle_notification(
                {
                    "method": "turn/completed",
                    "params": {"turn": {"id": "turn_1", "status": "completed"}},
                }
            )
            return {"turn": {"id": "turn_1", "status": "inProgress"}}
        raise AssertionError(f"unexpected method {method}")

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_run_turn_buffers_completion_notification_before_waiter(
    monkeypatch: pytest.MonkeyPatch,
):
    client = CodexAppServerClient()
    fake_rpc = _FakeRpc(client)
    client.rpc = fake_rpc

    async def fake_start() -> None:
        return None

    monkeypatch.setattr(client, "start", fake_start)

    answer = await client.run_turn("review this report")

    assert answer == "fast answer"
    assert client._completed_turn_notifications == {}


@pytest.mark.asyncio
async def test_run_turn_uses_isolated_read_only_sandbox(
    monkeypatch: pytest.MonkeyPatch,
):
    client = CodexAppServerClient()
    fake_rpc = _FakeRpc(client)
    client.rpc = fake_rpc

    async def fake_start() -> None:
        return None

    monkeypatch.setattr(client, "start", fake_start)

    await client.run_turn("review this report")

    _, thread_params = fake_rpc.requests[0]
    _, turn_params = fake_rpc.requests[1]
    sandbox_cwd = Path(thread_params["cwd"])
    sandbox_policy = turn_params["sandboxPolicy"]

    assert sandbox_cwd.exists()
    assert Path.cwd() not in sandbox_cwd.parents
    assert turn_params["cwd"] == str(sandbox_cwd)
    assert sandbox_policy == {
        "type": "readOnly",
        "networkAccess": False,
    }

    await client.shutdown()
    await asyncio.sleep(0)
    assert not sandbox_cwd.exists()


@pytest.mark.asyncio
async def test_run_turn_uses_mock_without_starting_app_server(
    monkeypatch: pytest.MonkeyPatch,
):
    client = CodexAppServerClient()

    async def fail_start() -> None:
        raise AssertionError("mock mode should not start Codex app-server")

    monkeypatch.setattr(settings, "codex_review_mock", True)
    monkeypatch.setattr(client, "start", fail_start)

    answer = await client.run_turn("質問:\nこの結果で一番注意する点は？\n\nコンテキスト:\n{}")

    assert "提示されたレポート内の情報だけ" in answer
    assert "次に検証すべきこと" in answer
