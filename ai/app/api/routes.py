import asyncio
import hashlib
import time
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth import authenticate, owner
from app.domain import (
    TERMINAL,
    Answer,
    CandidateBatch,
    ChatMessage,
    DatasetCreate,
    DomainError,
    GenerationSettings,
    HarnessStep,
    Package,
    PackageCreate,
    Question,
    RunCreate,
    RunOptions,
    SessionCreate,
    TextDocument,
    now,
    uid,
)
from app.infrastructure.files.cache_models import SourceFile
from app.services.comparison_inputs import parse_inputs
from app.services.documents import spans_for, with_documents
from app.services.evaluation import compare_evaluations, evaluate_run, export_csv
from app.services.file_imports import artifact_document
from app.services.harness import prompt_versions
from app.services.importing import import_archive
from app.services.model_limits import context_budget
from app.services.runner import public_run
from app.services.tools import ToolBox, tool_schemas

router = APIRouter(prefix="/api/v1")
Owner = Annotated[str, Depends(owner)]


class ReferenceAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    package: str
    status: Literal["ответ", "расхождение", "нет в документах"]
    kind: Literal["num", "date", "yes", "no", "all_kw", "absent"]
    expected: list[Any]
    type: str


class EvaluationRequest(BaseModel):
    reference_answers: list[ReferenceAnswer] = Field(min_length=1, max_length=200)


class ComparisonRequest(BaseModel):
    before_evaluation_id: str
    after_evaluation_id: str


class ComparisonFilesRequest(BaseModel):
    questions_file_id: UUID
    answers_file_id: UUID
    model: str = Field(min_length=1, max_length=150)
    document_file_ids: list[UUID] = Field(default_factory=list, max_length=64)


class ComparisonPair(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=12000,
        description="Reference question text, preserved without semantic rewriting.",
    )
    status: Literal["ответ", "расхождение", "нет в документах"]
    kind: Literal["num", "date", "yes", "no", "all_kw", "absent"]
    expected: list[Any]
    type: str = Field(min_length=1)


class ComparisonPairs(BaseModel):
    items: list[ComparisonPair] = Field(min_length=1, max_length=200)


class ParsedComparisonInputs(BaseModel):
    questions: list[Question]
    reference_answers: list[ReferenceAnswer]
    package_ids: dict[str, str] = Field(default_factory=dict)


class DatasetRun(GenerationSettings):
    pass


class PreviousChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRunRequest(BaseModel):
    chat_id: UUID
    message_id: UUID
    question: str = Field(min_length=1, max_length=12000, description="Complete user message. With documents the model selects up to 50 independently checked answer units; no line/CSV/keyword question splitter is used. Code checks lossless coverage and assigns message_id.q01, .q02 IDs. One unit keeps message_id. The entire original message remains shared context; planning shares the run's call/time budget. Without documents the message is answered directly.")
    model: str = Field(min_length=1, max_length=150)
    file_ids: list[UUID] = Field(default_factory=list, max_length=64)
    history: list[PreviousChatMessage] = Field(default_factory=list, max_length=20)
    system_prompt: str = Field(default="", max_length=8000)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=10)


class Event(BaseModel):
    seq: int
    run_id: str
    type: str
    data: HarnessStep | dict
    created_at: str


class APIError(BaseModel):
    code: str
    message: str


class RunResult(BaseModel):
    answers: list[Answer]
    raw_outputs: list[dict]
    evidence_audit: dict = Field(default_factory=dict)


class RunMetrics(BaseModel):
    model_config = ConfigDict(extra="allow")
    model_calls: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    known_total_tokens: int
    missing_usage_calls: int
    returned_models: list[str]
    cost: float | None
    currency: str | None
    price_snapshot: dict[str, float | None]
    elapsed_seconds: float | None = None
    elapsed_includes_queue: bool | None = None
    fallback_answers: int | None = None
    context_window_tokens_final: int | None = None
    context_reductions: int | None = None


class RunView(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    status: str
    mode: str
    model: str
    base_url: str | None = None
    system_prompt_source: Literal["profile", "builtin", "not_used"] | None = None
    context_budget: dict | None = None
    request: RunCreate
    result: RunResult
    metrics: RunMetrics
    error: APIError | None
    prompt_hashes: dict[str, str]
    source_revisions: dict[str, str]
    created_at: str
    updated_at: str


def package_view(package: Package):
    result = package.model_dump()
    result["documents"] = [
        {k: v for k, v in d.model_dump().items() if k != "text"} | {"characters": len(d.text)}
        for d in package.documents
    ]
    return result


@router.post("/comparison-inputs/parse", response_model=ParsedComparisonInputs, tags=["Evaluation"])
async def parse_comparison_files(
    body: ComparisonFilesRequest,
    request: Request,
    user: Owner,
    idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
):
    if idempotency_key is None:
        return await _prepare_comparison_files(body, request, user)
    key = hashlib.sha256((user + ":comparison-inputs:" + idempotency_key).encode()).hexdigest()
    digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    async with request.app.state.comparison_input_lock:
        try:
            cached = await request.app.state.store.get("comparison_inputs", key, user)
        except DomainError as exc:
            if exc.status != 404:
                raise
        else:
            if cached["digest"] != digest:
                raise DomainError(
                    "idempotency_conflict", "Input key already used for different files", 409
                )
            return ParsedComparisonInputs.model_validate(cached["value"])
        result = await _prepare_comparison_files(body, request, user)
        await request.app.state.store.create(
            "comparison_inputs",
            {"id": key, "digest": digest, "value": result.model_dump(mode="json")},
            user,
        )
        return result


async def _prepare_comparison_files(body: ComparisonFilesRequest, request: Request, user: str):
    """Read organizer CSV/JSON unchanged. Gold never enters a generation prompt.

    Optional documents: one ZIP retaining packages/P01...P06, or flat files for
    exactly one procurement. Unknown mappings are rejected rather than guessed.
    """
    texts = []
    input_hashes = set()
    async with asyncio.timeout(request.app.state.settings.file_import_timeout):
        for file_id in (body.questions_file_id, body.answers_file_id):
            source = SourceFile.model_validate(
                await request.app.state.store.source_file(str(file_id), user)
            )
            input_hashes.add(source.sha256)
            artifact = await request.app.state.file_cache.prepare(source, user)
            if artifact.parsed.partial:
                raise DomainError(
                    "partial_comparison_file",
                    "Questions and gold must be extracted completely",
                    422,
                )
            texts.append(artifact.parsed.text)
        if sum(map(len, texts)) > 120000:
            raise DomainError(
                "comparison_text_too_large", "Questions and gold exceed 120000 characters", 413
            )
        questions, references = parse_inputs(*texts)
        refs = [ReferenceAnswer.model_validate(r) for r in references]
        mapping = {}
        sources = [
            SourceFile.model_validate(await request.app.state.store.source_file(str(fid), user))
            for fid in body.document_file_ids
        ]
        if any(
            s.sha256 in input_hashes
            or s.filename.lower() in {"answers_public.json", "questions.csv", "check.py"}
            for s in sources
        ):
            raise DomainError(
                "evaluation_file_in_sources",
                "Questions/gold/checker cannot be generation sources",
                422,
            )
        codes = {q.package_id for q in questions}
        zipped = [s for s in sources if s.filename.lower().endswith(".zip")]
        if zipped:
            if len(sources) != 1:
                raise DomainError("ambiguous_documents", "Use one ZIP or flat files, not both", 422)
            raw = await asyncio.to_thread(request.app.state.file_cache._read_source, zipped[0])
            original_questions = [
                {"id": q.id, "package": q.package_id, "question": q.text} for q in questions
            ]
            dataset = import_archive(
                raw, request.app.state.settings, questions_override=original_questions
            )
            if {p.code for p in dataset.packages} != codes:
                raise DomainError(
                    "package_mapping_mismatch", "ZIP packages must exactly match questions.csv", 422
                )
            saved = await save_dataset(dataset, request, user)
            mapping = saved["packages"]
        elif sources:
            if len(codes) != 1:
                raise DomainError(
                    "package_mapping_required",
                    "Multiple procurements require ZIP packages/<code>/documents",
                    422,
                )
            package = Package(code=next(iter(codes)), name="Comparison procurement")
            documents = []
            for source in sources:
                artifact = await request.app.state.file_cache.prepare(source, user)
                document = artifact_document(artifact, source, document_id=source.id)
                if any(d.name == document.name for d in documents):
                    raise DomainError(
                        "duplicate_filename",
                        "Document filenames must be unique within a procurement",
                        422,
                    )
                documents.append(document)
            package = with_documents(package, documents, request.app.state.settings)
            await request.app.state.store.create("package", package.model_dump(), user)
            mapping = {package.code: package.id}
    return ParsedComparisonInputs(questions=questions, reference_answers=refs, package_ids=mapping)


@router.get("/info", tags=["Service"])
async def service_info(request: Request, user: Owner):
    settings = request.app.state.settings
    budgets = {
        model: context_budget(settings, model, request.app.state.runner.context_windows)
        for model in sorted({settings.model, *request.app.state.runner.context_windows})
    }

    return {
        "service": "onsoft-ai",
        "version": "0.1.0",
        "models": sorted(budgets),
        "default_model": settings.model,
        "provider_configured": bool(settings.api_key.get_secret_value()),
        "provider_models": sorted(request.app.state.runner.context_windows),
        "model_catalog_available": bool(request.app.state.runner.context_windows),
        "default_base_url": settings.base_url,
        "allowed_base_urls": sorted(settings.base_urls),
        "modes": ["plain", "harness", "raw", "baseline"],
        "recommended_modes": ["plain", "harness"],
        "prompt_hashes": prompt_versions(),
        "limits": {
            "run_defaults": RunOptions().model_dump(),
            "max_model_calls": settings.max_model_calls,
            "run_timeout_seconds": settings.run_timeout,
            "chat_document_timeout_seconds": min(settings.run_timeout, 3600),
            "chat_plain_timeout_seconds": min(settings.run_timeout, RunOptions().timeout_seconds),
            "context_window_tokens": budgets[settings.model]["context_window_tokens"],
            "configured_context_cap_tokens": settings.context_window,
            "max_context_reductions": settings.max_context_reductions,
            "max_output_tokens": settings.max_output_tokens,
            "max_tool_calls_per_response": 16,
            "concurrent_runs": settings.concurrent_runs,
            "concurrent_file_imports": settings.concurrent_runs,
            "file_import_timeout_seconds": settings.file_import_timeout,
            "file_parse_timeout_seconds": request.app.state.file_cache.ingestor.limits.timeout_seconds,
            "max_upload_bytes": settings.max_upload_bytes,
            "max_provider_request_bytes": 2 * 1024 * 1024,
            "max_http_body_bytes": settings.max_package_bytes * 4,
            "max_package_bytes": settings.max_package_bytes,
            "max_documents_per_package": 64,
            "chunk_target_tokens": settings.chunk_target_tokens,
            "chunk_overlap_tokens": settings.chunk_overlap_tokens,
            "pending_runs": settings.pending_runs,
            "ws_ticket_ttl_seconds": 120,
            "ws_heartbeat_seconds": 15,
            "min_context_window_tokens": 4096,
            "file_parse_memory_mb": request.app.state.file_cache.ingestor.limits.memory_mb,
            "file_parse_max_pages": request.app.state.file_cache.ingestor.limits.max_pages,
        },
        "model_context_budgets": budgets,
        "progress": {"event_type": "harness.step", "schema_version": 1},
        "storage": {
            "engine": "postgresql" if settings.database_url.get_secret_value() else "sqlite-test",
            "schema": "ai",
            "file_source": "shared_catalog_and_readonly_volume",
        },
        "authentication": "service-key"
        if settings.service_key.get_secret_value()
        else "local-development",
    }


@router.post(
    "/chat-runs", status_code=202, response_model=RunView, tags=["Chat"],
    description=(
        "Chats with documents use AI_RUN_TIMEOUT_SECONDS (default 1200 seconds), "
        "capped at 3600 seconds, for the complete harness run including planning and checking. "
        "Chats without documents retain the 600-second default. The configured server "
        "deadline remains an upper bound in both modes. Effective limits are in GET /info. "
        "Independent verification retries a transient provider failure once. In document chats, "
        "if that provider remains unavailable, factual answers that passed code checks retain "
        "their text and citations, with reason=independent_review_incomplete and a failed "
        "review_unavailable check. This does not mark AI verification as passed. "
        "Absence claims and comparison runs still require the independent verification."
    ),
)
async def create_chat_run(
    body: ChatRunRequest,
    request: Request,
    user: Owner,
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    package = Package(id=f"chat-{body.chat_id}", code="CHAT", name="Чат")
    documents = []
    try:
        async with asyncio.timeout(request.app.state.settings.file_import_timeout):
            for file_id in body.file_ids:
                source = SourceFile.model_validate(
                    await request.app.state.store.source_file(str(file_id), user)
                )
                artifact = await request.app.state.file_cache.prepare(source, user)
                document = artifact_document(artifact, source, document_id=str(file_id))
                if any(item.name == document.name for item in documents):
                    document.name = f"{source.filename[:160]} ({file_id})"
                documents.append(document)
    except TimeoutError:
        raise DomainError(
            "file_import_timeout", "File preparation exceeded the time limit", 422
        ) from None
    if documents:
        package = with_documents(package, documents, request.app.state.settings)
    run = RunCreate(
        mode="harness" if documents else "plain",
        model=body.model,
        questions=[Question(id=str(body.message_id), package_id=package.id, text=body.question)],
        options=RunOptions(
            # A full document scan plus independent checking needs the server's
            # document-run budget, rather than the short plain-chat default.
            timeout_seconds=min(3600, max(1, request.app.state.settings.run_timeout))
        ) if documents else RunOptions(),
    )
    return public_run(
        await request.app.state.runner.submit(
            run,
            user,
            idempotency_key,
            package_override=package,
            history_override=[message.model_dump() for message in body.history],
            idempotency_fingerprint=body.model_dump_json(),
            user_system_prompt=body.system_prompt,
            plan_chat=bool(documents),
        )
    )


class FilePreview(BaseModel):
    file_id: str
    name: str
    format: Literal["pdf", "docx", "txt", "md"]
    text: str
    text_sha256: str
    original_sha256: str
    version: str
    locations: list[dict]
    partial: bool
    warnings: list[str]
    offset_unit: Literal["unicode_code_points"] = "unicode_code_points"


@router.get("/files/{file_id}/preview", response_model=FilePreview, tags=["File imports"])
async def preview_file(
    file_id: UUID,
    request: Request,
    user: Owner,
    text_sha256: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
    version: str | None = Query(default=None, max_length=128),
):
    """Owner-scoped canonical extraction. Offsets use Unicode code points, exclusive end.

    Expected hash/version prevent navigating a quote against changed source text.
    This endpoint is service-key authenticated and returns no storage paths.
    """
    from pathlib import Path

    source = SourceFile.model_validate(
        await request.app.state.store.source_file(str(file_id), user)
    )
    if version is not None and version != source.version:
        raise DomainError("stale_citation", "Document version changed; request a new answer", 409)
    suffix = Path(source.filename).suffix.lower().lstrip(".")
    try:
        async with asyncio.timeout(request.app.state.settings.file_import_timeout):
            artifact = await request.app.state.file_cache.prepare(source, user)
    except TimeoutError:
        raise DomainError(
            "file_import_timeout", "File preparation exceeded the time limit", 422
        ) from None
    except DomainError as exc:
        if suffix != "pdf" or exc.code not in {"ocr_required", "ocr_unavailable", "ocr_empty_text"}:
            raise
        # A valid scanned PDF can still be viewed without pretending it was read.
        empty_hash = hashlib.sha256(b"").hexdigest()
        if text_sha256 is not None and text_sha256 != empty_hash:
            raise DomainError(
                "stale_citation", "No matching extracted text is available", 409
            ) from None
        return FilePreview(
            file_id=source.id,
            name=source.filename,
            format="pdf",
            text="",
            text_sha256=empty_hash,
            original_sha256=source.sha256,
            version=source.version,
            locations=[],
            partial=True,
            warnings=[exc.code],
        )
    parsed = artifact.parsed
    digest = hashlib.sha256(parsed.text.encode("utf-8")).hexdigest()
    if (text_sha256 is not None and text_sha256 != digest) or (
        version is not None and version != source.version
    ):
        raise DomainError(
            "stale_citation",
            "Document version or extracted text changed; request a new answer",
            409,
        )
    return FilePreview(
        file_id=source.id,
        name=source.filename,
        format=suffix if suffix in {"pdf", "docx", "txt", "md"} else "txt",
        text=parsed.text,
        text_sha256=digest,
        original_sha256=source.sha256,
        version=source.version,
        locations=[item.model_dump(exclude_none=True) for item in parsed.locations],
        partial=parsed.partial,
        warnings=parsed.warnings,
    )


@router.get("/capabilities", tags=["Service"])
async def capabilities(request: Request, user: Owner):
    return {
        "tools": tool_schemas(CandidateBatch.model_json_schema()),
        "file_ingestion": {
            "source": "postgres_catalog_and_volume",
            "ocr_enabled": request.app.state.settings.ocr_enabled,
            "formats": ["txt", "md", "csv", "json", "html", "pdf", "docx", "pptx", "xlsx"],
            "ocr_formats": ["png", "jpg", "jpeg", "tiff", "bmp", "webp"],
            "by_id_path": "/api/v1/packages/{id}/documents/by-id",
        },
        "mandatory_checks": [
            {
                "code": "quote",
                "method": "code",
                "description": "Evidence ID, package, source hash and exact original quotation",
            },
            {
                "code": "numbers",
                "method": "code",
                "description": "Numbers occur in evidence or in a verified calculation",
            },
            {
                "code": "calculation",
                "method": "code",
                "description": "Decimal arithmetic and evidence for every operand",
            },
            {
                "code": "conflict_evidence",
                "method": "code",
                "description": "At least two distinct original spans for a conflict",
            },
            {
                "code": "coverage",
                "method": "code",
                "description": "Full successfully read package before asserting absence",
            },
        ],
        "semantic_review": {
            "method": "llm",
            "enabled_by_default": True,
            "checks": [
                "subject_and_field",
                "units_and_conditions",
                "amendment_scope",
                "unresolved_conflicts",
                "negation_vs_absence",
            ],
            "limitation": "A reviewer model can also be wrong. Passing checks is not a proof of truth.",
        },
    }


@router.post("/packages", status_code=201, tags=["Packages"])
async def create_package(body: PackageCreate, request: Request, user: Owner):
    package = Package(**body.model_dump())
    await request.app.state.store.create("package", package.model_dump(), user)
    return package_view(package)


@router.get("/packages", tags=["Packages"])
async def list_packages(
    request: Request, user: Owner, limit: int = Query(default=100, ge=1, le=500)
):
    rows = await request.app.state.store.list("package", user, limit)
    return {"items": [package_view(Package.model_validate(row)) for row in rows]}


@router.get("/packages/{package_id}", tags=["Packages"])
async def get_package(package_id: str, request: Request, user: Owner):
    return package_view(
        Package.model_validate(await request.app.state.store.get("package", package_id, user))
    )


async def append_documents(request, user, package_id, additions):
    async with request.app.state.mutation_lock:
        package = Package.model_validate(
            await request.app.state.store.get("package", package_id, user)
        )
        package = with_documents(package, additions, request.app.state.settings)
        await request.app.state.store.save("package", package.model_dump(), user)
        return package_view(package)


async def parse_upload(request, user, raw, name, media_type="application/octet-stream"):
    document_id = uid()
    artifact = await request.app.state.file_cache.prepare_bytes(
        raw, name, user, media_type, document_id
    )
    return artifact_document(artifact, document_id=document_id)


@router.post("/packages/{package_id}/documents/text", status_code=201, tags=["Packages"])
async def add_text_document(package_id: str, body: TextDocument, request: Request, user: Owner):
    await request.app.state.store.get("package", package_id, user)
    addition = await parse_upload(request, user, body.text.encode(), body.name, "text/plain")
    return await append_documents(request, user, package_id, [addition])


@router.post("/packages/{package_id}/documents", status_code=201, tags=["Packages"])
async def upload_documents(
    package_id: str, request: Request, user: Owner, files: list[UploadFile] = File(...)
):
    await request.app.state.store.get("package", package_id, user)
    settings = request.app.state.settings
    if not 1 <= len(files) <= 64:
        raise DomainError("invalid_file_count", "Provide 1 to 64 files", 422)
    additions = []
    async with asyncio.timeout(settings.file_import_timeout):
        for upload in files:
            raw = await upload.read(settings.max_upload_bytes + 1)
            if len(raw) > settings.max_upload_bytes:
                raise DomainError("file_too_large", "File exceeds size limit", 413)
            additions.append(
                await parse_upload(
                    request,
                    user,
                    raw,
                    upload.filename or "document.txt",
                    upload.content_type or "application/octet-stream",
                )
            )
    return await append_documents(request, user, package_id, additions)


class FileImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_ids: list[str] = Field(
        min_length=1,
        max_length=64,
        description="Owner-scoped IDs registered by backend in shared PostgreSQL ai.files. No paths or URLs.",
    )

    @field_validator("file_ids")
    @classmethod
    def valid_ids(cls, values):
        from app.infrastructure.files.models import validate_file_id

        if len(set(values)) != len(values):
            raise ValueError("File IDs must be unique")
        for value in values:
            try:
                validate_file_id(value)
            except DomainError as exc:
                raise ValueError(exc.message) from None
        return values


class FileImportView(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    package_id: str
    file_ids: list[str]
    status: str
    processed: int
    total: int
    documents: list[dict]
    error: dict | None
    created_at: str
    updated_at: str


@router.post(
    "/packages/{package_id}/documents/by-id",
    status_code=202,
    response_model=FileImportView,
    tags=["File imports"],
)
async def import_file_ids(package_id: str, body: FileImportRequest, request: Request, user: Owner):
    return await request.app.state.file_imports.submit(package_id, body.file_ids, user)


@router.get("/file-imports/{import_id}", response_model=FileImportView, tags=["File imports"])
async def file_import_status(import_id: str, request: Request, user: Owner):
    return await request.app.state.store.get("file_import", import_id, user)


@router.post(
    "/file-imports/{import_id}/cancel", response_model=FileImportView, tags=["File imports"]
)
async def cancel_file_import(import_id: str, request: Request, user: Owner):
    return await request.app.state.file_imports.cancel(import_id, user)


@router.get("/file-imports/{import_id}/events", response_model=list[Event], tags=["File imports"])
async def file_import_events(
    import_id: str,
    request: Request,
    user: Owner,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return await request.app.state.store.events(import_id, user, after, limit, kind="file_import")


@router.post("/file-imports/{import_id}/ws-ticket", tags=["File imports"])
async def file_import_ticket(import_id: str, request: Request, user: Owner):
    await request.app.state.store.get("file_import", import_id, user)
    ticket, expires = request.app.state.tickets.issue("file-import:" + import_id, user)
    return {"ticket": ticket, "expires_at": expires, "path": f"/api/v1/file-imports/{import_id}/ws"}


@router.websocket("/file-imports/{import_id}/ws")
async def file_import_ws(
    websocket: WebSocket, import_id: str, after: int = 0, ticket: str | None = None
):
    await stream_events(websocket, import_id, after, ticket, kind="file_import")


@router.get("/packages/{package_id}/documents/{document_id}", tags=["Packages"])
async def read_document(package_id: str, document_id: str, request: Request, user: Owner):
    package = Package.model_validate(await request.app.state.store.get("package", package_id, user))
    for doc in package.documents:
        if doc.id == document_id:
            return {
                **doc.model_dump(),
                "spans": [
                    s.model_dump() for s in spans_for(package).values() if s.document_id == doc.id
                ],
            }
    raise DomainError("not_found", "Document not found", 404)


@router.post("/packages/{package_id}/search", tags=["Packages"])
async def search(package_id: str, body: SearchRequest, request: Request, user: Owner):
    package = Package.model_validate(await request.app.state.store.get("package", package_id, user))
    return ToolBox(package).search(body.query, body.limit)


async def save_dataset(body: DatasetCreate, request: Request, user: str):
    prepared = []
    for item in body.packages:
        package = Package(code=item.code, name=item.name)
        additions = [
            await parse_upload(request, user, d.text.encode(), d.name, "text/plain")
            for d in item.documents
        ]
        prepared.append(with_documents(package, additions, request.app.state.settings))
    mapping = {p.code: p.id for p in prepared}
    dataset = {
        "id": uid(),
        "name": body.name,
        "packages": mapping,
        "questions": [
            Question(id=q.id, package_id=mapping[q.package], text=q.question).model_dump()
            for q in body.questions
        ],
        "created_at": now(),
    }
    await request.app.state.store.create_many(
        [("package", p.model_dump()) for p in prepared] + [("dataset", dataset)], user
    )
    return dataset


@router.post("/datasets", status_code=201, tags=["Datasets"])
async def create_dataset(body: DatasetCreate, request: Request, user: Owner):
    return await save_dataset(body, request, user)


@router.post("/datasets/import", status_code=201, tags=["Datasets"])
async def upload_dataset(request: Request, user: Owner, file: UploadFile = File(...)):
    raw = await file.read(request.app.state.settings.max_package_bytes + 1)
    dataset = import_archive(raw, request.app.state.settings)
    return await save_dataset(dataset, request, user)


@router.get("/datasets/{dataset_id}", tags=["Datasets"])
async def get_dataset(dataset_id: str, request: Request, user: Owner):
    return await request.app.state.store.get("dataset", dataset_id, user)


@router.post("/datasets/{dataset_id}/runs", status_code=202, response_model=RunView, tags=["Runs"])
async def run_dataset(
    dataset_id: str,
    body: DatasetRun,
    request: Request,
    user: Owner,
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    dataset = await request.app.state.store.get("dataset", dataset_id, user)
    run = RunCreate(**body.model_dump(), questions=dataset["questions"])
    return public_run(await request.app.state.runner.submit(run, user, idempotency_key))


@router.post("/runs", status_code=202, response_model=RunView, tags=["Runs"])
async def create_run(
    body: RunCreate,
    request: Request,
    user: Owner,
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    return public_run(await request.app.state.runner.submit(body, user, idempotency_key))


@router.get("/runs", tags=["Runs"])
async def list_runs(request: Request, user: Owner, limit: int = Query(default=100, ge=1, le=500)):
    return {
        "items": [public_run(r) for r in await request.app.state.store.list("run", user, limit)]
    }


@router.get("/runs/{run_id}", response_model=RunView, tags=["Runs"])
async def get_run(run_id: str, request: Request, user: Owner):
    return public_run(await request.app.state.store.get("run", run_id, user))


@router.get("/runs/{run_id}/inputs", tags=["Runs"])
async def get_run_inputs(run_id: str, request: Request, user: Owner):
    run = await request.app.state.store.get("run", run_id, user)
    return {
        "request": run["request"],
        "snapshot": run["snapshot"],
        "prompt_hashes": run["prompt_hashes"],
    }


@router.post("/runs/{run_id}/cancel", response_model=RunView, tags=["Runs"])
async def cancel_run(run_id: str, request: Request, user: Owner):
    return public_run(await request.app.state.runner.cancel(run_id, user))


@router.get("/runs/{run_id}/answers.csv", tags=["Exports"])
async def answers_csv(run_id: str, request: Request, user: Owner):
    run = await request.app.state.store.get("run", run_id, user)
    if run["status"] not in TERMINAL:
        raise DomainError("run_not_finished", "Wait for completion before exporting", 409)
    return Response(
        export_csv(run),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="answers.csv"'},
    )


@router.get("/runs/{run_id}/events", response_model=list[Event], tags=["Events"])
async def events(
    run_id: str,
    request: Request,
    user: Owner,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    return await request.app.state.store.events(run_id, user, after, limit)


@router.post("/runs/{run_id}/ws-ticket", tags=["Events"])
async def websocket_ticket(run_id: str, request: Request, user: Owner):
    await request.app.state.store.get("run", run_id, user)
    ticket, expires = request.app.state.tickets.issue(run_id, user)
    return {"ticket": ticket, "expires_at": expires, "path": f"/api/v1/runs/{run_id}/ws"}


@router.websocket("/runs/{run_id}/ws")
async def websocket_events(
    websocket: WebSocket, run_id: str, after: int = 0, ticket: str | None = None
):
    await stream_events(websocket, run_id, after, ticket)


async def stream_events(websocket, run_id, after, ticket, kind="run"):
    state = websocket.app.state
    ticket_scope = run_id if kind == "run" else "file-import:" + run_id
    try:
        if after < 0:
            raise DomainError("invalid_cursor", "Cursor must be nonnegative", 422)
        origin = websocket.headers.get("origin")
        if origin and origin not in state.settings.origins:
            raise DomainError("origin_not_allowed", "Origin is not allowed", 403)
        user = (
            state.tickets.verify(ticket, ticket_scope)
            if ticket
            else authenticate(
                state.settings,
                websocket.headers.get("X-AI-Service-Key"),
                websocket.headers.get("X-User-ID"),
            )
        )
        await state.store.get(kind, run_id, user)
    except DomainError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    cursor = after
    heartbeat = time.monotonic()
    try:
        while True:
            page = await state.store.events(run_id, user, cursor, kind=kind)
            for event in page:
                await websocket.send_json(event)
                cursor = event["seq"]
            if len(page) == 100:
                continue
            run = await state.store.get(kind, run_id, user)
            if run["status"] in TERMINAL:
                # Re-read after terminal state to avoid losing an event committed between reads.
                tail = await state.store.events(run_id, user, cursor, kind=kind)
                if tail:
                    for event in tail:
                        await websocket.send_json(event)
                        cursor = event["seq"]
                    continue
                await websocket.close(code=1000)
                return
            if time.monotonic() - heartbeat >= 15:
                await websocket.send_json({"type": "heartbeat", "cursor": cursor})
                heartbeat = time.monotonic()
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if message == "ping":
                    await websocket.send_json({"type": "pong", "cursor": cursor})
            except TimeoutError:
                pass
    except (WebSocketDisconnect, RuntimeError):
        return


@router.post("/sessions", status_code=201, tags=["Chat"])
async def create_session(body: SessionCreate, request: Request, user: Owner):
    await request.app.state.store.get("package", body.package_id, user)
    return await request.app.state.store.create(
        "session", {"id": uid(), **body.model_dump(), "messages": [], "created_at": now()}, user
    )


@router.get("/sessions", tags=["Chat"])
async def list_sessions(request: Request, user: Owner):
    return {"items": await request.app.state.store.list("session", user)}


@router.get("/sessions/{session_id}", tags=["Chat"])
async def get_session(session_id: str, request: Request, user: Owner):
    return await request.app.state.store.get("session", session_id, user)


@router.post(
    "/sessions/{session_id}/messages", status_code=202, response_model=RunView, tags=["Chat"]
)
async def send_message(
    session_id: str,
    body: ChatMessage,
    request: Request,
    user: Owner,
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    session = await request.app.state.store.get("session", session_id, user)
    question_id = body.question_id or (
        "chat-"
        + (hashlib.sha256(idempotency_key.encode()).hexdigest()[:24] if idempotency_key else uid())
    )
    run = RunCreate(
        mode=body.mode,
        session_id=session_id,
        questions=[Question(id=question_id, package_id=session["package_id"], text=body.text)],
        model=body.model,
        base_url=body.base_url,
        options=body.options,
        system_prompt=body.system_prompt,
        additional_instructions=body.additional_instructions,
    )
    return public_run(await request.app.state.runner.submit(run, user, idempotency_key))


@router.post("/runs/{run_id}/evaluate", status_code=201, tags=["Evaluation"])
async def evaluate(run_id: str, body: EvaluationRequest, request: Request, user: Owner):
    run = await request.app.state.store.get("run", run_id, user)
    result = evaluate_run(run, [r.model_dump() for r in body.reference_answers])
    by_id = {row["id"]: row for row in result["rows"]}
    cursor = 0
    while True:
        page = await request.app.state.store.events(run_id, user, cursor, 500)
        if not page:
            break
        for event in page:
            if event["type"] == "validation.failed":
                data = event["data"]
                if data.get("id") in by_id:
                    by_id[data["id"]]["validation_failures"].append(
                        {
                            "candidate": data.get("candidate"),
                            "checks": data.get("checks", []),
                        }
                    )
        cursor = page[-1]["seq"]
    return await request.app.state.store.create("evaluation", result, user)


@router.get("/evaluations/{evaluation_id}", tags=["Evaluation"])
async def get_evaluation(evaluation_id: str, request: Request, user: Owner):
    return await request.app.state.store.get("evaluation", evaluation_id, user)


@router.post("/comparisons", tags=["Evaluation"])
async def compare(body: ComparisonRequest, request: Request, user: Owner):
    before = await request.app.state.store.get("evaluation", body.before_evaluation_id, user)
    after = await request.app.state.store.get("evaluation", body.after_evaluation_id, user)
    return compare_evaluations(before, after)
