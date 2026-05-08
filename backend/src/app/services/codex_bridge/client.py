import asyncio
import json
import logging
import os
import shutil
import tempfile
from asyncio.subprocess import Process
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from src.app.config import settings

logger = logging.getLogger(__name__)

NotificationHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class CodexBridgeError(RuntimeError):
    pass


class JsonRpcClient:
    def __init__(
        self,
        process: Process,
        *,
        timeout_seconds: float,
        notification_handler: NotificationHandler | None = None,
    ) -> None:
        if process.stdin is None or process.stdout is None:
            raise CodexBridgeError("Codex app-server stdio pipes are unavailable")
        self.process = process
        self.stdin = process.stdin
        self.stdout = process.stdout
        self.timeout_seconds = timeout_seconds
        self.notification_handler = notification_handler
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task | None = asyncio.create_task(self._read_loop())

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future
        await self._write({"method": method, "id": request_id, "params": params or {}})
        try:
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise CodexBridgeError(f"Codex request timed out: {method}") from exc

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._write({"method": method, "params": params or {}})

    async def respond(self, request_id: int, result: dict[str, Any]) -> None:
        await self._write({"id": request_id, "result": result})

    async def respond_error(self, request_id: int, message: str, code: int = -32000) -> None:
        await self._write({"id": request_id, "error": {"code": code, "message": message}})

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        for future in self._pending.values():
            if not future.done():
                future.set_exception(CodexBridgeError("Codex app-server connection closed"))
        self._pending.clear()

    async def _write(self, message: dict[str, Any]) -> None:
        if self.stdin.is_closing():
            raise CodexBridgeError("Codex app-server stdin is closed")
        self.stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        await self.stdin.drain()

    async def _read_loop(self) -> None:
        while True:
            line = await self.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                logger.warning("Ignoring non-JSON Codex app-server line: %r", line[:200])
                continue
            await self._handle_message(message)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message) and "method" not in message:
            request_id = message.get("id")
            future = self._pending.pop(request_id, None)
            if future and not future.done():
                if "error" in message:
                    error = message["error"]
                    future.set_exception(CodexBridgeError(str(error.get("message", error))))
                else:
                    future.set_result(message.get("result") or {})
            return

        if "id" in message and "method" in message:
            await self._handle_server_request(message)
            return

        if self.notification_handler:
            result = self.notification_handler(message)
            if asyncio.iscoroutine(result):
                await result

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        request_id = message["id"]
        method = message.get("method")
        if method == "item/commandExecution/requestApproval":
            await self.respond(request_id, {"decision": "decline"})
        elif method == "item/fileChange/requestApproval":
            await self.respond(request_id, {"decision": "decline"})
        elif method == "tool/requestUserInput":
            await self.respond_error(request_id, "User input requests are disabled in review-only mode")
        elif method == "account/chatgptAuthTokens/refresh":
            await self.respond_error(request_id, "External token refresh is not supported")
        else:
            await self.respond_error(request_id, f"Unsupported Codex server request: {method}")


class CodexAppServerClient:
    def __init__(self) -> None:
        self.process: Process | None = None
        self.rpc: JsonRpcClient | None = None
        self.initialized = False
        self.last_error = ""
        self._stderr_task: asyncio.Task | None = None
        self._agent_text_by_turn: dict[str, str] = {}
        self._turn_completed: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._completed_turn_notifications: dict[str, dict[str, Any]] = {}
        self._sandbox_workspace: TemporaryDirectory[str] | None = None

    @staticmethod
    def command_available() -> bool:
        if settings.codex_review_mock:
            return True
        command = settings.codex_command
        return bool(shutil.which(command) or Path(command).exists())

    async def start(self) -> None:
        if self.process and self.process.returncode is None and self.rpc:
            return
        if settings.codex_review_mock:
            return
        if not settings.codex_transport_supported():
            raise CodexBridgeError("Codex review v1 supports only stdio transport")
        argv = settings.codex_argv()
        sandbox_cwd = self._ensure_sandbox_workspace()
        env = os.environ.copy()
        env["PWD"] = sandbox_cwd
        try:
            self.process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=sandbox_cwd,
                env=env,
            )
        except OSError as exc:
            self.last_error = str(exc)
            if self._sandbox_workspace:
                self._sandbox_workspace.cleanup()
                self._sandbox_workspace = None
            raise CodexBridgeError(f"Failed to start Codex app-server: {exc}") from exc

        self._stderr_task = asyncio.create_task(self._drain_stderr())
        self.rpc = JsonRpcClient(
            self.process,
            timeout_seconds=settings.codex_timeout_seconds,
            notification_handler=self._handle_notification,
        )
        try:
            await asyncio.wait_for(self.initialize(), timeout=settings.codex_startup_timeout_seconds)
        except Exception as exc:
            self.last_error = str(exc)
            await self.shutdown()
            raise

    async def initialize(self) -> None:
        if not self.rpc:
            raise CodexBridgeError("Codex app-server is not started")
        await self.rpc.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "agoraai_codex_review",
                    "title": "AgoraAI Codex Review Agent",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "experimentalApi": False,
                    "optOutNotificationMethods": [],
                },
            },
        )
        await self.rpc.notify("initialized", {})
        self.initialized = True
        self.last_error = ""

    async def run_turn(self, prompt: str) -> str:
        if settings.codex_review_mock:
            return self._mock_review_answer(prompt)
        if not settings.codex_review_only:
            raise CodexBridgeError("Codex bridge is configured outside review-only mode")
        await self.start()
        if not self.rpc:
            raise CodexBridgeError("Codex app-server is not connected")

        sandbox_cwd = self._ensure_sandbox_workspace()
        sandbox_policy = self._read_only_sandbox()

        thread_response = await self.rpc.request(
            "thread/start",
            {
                "cwd": sandbox_cwd,
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "serviceName": "agoraai_codex_review",
                "ephemeral": True,
            },
        )
        thread_id = thread_response.get("thread", {}).get("id")
        if not thread_id:
            raise CodexBridgeError("Codex app-server did not return a thread id")

        turn_params = {
            "threadId": thread_id,
            "cwd": sandbox_cwd,
            "input": [{"type": "text", "text": prompt}],
            "approvalPolicy": "never",
            "sandboxPolicy": sandbox_policy,
        }
        if settings.codex_review_model.strip():
            turn_params["model"] = settings.codex_review_model.strip()

        turn_response = await self.rpc.request("turn/start", turn_params)
        turn_id = turn_response.get("turn", {}).get("id")
        if not turn_id:
            raise CodexBridgeError("Codex app-server did not return a turn id")

        loop = asyncio.get_running_loop()
        completed = self._get_turn_completion_future(turn_id, loop)
        try:
            notification = await asyncio.wait_for(completed, timeout=settings.codex_timeout_seconds)
        except TimeoutError as exc:
            raise CodexBridgeError("Codex review timed out") from exc

        turn = notification.get("turn") or {}
        if turn.get("status") == "failed":
            raise CodexBridgeError(str(turn.get("error") or "Codex turn failed"))
        answer = (self._agent_text_by_turn.get(turn_id) or "").strip()
        if not answer:
            answer = self._extract_answer_from_turn(turn)
        if not answer:
            raise CodexBridgeError("Codex review completed without an answer")
        return answer

    async def shutdown(self) -> None:
        if self.rpc:
            await self.rpc.close()
            self.rpc = None
        if self._stderr_task:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None
        self.initialized = False
        self._agent_text_by_turn.clear()
        self._turn_completed.clear()
        self._completed_turn_notifications.clear()
        if self._sandbox_workspace:
            self._sandbox_workspace.cleanup()
            self._sandbox_workspace = None

    async def _drain_stderr(self) -> None:
        if not self.process or self.process.stderr is None:
            return
        while True:
            line = await self.process.stderr.readline()
            if not line:
                return
            logger.debug("codex app-server stderr: %s", line.decode("utf-8", errors="replace").rstrip())

    def _handle_notification(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params") or {}
        if method == "item/agentMessage/delta":
            turn_id = params.get("turnId")
            delta = params.get("delta") or ""
            if turn_id:
                self._agent_text_by_turn[turn_id] = self._agent_text_by_turn.get(turn_id, "") + delta
        elif method == "item/completed":
            item = params.get("item") or {}
            turn_id = params.get("turnId")
            if turn_id and item.get("type") == "agentMessage" and item.get("text"):
                self._agent_text_by_turn[turn_id] = item["text"]
        elif method == "turn/completed":
            turn = params.get("turn") or {}
            turn_id = turn.get("id")
            future = self._turn_completed.get(turn_id)
            if future and not future.done():
                future.set_result(params)
            elif turn_id:
                self._completed_turn_notifications[turn_id] = params

    @staticmethod
    def _extract_answer_from_turn(turn: dict[str, Any]) -> str:
        items = turn.get("items") or []
        texts = [
            str(item.get("text", "")).strip()
            for item in items
            if item.get("type") == "agentMessage" and item.get("text")
        ]
        return "\n\n".join(text for text in texts if text)

    def _ensure_sandbox_workspace(self) -> str:
        if self._sandbox_workspace is None:
            base_dir = Path(settings.codex_review_workdir)
            base_dir.mkdir(parents=True, exist_ok=True)
            self._sandbox_workspace = tempfile.TemporaryDirectory(
                prefix="session-",
                dir=str(base_dir),
            )
        return self._sandbox_workspace.name

    @staticmethod
    def _read_only_sandbox() -> dict[str, Any]:
        return {
            "type": "readOnly",
            "networkAccess": False,
        }

    def _get_turn_completion_future(
        self,
        turn_id: str,
        loop: asyncio.AbstractEventLoop,
    ) -> asyncio.Future[dict[str, Any]]:
        future = self._turn_completed.get(turn_id)
        if future is None:
            future = loop.create_future()
            self._turn_completed[turn_id] = future
        completed_notification = self._completed_turn_notifications.pop(turn_id, None)
        if completed_notification and not future.done():
            future.set_result(completed_notification)
        return future

    @staticmethod
    def _mock_review_answer(prompt: str) -> str:
        question_marker = "質問:"
        question = ""
        if question_marker in prompt:
            question = prompt.split(question_marker, 1)[1].split("\n", 1)[0].strip()
        if not question:
            question = "この結果の確認"
        return (
            "1. 結論\n"
            f"{question}について、提示されたレポート内の情報だけでは追加確認が必要です。\n\n"
            "2. 根拠\n"
            "Decision Brief、主要な理由、未確認事項を優先して見る構成になっています。\n\n"
            "3. 弱い前提\n"
            "サンプル応答のため、実際のレポート固有の根拠は含めていません。\n\n"
            "4. 反証・別解\n"
            "別の立場では、前提条件や未検証の外部要因を重く見る可能性があります。\n\n"
            "5. 意思決定リスク\n"
            "根拠が薄い項目を確定事項として扱うと判断を誤る恐れがあります。\n\n"
            "6. 次に検証すべきこと\n"
            "重要な未知事項、証拠不足、反対意見を順に確認してください。"
        )
