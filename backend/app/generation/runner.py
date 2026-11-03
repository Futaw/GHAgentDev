from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError

from backend.app.codex import CodexAppServer, CodexConnectionError, CodexTimeoutError
from backend.app.codex.client import rpc_trace_id
from backend.app.events import EventBuffer
from backend.app.generation.models import GenerationJobModel, GenerationStatus, ViewerModel
from backend.app.generation.prompt import build_generation_prompt, build_schema_repair_prompt
from backend.app.generation.security import (
    GenerationPreflight,
    GenerationSecurityError,
)
from backend.app.generation.store import GenerationStore
from backend.app.settings import Settings
from backend.app.viewers.document import (
    canonical_document_json,
    parse_viewer_document,
    viewer_document_json_schema,
)
from backend.app.viewers.git_refs import (
    ViewerGitRefs,
    generation_ref,
    viewer_revision_ref,
)
from backend.app.viewers.renderer import render_viewer_document
from backend.app.viewers.sanitizer import HtmlSanitizeError, sanitize_viewer_html
from backend.app.viewers.source_validation import SourceReferenceError, SourceReferenceValidator

LOGGER = logging.getLogger(__name__)


class GenerationRunError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class TurnCapture:
    thread_id: str
    turn_id: str | None = None
    chunks: list[str] = field(default_factory=list)
    completed: asyncio.Future[str] | None = None
    approval_rejected: bool = False


class GenerationRunner:
    def __init__(
        self,
        codex: CodexAppServer,
        store: GenerationStore,
        settings: Settings,
    ) -> None:
        self.codex = codex
        self.store = store
        self.settings = settings
        self.refs = ViewerGitRefs(settings.git_executable)
        self.sources = SourceReferenceValidator(
            settings.git_executable, settings.viewer_source_max_file_bytes
        )
        self.semaphore = asyncio.Semaphore(settings.generation_max_concurrency)
        self.events: dict[UUID, EventBuffer] = {}
        self.captures: dict[str, TurnCapture] = {}
        self.tasks: dict[UUID, asyncio.Task[None]] = {}
        self.inspections: dict[UUID, GenerationPreflight] = {}
        codex.add_notification_handler(self._handle_notification)

    def event_buffer(self, job_id: UUID) -> EventBuffer:
        return self.events.setdefault(
            job_id, EventBuffer(self.settings.generation_event_buffer_size)
        )

    async def inspect_security(self) -> None:
        if not self.codex.connected:
            raise CodexConnectionError("Codex unavailable")
        try:
            await self.codex.ensure_generation_contract()
            inspection = GenerationPreflight(self.codex, uuid4())
            await inspection.inspect()
            account = await self.codex.request("account/read", {"refreshToken": False})
            inspection.assert_current()
            if not account.get("account") and account.get("requiresOpenaiAuth", True):
                from backend.app.codex import CodexRpcError

                raise CodexRpcError(-32000, "Authentication required")
        except CodexConnectionError:
            raise
        except Exception as exc:
            from backend.app.codex import CodexRpcError

            if isinstance(exc, CodexRpcError) and exc.code == -32000:
                raise
            LOGGER.warning(
                "Generation baseline rejected classification=%s method=%s reason=%s trace_id=%s",
                type(exc).__name__,
                getattr(exc, "method", "preflight"),
                str(exc) if isinstance(exc, GenerationSecurityError) else "rpc_failure",
                rpc_trace_id.get(),
            )
            raise GenerationSecurityError("baseline_failed") from exc

    async def execute(
        self,
        job_id: UUID,
        repository_path: Path,
        repository_github_url: str,
    ) -> None:
        rpc_trace_id.set(str(job_id))
        if not await self.store.set_running(job_id):
            return
        events = self.event_buffer(job_id)
        temporary_ref = generation_ref(job_id)
        new_ref: str | None = None
        try:
            await events.publish("job.started", {"job_id": str(job_id), "status": "running"})
            job = await self._job(job_id)
            if await self.refs.resolve(str(repository_path), "HEAD") != job.commit_sha:
                raise GenerationRunError(
                    "GENERATION_FAILED", "RepositoryのCommitが変更されました。", True
                )
            await self.refs.create(str(repository_path), temporary_ref, job.commit_sha)
            document = await asyncio.wait_for(
                self._generate(job, repository_path),
                timeout=self.settings.generation_timeout_seconds,
            )
            await self._phase(job_id, "validating_document")
            try:
                await self.sources.validate(
                    str(repository_path), job.commit_sha, document.source_references
                )
            except SourceReferenceError as exc:
                raise GenerationRunError(
                    "SOURCE_REFERENCE_INVALID",
                    "生成結果のソース参照を検証できませんでした。",
                    True,
                ) from exc
            await events.publish(
                "job.sources.validated",
                {
                    "job_id": str(job_id),
                    "paths": sorted({item.path for item in document.source_references}),
                },
            )
            await self._cancel_point(job_id)
            await self._phase(job_id, "rendering_html")
            html = render_viewer_document(document)
            await self._cancel_point(job_id)
            await self._phase(job_id, "sanitizing_html")
            try:
                html = sanitize_viewer_html(html, repository_github_url)
            except HtmlSanitizeError as exc:
                raise GenerationRunError(
                    "HTML_SANITIZE_FAILED", "Viewer HTMLを安全に保存できませんでした。", False
                ) from exc
            await self._cancel_point(job_id)
            self.inspections[job_id].assert_current()
            await self._phase(job_id, "saving_viewer")
            current = await self._job(job_id)
            viewer_id = current.viewer_id or uuid4()
            revision = (current.base_viewer_revision or 0) + 1
            new_ref = viewer_revision_ref(viewer_id, revision)
            await self.refs.create(str(repository_path), new_ref, current.commit_sha)
            now = current.updated_at
            viewer = ViewerModel(
                id=viewer_id,
                repository_id=current.repository_id,
                title=document.title,
                summary=document.summary,
                document_type=current.document_type,
                detail_level=current.detail_level,
                target_audience=current.target_audience,
                theme_slug=current.theme_slug,
                density=current.density,
                content_json=canonical_document_json(document),
                sanitized_html=html,
                request=current.request,
                additional_instruction=current.additional_instruction,
                commit_sha=current.commit_sha,
                renderer_version=self.settings.viewer_renderer_version,
                content_revision=revision,
                created_at=now,
                updated_at=now,
            )
            self.inspections[job_id].assert_current()
            saved = await self.store.save_viewer(
                job_id,
                viewer,
                current.base_viewer_revision,
                safety_check=self.inspections[job_id].assert_current,
            )
            if not saved:
                raise GenerationRunError("VIEWER_CHANGED", "Viewerの状態が変更されました。", True)
            await self.refs.delete(str(repository_path), temporary_ref)
            if current.base_viewer_revision:
                await self.refs.delete(
                    str(repository_path),
                    viewer_revision_ref(viewer_id, current.base_viewer_revision),
                )
            await events.publish(
                "job.completed", {"job_id": str(job_id), "viewer_id": str(viewer_id)}
            )
        except asyncio.CancelledError:
            await self._stop_job(job_id)
            await self.store.mark_terminal(job_id, GenerationStatus.CANCELLED)
            await events.publish("job.cancelled", {"job_id": str(job_id)})
            raise
        except (TimeoutError, CodexTimeoutError):
            await self._stop_job(job_id)
            await self._fail(job_id, "CODEX_TIMEOUT", "Viewer生成がタイムアウトしました。", True)
        except GenerationSecurityError as exc:
            LOGGER.warning(
                "Generation safety check failed job_id=%s trace_id=%s classification=%s",
                job_id,
                job_id,
                str(exc),
            )
            await self._stop_job(job_id)
            await self._fail(
                job_id,
                "CODEX_SANDBOX_UNSUPPORTED",
                "Codexの安全設定を確認できないため、生成を停止しました。",
                False,
            )
        except CodexConnectionError:
            await self._fail(job_id, "CODEX_UNAVAILABLE", "Codexとの接続が切断されました。", True)
        except GenerationRunError as exc:
            await self._fail(job_id, exc.code, str(exc), exc.retryable)
        except Exception:
            LOGGER.error("Generation failed job_id=%s trace_id=%s", job_id, job_id)
            await self._fail(job_id, "GENERATION_FAILED", "Viewerを生成できませんでした。", True)
        finally:
            inspection = self.inspections.pop(job_id, None)
            if inspection and inspection.thread_id and self.codex.connected:
                try:
                    await asyncio.wait_for(
                        self.codex.request(
                            "thread/unsubscribe", {"threadId": inspection.thread_id}
                        ),
                        timeout=5,
                    )
                except Exception:
                    await self.codex.discard_connection()
            if inspection and inspection.thread_id:
                self.captures.pop(inspection.thread_id, None)
            await self.refs.delete(str(repository_path), temporary_ref)
            terminal = await self.store.get_job(job_id)
            if new_ref and terminal and terminal.status != "completed":
                await self.refs.delete(str(repository_path), new_ref)
            self.tasks.pop(job_id, None)

    async def cancel(self, job: GenerationJobModel) -> None:
        if job.codex_thread_id and job.codex_turn_id:
            await self.codex.request(
                "turn/interrupt",
                {"threadId": job.codex_thread_id, "turnId": job.codex_turn_id},
            )
        elif task := self.tasks.get(job.id):
            task.cancel()

    async def _generate(self, job: GenerationJobModel, repository_path: Path):
        await self._phase(job.id, "starting_thread")
        inspection = GenerationPreflight(self.codex, job.id, repository_path)
        self.inspections[job.id] = inspection
        try:
            thread_id = await inspection.start_thread()
        except CodexTimeoutError as exc:
            if exc.method == "thread/start":
                await self.codex.discard_connection()
            raise GenerationSecurityError("preflight_timeout") from exc
        except CodexConnectionError:
            raise
        except Exception as exc:
            raise GenerationSecurityError("thread_preflight_failed") from exc
        capture = TurnCapture(thread_id=thread_id)
        self.captures[thread_id] = capture
        await self.store.set_phase(job.id, "analyzing_repository", codex_thread_id=thread_id)
        try:
            raw = await self._turn(
                job,
                capture,
                build_generation_prompt(job),
                inspection,
            )
            try:
                return parse_viewer_document(raw, self.settings.viewer_document_max_bytes)
            except (ValidationError, ValueError) as first_error:
                fields = _validation_fields(first_error)
                raw = await self._turn(
                    job,
                    capture,
                    build_schema_repair_prompt(fields),
                    inspection,
                )
                try:
                    return parse_viewer_document(raw, self.settings.viewer_document_max_bytes)
                except (ValidationError, ValueError) as exc:
                    raise GenerationRunError(
                        "DOCUMENT_SCHEMA_INVALID",
                        "生成結果の形式を検証できませんでした。",
                        True,
                    ) from exc
        finally:
            # On an uncertain/failed turn, stop it before removing the capture.
            if capture.completed and (
                capture.completed.cancelled()
                or not capture.completed.done()
                or capture.approval_rejected
            ):
                await self._stop_job(job.id)

    async def _turn(
        self,
        job: GenerationJobModel,
        capture: TurnCapture,
        prompt: str,
        inspection: GenerationPreflight,
    ) -> str:
        try:
            await inspection.recheck()
        except CodexConnectionError:
            raise
        except Exception as exc:
            raise GenerationSecurityError("turn_preflight_failed") from exc
        capture.turn_id = None
        capture.chunks.clear()
        capture.approval_rejected = False
        capture.completed = asyncio.get_running_loop().create_future()
        result = await self.codex.request(
            "turn/start",
            {
                "threadId": capture.thread_id,
                "input": [{"type": "text", "text": prompt}],
                "approvalPolicy": "never",
                "outputSchema": viewer_document_json_schema(),
            },
        )
        capture.turn_id = result["turn"]["id"]
        await self.store.set_phase(
            job.id,
            "analyzing_repository",
            codex_thread_id=capture.thread_id,
            codex_turn_id=capture.turn_id,
        )
        raw = await capture.completed
        inspection.assert_current()
        if capture.approval_rejected:
            raise GenerationSecurityError("permission_request_rejected")
        return raw

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "app_server/connected":
            try:
                await self.inspect_security()
            except Exception as exc:
                LOGGER.warning(
                    "Generation startup baseline unavailable classification=%s", type(exc).__name__
                )
            return
        if method == "app_server/disconnected":
            for capture in self.captures.values():
                if capture.completed and not capture.completed.done():
                    capture.completed.set_exception(
                        GenerationRunError(
                            "CODEX_UNAVAILABLE", "Codexとの接続が切断されました。", True
                        )
                    )
            return
        if method == "app_server/server_request_rejected":
            thread_id = params.get("threadId")
            captures = (
                [self.captures[thread_id]]
                if isinstance(thread_id, str) and thread_id in self.captures
                else self.captures.values()
            )
            for capture in captures:
                if capture.completed and not capture.completed.done():
                    capture.approval_rejected = True
                    capture.completed.set_exception(
                        GenerationSecurityError("permission_request_rejected")
                    )
            return
        thread_id = params.get("threadId")
        capture = self.captures.get(thread_id)
        if capture is None:
            return
        if method in {"item/started", "item/completed"}:
            item = params.get("item", {})
            if item.get("type") not in {"agentMessage", "reasoning", "plan", "commandExecution"}:
                self.codex.security_epoch += 1
                capture.approval_rejected = True
                if capture.completed and not capture.completed.done():
                    capture.completed.set_exception(GenerationSecurityError("unexpected_tool_item"))
                return
        turn_id = params.get("turnId") or params.get("turn", {}).get("id")
        if capture.turn_id and turn_id and capture.turn_id != turn_id:
            return
        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            if isinstance(delta, str):
                capture.chunks.append(delta)
        elif method == "turn/completed" and capture.completed and not capture.completed.done():
            items = params.get("turn", {}).get("items", [])
            if not isinstance(items, list) or any(
                not isinstance(item, dict)
                or item.get("type") not in {"agentMessage", "reasoning", "plan", "commandExecution"}
                for item in items
            ):
                self.codex.security_epoch += 1
                capture.approval_rejected = True
                capture.completed.set_exception(GenerationSecurityError("unexpected_tool_item"))
                return
            status = params.get("turn", {}).get("status")
            if status == "completed" and not capture.approval_rejected:
                capture.completed.set_result("".join(capture.chunks))
            else:
                capture.completed.set_exception(
                    GenerationRunError("CODEX_TURN_FAILED", "Codexによる調査が失敗しました。", True)
                )

    async def _stop_job(self, job_id: UUID) -> None:
        inspection = self.inspections.get(job_id)
        capture = self.captures.get(inspection.thread_id) if inspection else None
        if capture and self.codex.connected:
            if not capture.turn_id:
                await self.codex.discard_connection()
                return
            try:
                await asyncio.wait_for(
                    self.codex.request(
                        "turn/interrupt",
                        {
                            "threadId": capture.thread_id,
                            "turnId": capture.turn_id,
                        },
                    ),
                    timeout=5,
                )
            except Exception:
                pass
            # An interrupt response is only acknowledgement, not proof of completion.
            # Close the shared transport when completion was not safely observed.
            await self.codex.discard_connection()

    async def _phase(self, job_id: UUID, phase: str) -> None:
        if not await self.store.set_phase(job_id, phase):
            raise GenerationRunError(
                "GENERATION_FAILED", "Generation Jobの状態が変更されました。", True
            )
        await self.event_buffer(job_id).publish(
            "job.phase.changed", {"job_id": str(job_id), "phase": phase}
        )

    async def _cancel_point(self, job_id: UUID) -> None:
        if await self.store.is_cancel_requested(job_id):
            raise asyncio.CancelledError

    async def _job(self, job_id: UUID) -> GenerationJobModel:
        job = await self.store.get_job(job_id)
        if job is None:
            raise GenerationRunError("GENERATION_FAILED", "Generation Jobが見つかりません。", False)
        return job

    async def _fail(self, job_id: UUID, code: str, message: str, retryable: bool) -> None:
        if await self.store.mark_terminal(
            job_id,
            GenerationStatus.FAILED,
            error_code=code,
            error_message=message,
            retryable=retryable,
        ):
            await self.event_buffer(job_id).publish(
                "job.failed",
                {
                    "job_id": str(job_id),
                    "error": {
                        "code": code,
                        "message": message,
                        "retryable": retryable,
                        "trace_id": str(job_id),
                    },
                },
            )


def _validation_fields(error: Exception) -> list[str]:
    if isinstance(error, ValidationError):
        return [".".join(map(str, item["loc"])) for item in error.errors()]
    return ["document"]
