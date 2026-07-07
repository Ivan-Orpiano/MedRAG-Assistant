from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import admin, auth, chat, documents
from app.core.logging import configure_logging, get_logger
from app.schemas.schemas import DISCLAIMER

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = f"""
AI Medical Knowledge Assistant API — Retrieval-Augmented Generation over an
uploaded corpus of clinical guidelines, research papers, SOPs, and protocols.

**Disclaimer:** {DISCLAIMER}
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.retrieval.vector_store import ensure_collection

    try:
        ensure_collection()
    except Exception:
        logger.exception("Could not ensure Qdrant collection at startup (will retry on ingest)")
    yield


app = FastAPI(
    title="MedAssist RAG API",
    version="2.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # frontend is server-side (NiceGUI); tighten if exposing the API publicly
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "disclaimer": DISCLAIMER}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
