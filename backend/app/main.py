import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers.events import auth, events, media, revisions, reference
from app.schemas.events.comman import APIResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


upload_dir = Path(settings.LOCAL_UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Event Flow API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    settings.SERVE_FILES_URL_PREFIX,
    StaticFiles(directory=str(upload_dir)),
    name="uploads",
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(media.router, prefix="/api/events/{event_id}/media", tags=["Media"])
app.include_router(revisions.router, prefix="/api/events/{event_id}/revisions", tags=["Revisions"])
app.include_router(reference.router, prefix="/api/reference", tags=["Reference"])


@app.get("/health")
async def health():
    return {"status": "ok"}


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
