from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import build_router
from .api.tournament_reports import build_tournament_report_router
from .config import Settings
from .deck_store import DeckStore
from .provider_config import ProviderConfig, ProviderConfigStore
from .services.dataset_analysis_service import DatasetAnalysisService
from .services.dataset_registry_service import DatasetRegistryService
from .services.dataset_state_store import DatasetStateStore
from .services.tournament_report_service import TournamentReportService
from .tournament_reports.snapshots import SnapshotStore


def create_app(
    data_root: str | Path | None = None,
    dataset_state_path: str | Path | None = None,
    provider_config_path: str | Path | None = None,
    user_decks_path: str | Path | None = None,
) -> FastAPI:
    settings = Settings.from_env(
        data_root=Path(data_root) if data_root else None,
        dataset_state_path=Path(dataset_state_path) if dataset_state_path else None,
        provider_config_path=Path(provider_config_path) if provider_config_path else None,
        user_decks_path=Path(user_decks_path) if user_decks_path else None,
    )
    service = DatasetAnalysisService()
    dataset_registry = DatasetRegistryService(settings.data_root)
    dataset_state_store = DatasetStateStore(settings.dataset_state_path)
    provider_config_store = ProviderConfigStore(config_path=settings.provider_config_path)
    deck_store = DeckStore(path=settings.user_decks_path)
    tournament_report_service = TournamentReportService(
        dataset_registry=dataset_registry,
        dataset_state_store=dataset_state_store,
        snapshot_store=SnapshotStore(),
        family_overrides_path=settings.data_root / "config" / "archetype_family_overrides.json",
    )
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
        return RedirectResponse(url="/api/v1/provider/config")

    app.include_router(
        build_router(
            service=service,
            provider_config_store=provider_config_store,
            env_provider_config=env_provider_config,
            dataset_registry=dataset_registry,
            dataset_state_store=dataset_state_store,
            deck_store=deck_store,
        )
    )
    app.include_router(build_tournament_report_router(tournament_report_service))
    return app


app = create_app()
