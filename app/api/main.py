"""
app/api/main.py
FastAPI application entrypoint for the Script Writer platform.
Configures CORS, mounts authentication, user studio, and admin endpoints,
and initializes default admin & creator accounts on startup.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.account.service import AccountService
from app.api import admin, auth, user
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle manager."""
    # Ensure database schema is migrated and default accounts exist
    init_db()
    account_service = AccountService()
    account_service.ensure_default_accounts()
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(
        title="Script Writer API",
        description="Production REST API for Video-to-Style Script Generation and Creative RAG Studio",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS configuration for local development and decoupled frontends
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API Routers
    app.include_router(auth.router)
    app.include_router(user.router)
    app.include_router(admin.router)

    @app.get("/api/health", tags=["Health"])
    def health_check():
        return JSONResponse(content={"status": "healthy", "service": "script-writer-api", "version": "1.0.0"})

    return app


app = create_app()

