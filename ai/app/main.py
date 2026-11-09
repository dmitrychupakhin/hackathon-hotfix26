import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.auth import Tickets
from app.api.routes import router
from app.config import Settings, get_settings
from app.domain import DomainError
from app.infrastructure.files import ExtractionLimits, FileIngestor
from app.infrastructure.llm import ApiMira
from app.infrastructure.postgres import PostgresStore
from app.infrastructure.store import Store
from app.services.file_cache import FileCache
from app.services.file_imports import FileImports
from app.services.runner import Runner


class BodyLimit:
    def __init__(self, app, maximum: int):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope.get("headers", [])).get(b"content-length")
        if length:
            try:
                too_large = int(length) > self.maximum
            except ValueError:
                too_large = True
            if too_large:
                return await JSONResponse(
                    {
                        "error": {
                            "code": "body_too_large",
                            "message": "Request exceeds the configured limit",
                        }
                    },
                    status_code=413,
                )(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.maximum:
                raise HTTPException(413, "Request body limit exceeded")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(settings: Settings | None = None, model=None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        if settings.database_url.get_secret_value():
            store = PostgresStore(settings.database_url.get_secret_value())
        elif settings.environment == "test":
            store = Store(settings.db_file)
        else:
            raise RuntimeError(
                "AI_DATABASE_URL must point to the PostgreSQL database created by backend"
            )
        async with AsyncExitStack() as stack:
            await store.open()
            stack.push_async_callback(store.close)
            await store.recover_interrupted()
            client = model or ApiMira(settings)
            if model is None:
                stack.push_async_callback(client.close)
            app.state.store = store
            app.state.comparison_input_lock = asyncio.Lock()
            windows = await client.context_windows() if model is None else {}
            source_root = settings.storage_path(settings.source_root)
            if settings.environment == "test":
                source_root.mkdir(parents=True, exist_ok=True)
            file_client = httpx.AsyncClient(trust_env=False)
            stack.push_async_callback(file_client.aclose)
            ingestor = FileIngestor(
                file_client,
                limits=ExtractionLimits(
                    max_bytes=settings.max_upload_bytes, ocr_enabled=settings.ocr_enabled
                ),
            )
            app.state.file_cache = FileCache(
                source_root,
                settings.storage_path(settings.file_cache_root),
                ingestor,
                settings.max_upload_bytes,
            )
            app.state.file_imports = FileImports(
                store, app.state.file_cache, settings, app.state.mutation_lock
            )
            await app.state.file_imports.recover()
            stack.push_async_callback(app.state.file_imports.close)
            app.state.runner = Runner(store, client, settings, windows)
            stack.push_async_callback(app.state.runner.close)
            yield

    app = FastAPI(
        title="ОНСОФТ AI — проверяемые ответы по закупкам",
        version="0.1.0",
        description="AI-side service: immutable source snapshots, evidence tools, bounded repair, durable run events and organizer CSV export. Django owns end-user authentication. WebSocket contract: ai/README.md.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.tickets = Tickets(settings)
    app.state.mutation_lock = asyncio.Lock()
    app.add_middleware(BodyLimit, maximum=settings.max_package_bytes * 4)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-AI-Service-Key", "X-User-ID", "Idempotency-Key"],
    )

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.get("/", include_in_schema=False)
    async def index():
        return RedirectResponse("/docs")

    @app.get("/health/live", tags=["Health"])
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["Health"])
    async def ready():
        try:
            await app.state.store.ping()
        except Exception:
            return JSONResponse({"status": "storage_unavailable"}, status_code=503)
        configured = model is not None or bool(settings.api_key.get_secret_value())
        return JSONResponse(
            {
                "status": "ready" if configured else "provider_not_configured",
                "provider_configured": configured,
            },
            status_code=200 if configured else 503,
        )

    app.include_router(router)

    def current_openapi():
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title, version=app.version, description=app.description, routes=app.routes
            )
            for model_schema in schema.get("components", {}).get("schemas", {}).values():
                properties = model_schema.get("properties", {})
                if "mode" in properties and "system_prompt" in properties:
                    if "model" in properties:
                        properties["model"]["default"] = settings.model
                    if "base_url" in properties:
                        properties["base_url"]["default"] = settings.base_url
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = current_openapi
    return app


app = create_app()
