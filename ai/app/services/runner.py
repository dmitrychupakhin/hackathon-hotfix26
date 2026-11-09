import asyncio
import hashlib
import logging
import time

from app.config import Settings
from app.domain import TERMINAL, DomainError, Package, RunCreate, now, uid
from app.infrastructure.llm import Usage
from app.infrastructure.store import Store
from app.services.chat_context import (
    advance_chat_state,
    build_chat_context,
    model_history,
    record_evidence_references,
)
from app.services.harness import Harness, resolve_prompts
from app.services.model_limits import context_budget
from app.services.progress import Progress
from app.services.validation import unknown

logger = logging.getLogger(__name__)


def public_run(run: dict):
    return {key: value for key, value in run.items() if key != "snapshot"}


class Runner:
    def __init__(self, store: Store, model, settings: Settings, context_windows=None):
        self.store, self.model, self.settings = store, model, settings
        self.context_windows = dict(context_windows or {})
        self.semaphore = asyncio.Semaphore(settings.concurrent_runs)
        self.submission_lock = asyncio.Lock()
        self.cancellation_lock = asyncio.Lock()
        self.tasks: dict[str, asyncio.Task] = {}
        self.signals: dict[str, asyncio.Event] = {}
        self.started: set[str] = set()
        self.finalizing: set[str] = set()
        self.active_sessions: dict[str, str] = {}
        self.closing = False

    async def submit(
        self,
        request: RunCreate,
        owner: str,
        idempotency_key: str | None = None,
        package_override: Package | None = None,
        history_override: list[dict] | None = None,
        idempotency_fingerprint: str | None = None,
        user_system_prompt: str = "",
        plan_chat: bool = False,
    ):
        if self.closing:
            raise DomainError("shutting_down", "Service is shutting down", 503)
        request = request.model_copy(deep=True)
        request.model = request.model or self.settings.model
        request.base_url = request.base_url or self.settings.base_url
        if request.base_url not in self.settings.base_urls:
            raise DomainError(
                "provider_not_allowed",
                "Requested provider base URL is not enabled on this service",
                422,
            )
        digest = hashlib.sha256(
            (idempotency_fingerprint or request.model_dump_json()).encode()
        ).hexdigest()
        key_id = (
            hashlib.sha256(f"{owner}:{idempotency_key}".encode()).hexdigest()
            if idempotency_key
            else None
        )
        async with self.submission_lock:
            if key_id:
                try:
                    previous = await self.store.get("idempotency", key_id, owner)
                    if previous["digest"] != digest:
                        raise DomainError(
                            "idempotency_conflict",
                            "This key was already used with different input",
                            409,
                        )
                    return await self.store.get("run", previous["run_id"], owner)
                except DomainError as exc:
                    if exc.code != "not_found":
                        raise
            if len(self.tasks) >= self.settings.pending_runs:
                raise DomainError("queue_full", "Too many queued or running jobs", 429)
            session = None
            history = []
            chat_context = None
            if request.session_id:
                session = await self.store.get("session", request.session_id, owner)
                if request.session_id in self.active_sessions:
                    raise DomainError(
                        "session_busy", "A turn is already running in this session", 409
                    )
                if any(q.package_id != session["package_id"] for q in request.questions):
                    raise DomainError(
                        "session_package_mismatch", "Session is bound to another package", 422
                    )
            packages = []
            if package_override:
                if request.session_id or any(
                    q.package_id != package_override.id for q in request.questions
                ):
                    raise DomainError("package_mismatch", "Invalid external package", 422)
                packages = [package_override]
                history = history_override or []
            else:
                for package_id in dict.fromkeys(q.package_id for q in request.questions):
                    package = Package.model_validate(
                        await self.store.get("package", package_id, owner)
                    )
                    if not package.documents:
                        raise DomainError(
                            "empty_package", "Upload documents before starting a run", 422
                        )
                    packages.append(package)
            if session:
                chat_context = build_chat_context(session, packages[0])
                history = model_history(chat_context)
            templates = resolve_prompts(request.system_prompt, request.mode)
            additional = user_system_prompt or request.additional_instructions
            if additional:
                template_name = (
                    "chat"
                    if package_override
                    and request.mode == "plain"
                    and not package_override.documents
                    else request.mode
                )
                templates[template_name] += (
                    "\n\nДополнительные инструкции пользователя:\n" + additional
                )
            budget = context_budget(
                self.settings,
                request.model,
                self.context_windows if request.base_url == self.settings.base_url else {},
            )
            run = {
                "id": uid(),
                "status": "queued",
                "mode": request.mode,
                "model": request.model,
                "base_url": request.base_url,
                "context_budget": budget,
                "system_prompt_source": (
                    "not_used"
                    if request.mode in {"raw", "baseline"}
                    else "profile"
                    if request.system_prompt is not None or additional
                    else "builtin"
                ),
                "request": request.model_dump(mode="json"),
                "created_at": now(),
                "updated_at": now(),
                "prompt_hashes": {
                    name: hashlib.sha256(text.encode()).hexdigest()
                    for name, text in templates.items()
                },
                "source_revisions": {p.id: p.revision for p in packages},
                "snapshot": {
                    "packages": [p.model_dump() for p in packages],
                    "history": history,
                    "chat_context": chat_context,
                    "prompts": templates,
                    "context_budget": budget,
                    "base_url": request.base_url,
                    "chat_message": request.questions[0].model_dump() if plan_chat else None,
                },
                "result": {"answers": [], "raw_outputs": []},
                "metrics": Usage().snapshot(self.settings),
                "error": None,
                "cancel_requested": False,
            }
            await self.store.create("run", run, owner)
            await self.store.append_event(
                run["id"], "run.queued", {"questions": len(request.questions)}
            )
            if key_id:
                await self.store.create(
                    "idempotency", {"id": key_id, "digest": digest, "run_id": run["id"]}, owner
                )
            if session:
                advance_chat_state(
                    session, packages[0], "\n".join(q.text for q in request.questions)
                )
                session["messages"].append(
                    {
                        "id": uid(),
                        "role": "user",
                        "content": "\n".join(q.text for q in request.questions),
                        "run_id": run["id"],
                        "created_at": now(),
                    }
                )
                await self.store.save("session", session, owner)
                self.active_sessions[session["id"]] = run["id"]
            self.signals[run["id"]] = asyncio.Event()
            task = asyncio.create_task(self._run(run, owner), name=f"ai-run-{run['id']}")
            self.tasks[run["id"]] = task
            task.add_done_callback(lambda _: self.tasks.pop(run["id"], None))
            return run

    async def _run(self, run, owner):
        run_id = run["id"]
        self.started.add(run_id)
        started = time.monotonic()
        engine = None

        async def progress_emit(event_type, data):
            await self.store.append_event(run_id, event_type, data)

        progress = Progress(progress_emit)
        request = RunCreate.model_validate(run["request"])
        status, error = "completed", None
        try:
            async with (
                asyncio.timeout(min(request.options.timeout_seconds, self.settings.run_timeout)),
                self.semaphore,
            ):
                await self.store.patch_run(
                    run_id,
                    owner,
                    {"status": "running", "started_at": now()},
                    "run.started",
                    {"model": request.model, "mode": request.mode},
                )

                async def emit(event_type, data):
                    if event_type == "answer.completed":
                        await self.store.patch_run(
                            run_id,
                            owner,
                            {
                                "result": {
                                    "answers": [
                                        a.model_dump(mode="json") for a in engine.accepted.values()
                                    ],
                                    "raw_outputs": engine.raw_outputs,
                                    "evidence_audit": engine.audit_state(),
                                },
                                "metrics": engine.usage.snapshot(self.settings),
                            },
                            event_type,
                            data,
                        )
                    else:
                        await self.store.append_event(run_id, event_type, data)
                    await progress.handle(event_type, data)

                run_settings = self.settings.model_copy(
                    update={
                        "context_window": run["snapshot"]["context_budget"]["context_window_tokens"]
                    }
                )
                engine = Harness(self.model, run_settings, request, emit, self.signals[run_id])
                engine.chat_return_code_checked = bool(run["snapshot"].get("chat_message"))
                engine.templates = run["snapshot"]["prompts"]
                packages = [Package.model_validate(p) for p in run["snapshot"]["packages"]]
                history = run["snapshot"]["history"]
                if run["snapshot"].get("chat_message"):
                    original = request.questions[0]
                    request.questions = await engine.plan_chat(original)
                    await self.store.patch_run(
                        run_id,
                        owner,
                        {"request": request.model_dump(mode="json")},
                        "chat.planned",
                        {"units": len(request.questions)},
                    )
                    # Every unit keeps shared conditions from the complete user message.
                    history = [*history, {"role": "user", "content": original.text}]
                await engine.execute(packages, history)
        except asyncio.CancelledError:
            status = "interrupted" if self.closing else "cancelled"
            error = {
                "code": "service_shutdown" if self.closing else "cancelled",
                "message": "Run stopped; incomplete answers are marked unknown.",
            }
        except TimeoutError:
            status, error = "failed", {"code": "run_timeout", "message": "Run deadline exceeded"}
        except DomainError as exc:
            status, error = "failed", {"code": exc.code, "message": exc.message}
        except Exception:
            logger.exception("AI run failed: %s", run_id)
            status, error = (
                "failed",
                {"code": "internal_error", "message": "Unexpected execution error"},
            )
        finally:
            self.finalizing.add(run_id)
            finalization = asyncio.create_task(
                self._finalize(run_id, owner, request, engine, status, error, started, progress)
            )
            try:
                while not finalization.done():
                    try:
                        await asyncio.shield(finalization)
                    except asyncio.CancelledError:
                        # Cancellation may race with completion or shutdown. Keep the
                        # runner task alive until its persistence task has completed.
                        continue
                finalization.result()
            finally:
                if request.session_id:
                    self.active_sessions.pop(request.session_id, None)
                self.signals.pop(run_id, None)
                self.started.discard(run_id)
                self.finalizing.discard(run_id)

    async def _finalize(self, run_id, owner, request, engine, status, error, started, progress):
        await progress.close(status, error)
        metrics = (
            engine.usage.snapshot(self.settings) if engine else Usage().snapshot(self.settings)
        )
        metrics["elapsed_seconds"] = round(time.monotonic() - started, 3)
        metrics["elapsed_includes_queue"] = True
        if engine:
            metrics["context_window_tokens_final"] = engine.context_window
            metrics["context_reductions"] = engine.context_reductions
        result = {
            "answers": [
                a.model_dump(mode="json")
                for a in engine.results(error["code"] if error else "No accepted answer")
            ]
            if engine
            else [
                unknown(q.id, error["code"] if error else "Run did not start").model_dump(
                    mode="json"
                )
                for q in request.questions
            ],
            "raw_outputs": engine.raw_outputs if engine else [],
            "evidence_audit": engine.audit_state() if engine else {},
        }
        metrics["fallback_answers"] = sum(a["origin"] == "fallback" for a in result["answers"])
        if request.session_id:
            session = await self.store.get("session", request.session_id, owner)
            record_evidence_references(session, result["answers"], run_id)
            session["messages"].append(
                {
                    "id": uid(),
                    "role": "assistant",
                    "content": "\n".join(
                        a.get("clarification_question") or a["answer"] or a["status"] or ""
                        for a in result["answers"]
                    ),
                    "run_id": run_id,
                    "created_at": now(),
                }
            )
            await self.store.save("session", session, owner)

        await self.store.patch_run(
            run_id,
            owner,
            {
                "status": status,
                "result": result,
                "metrics": metrics,
                "error": error,
                "finished_at": now(),
            },
            f"run.{status}",
            {"status": status, "metrics": metrics, "error": error},
        )

    async def cancel(self, run_id, owner):
        async with self.cancellation_lock:
            run = await self.store.get("run", run_id, owner)
            if (
                run["status"] in TERMINAL
                or run.get("cancel_requested")
                or run_id in self.finalizing
            ):
                return run
            await self.store.patch_run(
                run_id, owner, {"cancel_requested": True}, "run.cancel_requested", {}
            )
            signal = self.signals.get(run_id)
            if signal:
                signal.set()
            task = self.tasks.get(run_id)
            if task:
                task.cancel()
            if run_id not in self.started:
                await self.store.patch_run(
                    run_id,
                    owner,
                    {
                        "status": "cancelled",
                        "finished_at": now(),
                        "result": {
                            "answers": [
                                unknown(q["id"], "cancelled_before_start").model_dump(mode="json")
                                for q in run["request"]["questions"]
                            ],
                            "raw_outputs": [],
                        },
                    },
                    "run.cancelled",
                    {"status": "cancelled"},
                )
                if run["request"].get("session_id"):
                    self.active_sessions.pop(run["request"]["session_id"], None)
                self.signals.pop(run_id, None)
            return await self.store.get("run", run_id, owner)

    async def close(self):
        self.closing = True
        tasks = list(self.tasks.values())
        for run_id, task in list(self.tasks.items()):
            if run_id not in self.finalizing and not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
