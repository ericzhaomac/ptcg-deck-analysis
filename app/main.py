from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import build_router
from .config import Settings
from .provider_config import ProviderConfig, ProviderConfigStore
from .services.prague_analysis_service import PragueAnalysisService


def create_app(report_path: str | Path | None = None) -> FastAPI:
    settings = Settings.from_env(report_path=Path(report_path) if report_path else None)
    service = PragueAnalysisService(report_path=settings.report_path)
    provider_config_store = ProviderConfigStore(config_path=settings.provider_config_path)
    env_provider_config = None
    if settings.openai_base_url and settings.openai_api_key:
        env_provider_config = ProviderConfig(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            source="env",
        )

    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "deck-analysis-service"}

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def root():
        index_path = static_dir / "index.html"
        if index_path.exists():
            from fastapi.responses import FileResponse
            return FileResponse(str(index_path))
        return RedirectResponse(url="/api/v1/analysis/prague/provider/config")

    app.include_router(build_router(service=service, provider_config_store=provider_config_store, env_provider_config=env_provider_config))
    return app


app = create_app()
