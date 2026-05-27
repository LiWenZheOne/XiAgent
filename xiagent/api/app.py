from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from xiagent.api.dependencies import build_services
from xiagent.api.error_handlers import register_error_handlers
from xiagent.api.routers import assets, auth, nodes, projects, tasks, ui, workflows
from xiagent.infrastructure.config import Settings, load_settings
from xiagent.infrastructure.migrations import migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await migrate(resolved_settings.database_path)
        app.state.services = build_services(resolved_settings)
        yield

    app = FastAPI(title="XiAgent API", lifespan=lifespan)
    app.state.settings = resolved_settings
    register_error_handlers(app)

    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(nodes.router)
    app.include_router(assets.router)
    app.include_router(workflows.router)
    app.include_router(tasks.router)
    app.include_router(ui.router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
