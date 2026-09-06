from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.routes import router
from backend.app.auth import AuthService
from backend.app.chat import ChatConflictError, ChatNotFoundError, ChatService
from backend.app.codex import CodexAppServer, CodexConnectionError, CodexRpcError
from backend.app.settings import Settings
from backend.app.settings import settings as default_settings


def create_app(config: Settings | None = None, codex: CodexAppServer | None = None) -> FastAPI:
    app_settings = config or default_settings
    logging.basicConfig(level=app_settings.log_level)
    codex_client = codex or CodexAppServer(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = app_settings
        app.state.codex = codex_client
        app.state.auth_service = AuthService(codex_client, app_settings)
        app.state.chat_service = ChatService(codex_client, app_settings)
        await codex_client.start()
        try:
            yield
        finally:
            await codex_client.stop()

    app = FastAPI(title="RepoSpec Viewer API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(ChatNotFoundError)
    async def not_found_handler(request: Request, exc: ChatNotFoundError) -> JSONResponse:
        return _problem(request, 404, "Resource not found", str(exc), "RESOURCE_NOT_FOUND", False)

    @app.exception_handler(ChatConflictError)
    async def conflict_handler(request: Request, exc: ChatConflictError) -> JSONResponse:
        return _problem(request, 409, "Turn already running", str(exc), "TURN_CONFLICT", True)

    @app.exception_handler(CodexConnectionError)
    async def unavailable_handler(request: Request, exc: CodexConnectionError) -> JSONResponse:
        return _problem(
            request,
            503,
            "Codex App Server is unavailable",
            "Codex App Serverへ接続できません。しばらく待って再試行してください。",
            "CODEX_UNAVAILABLE",
            True,
        )

    @app.exception_handler(CodexRpcError)
    async def rpc_error_handler(request: Request, exc: CodexRpcError) -> JSONResponse:
        code = "AUTH_REQUIRED" if exc.code == -32000 else "CODEX_TURN_FAILED"
        return _problem(request, 502, "Codex request failed", str(exc), code, True)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return _problem(
            request,
            422,
            "Validation error",
            "入力内容を確認してください。",
            "VALIDATION_ERROR",
            False,
        )

    return app


def _problem(
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    retryable: bool,
) -> JSONResponse:
    trace_id = request.headers.get("X-Trace-ID", str(uuid4()))
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": f"https://repospec.local/problems/{code.lower().replace('_', '-')}",
            "title": title,
            "status": status_code,
            "detail": detail,
            "code": code,
            "retryable": retryable,
            "trace_id": trace_id,
        },
    )


app = create_app()
