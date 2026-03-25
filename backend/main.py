import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from cache import close_redis
from routers.documents import combined as doc_combined
from routers.documents import documents as doc_router
from routers.documents import reference as doc_reference
from routers.events import auth, events, reference
from schemas.events.comman import APIResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
# Keep Azure SDK request/response headers/body out of logs.
for noisy_logger in (
    "azure",
    "azure.core",
    "azure.core.pipeline",
    "azure.core.pipeline.policies",
    "azure.storage",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.storage.blob",
):
    lg = logging.getLogger(noisy_logger)
    lg.setLevel(logging.CRITICAL + 1)
    lg.propagate = False
    lg.disabled = True
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    yield
    logger.info("Shutting down – closing Redis")
    await close_redis()


app = FastAPI(
    title="Event Flow API",
    version="1.0.0",
    lifespan=lifespan,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Reduce browser MIME sniffing on API responses (JSON, etc.)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(reference.router, prefix="/api/reference", tags=["Reference"])

app.include_router(doc_combined.router, prefix="/api/items", tags=["Items"])

app.include_router(events.router, prefix="/api/events", tags=["Events"])

app.include_router(doc_router.router, prefix="/api/documents", tags=["Documents"])
app.include_router(doc_reference.router, prefix="/api/reference/documents", tags=["Document Reference"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(ValidationError)
async def validation_exception_handler(_request: Request, exc: ValidationError):
    errors = exc.errors()
    msg = errors[0]["msg"] if errors else "Validation error"
    body = APIResponse(
        message=msg,
        status_code=422,
        status="error",
        data=None,
    )
    return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    body = APIResponse(
        message=str(exc.detail),
        status_code=exc.status_code,
        status="error",
        data=None,
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    body = APIResponse(
        message="Internal server error",
        status_code=500,
        status="error",
        data=None,
    )
    return JSONResponse(status_code=500, content=body.model_dump())
