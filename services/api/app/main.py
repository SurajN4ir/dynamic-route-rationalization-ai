"""AURA API entrypoint.

Run locally with: uvicorn app.main:app --reload --app-dir services/api
(or, from inside services/api: uvicorn app.main:app --reload)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)
