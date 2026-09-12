from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from minutes.app_lifecycle import app_lifespan
from minutes.http_errors import http_exception_handler
from minutes.request_auth import require_admin
from minutes.routers.admin_buckets import router as admin_buckets_router
from minutes.routers.authentication import router as authentication_router
from minutes.routers.background_tasks import (
    router as background_tasks_router,
)
from minutes.routers.pipeline import router as pipeline_router
from minutes.routers.service_tokens import router as service_tokens_router
from minutes.routers.upload_cleanup import router as upload_cleanup_router
from minutes.routers.uploads import router as uploads_router
from minutes.routers.user_buckets import router as user_buckets_router

app = FastAPI(title="Minutes Service (prototype)", lifespan=app_lifespan)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)


def include_canonical_and_legacy_alias(router, **kwargs) -> None:
    app.include_router(router, prefix="/api", **kwargs)
    app.include_router(router, include_in_schema=False, **kwargs)


app.include_router(background_tasks_router)

app.include_router(admin_buckets_router, dependencies=[Depends(require_admin)])
app.include_router(service_tokens_router, dependencies=[Depends(require_admin)])
include_canonical_and_legacy_alias(
    upload_cleanup_router, dependencies=[Depends(require_admin)]
)
app.include_router(pipeline_router)
include_canonical_and_legacy_alias(uploads_router)
app.include_router(user_buckets_router)
include_canonical_and_legacy_alias(authentication_router)


# CORS is only used when the browser talks to FastAPI directly (Vite on :5173).
# Compose serves the SPA and `/api` from the same nginx origin, so these
# origins are unused for docker compose up.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
