from __future__ import annotations

from typing import Any

from backend.app.codex import CodexAppServer, CodexConnectionError
from backend.app.events import EventBuffer
from backend.app.settings import Settings


class AuthService:
    def __init__(self, codex: CodexAppServer, config: Settings) -> None:
        self._codex = codex
        self.events = EventBuffer(config.sse_event_buffer_size)
        codex.add_notification_handler(self._handle_notification)

    async def status(self) -> dict[str, Any]:
        if not self._codex.connected:
            return {
                "status": "error",
                "auth_mode": None,
                "plan_type": None,
                "app_server_connected": False,
            }
        try:
            result = await self._codex.request("account/read", {"refreshToken": False})
        except CodexConnectionError:
            return {
                "status": "error",
                "auth_mode": None,
                "plan_type": None,
                "app_server_connected": False,
            }
        account = result.get("account")
        if not account:
            state = "unauthenticated" if result.get("requiresOpenaiAuth", True) else "authenticated"
            return {
                "status": state,
                "auth_mode": None,
                "plan_type": None,
                "app_server_connected": True,
            }
        return {
            "status": "authenticated",
            "auth_mode": account.get("type"),
            "plan_type": account.get("planType"),
            "app_server_connected": True,
        }

    async def login(self) -> dict[str, Any]:
        await self._codex.ensure_connected()
        result = await self._codex.request(
            "account/login/start",
            {"type": "chatgpt", "appBrand": "chatgpt", "useHostedLoginSuccessPage": True},
        )
        await self.events.publish(
            "auth.authenticating",
            {"login_id": result.get("loginId")},
        )
        return {
            "login_id": result["loginId"],
            "auth_url": result["authUrl"],
        }

    async def cancel(self, login_id: str) -> None:
        await self._codex.request("account/login/cancel", {"loginId": login_id})
        await self.events.publish("auth.cancelled", {"login_id": login_id})

    async def logout(self) -> None:
        await self._codex.request("account/logout", {})

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "account/login/completed":
            if params.get("success"):
                await self.events.publish(
                    "auth.authenticated",
                    {"login_id": params.get("loginId")},
                )
            else:
                await self.events.publish(
                    "auth.failed",
                    {
                        "login_id": params.get("loginId"),
                        "message": "ChatGPTへのログインを完了できませんでした。",
                    },
                )
        elif method == "account/updated":
            authenticated = params.get("authMode") is not None
            await self.events.publish(
                "auth.authenticated" if authenticated else "auth.unauthenticated",
                {
                    "auth_mode": params.get("authMode"),
                    "plan_type": params.get("planType"),
                },
            )
        elif method == "app_server/disconnected":
            await self.events.publish(
                "auth.error",
                {"message": "Codex App Serverとの接続が切断されました。"},
            )
