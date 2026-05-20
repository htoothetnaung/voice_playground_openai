"""Creates the Atenxion backend, configures logging, CORS, request tracing, and mounts all API routers."""
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_context


def create_app() -> FastAPI:
    """Build and configure the FastAPI application that hosts every backend API and WebSocket route."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Atenxion Call Center Backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_trace(request: Request, call_next):
        """Attach a request ID to the logging context and response headers so each HTTP request can be followed across the backend."""
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request_id_context.set(request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(api_router)
    return app


app = create_app()
