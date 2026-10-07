from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.repository_routes import router as repository_router
from backend.app.api.routes import router
from backend.app.auth import AuthService
from backend.app.chat import ChatConflictError, ChatNotFoundError, ChatService
from backend.app.codex import CodexAppServer, CodexConnectionError, CodexRpcError
from backend.app.db import Database
from backend.app.repositories import (
    DatabaseUnavailableError,
    RepositoryAlreadyRegisteredError,
    RepositoryBusyError,
    RepositoryDeleteError,
    RepositoryInUseError,
    RepositoryNotFoundError,
    RepositoryOperationRunner,
    RepositoryService,
)
from backend.app.repositories.git import GitClient
from backend.app.repositories.store import RepositoryStore
from backend.app.repositories.url import InvalidGitHubUrlError
from backend.app.repositories.workspace import WorkspaceResolver
from backend.app.settings import Settings


def create_app(config: Settings | None = None, codex: CodexAppServer | None = None) -> FastAPI:
    app_settings = config or Settings()
    logging.basicConfig(level=app_settings.log_level)
    codex_client = codex or CodexAppServer(app_settings)
    database = Database(app_settings.database_url)
    workspace = WorkspaceResolver(app_settings.workspace_root)
    operation_runner = RepositoryOperationRunner()
    repository_store = RepositoryStore(database.sessions)
    git_client = GitClient(
        app_settings.git_executable,
        workspace,
        app_settings.git_clone_timeout_seconds,
        app_settings.git_sync_timeout_seconds,
        app_settings.git_max_repository_bytes,
        app_settings.git_max_file_count,
    )
    repository_service = RepositoryService(
        repository_store, git_client, workspace, operation_runner
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = app_settings
        app.state.codex = codex_client
        app.state.auth_service = AuthService(codex_client, app_settings)
        app.state.chat_service = ChatService(codex_client, app_settings)
        app.state.database = database
        app.state.repository_service = repository_service
        workspace.prepare()
        await codex_client.start()
        try:
            await repository_service.recover_interrupted()
            yield
        finally:
            await operation_runner.shutdown()
            await database.close()
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
    app.include_router(repository_router)

    @app.exception_handler(InvalidGitHubUrlError)
    async def invalid_github_url_handler(
        request: Request, exc: InvalidGitHubUrlError
    ) -> JSONResponse:
        return _problem(request, 422, "Invalid GitHub URL", str(exc), "INVALID_GITHUB_URL", False)

    @app.exception_handler(RepositoryAlreadyRegisteredError)
    async def duplicate_repository_handler(
        request: Request, exc: RepositoryAlreadyRegisteredError
    ) -> JSONResponse:
        extra = {"repository_id": str(exc.repository_id)} if exc.repository_id else None
        return _problem(
            request,
            409,
            "Repository already registered",
            str(exc),
            "REPOSITORY_ALREADY_REGISTERED",
            False,
            extra,
        )

    @app.exception_handler(RepositoryNotFoundError)
    async def repository_not_found_handler(
        request: Request, exc: RepositoryNotFoundError
    ) -> JSONResponse:
        return _problem(
            request, 404, "Repository not found", str(exc), "REPOSITORY_NOT_FOUND", False
        )

    @app.exception_handler(RepositoryBusyError)
    async def repository_busy_handler(request: Request, exc: RepositoryBusyError) -> JSONResponse:
        return _problem(request, 409, "Repository busy", str(exc), "REPOSITORY_BUSY", True)

    @app.exception_handler(RepositoryInUseError)
    async def repository_in_use_handler(
        request: Request, exc: RepositoryInUseError
    ) -> JSONResponse:
        return _problem(request, 409, "Repository in use", str(exc), "REPOSITORY_IN_USE", False)

    @app.exception_handler(RepositoryDeleteError)
    async def repository_delete_handler(
        request: Request, exc: RepositoryDeleteError
    ) -> JSONResponse:
        return _problem(request, 500, "Repository deletion failed", str(exc), "DELETE_FAILED", True)

    @app.exception_handler(DatabaseUnavailableError)
    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable_handler(request: Request, _exc: Exception) -> JSONResponse:
        return _problem(
            request,
            503,
            "Database unavailable",
            "データベースへ接続できません。しばらく待って再試行してください。",
            "DATABASE_UNAVAILABLE",
            True,
        )

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
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    trace_id = getattr(
        request.state,
        "trace_id",
        request.headers.get("X-Trace-ID", str(uuid4())),
    )
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
            **(extra or {}),
        },
    )


app = create_app()
