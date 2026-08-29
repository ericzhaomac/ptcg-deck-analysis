from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Form, HTTPException, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ..deck_store import DeckNotFoundError, DeckStore
from ..models import (
    DatasetIdRequest,
    DatasetListResponse,
    DatasetRecord,
    DatasetState,
    DatasetStateResponse,
    DeckCompareRequest,
    DeckWrite,
    ExplainRequest,
    ExplainResponse,
    ModelDiscoveryRequest,
    ProviderSettingsWrite,
    SavedDeck,
)
from ..provider_config import ProviderConfig, ProviderConfigStore
from ..providers.openai_compatible import OpenAICompatibleProvider
from ..services.dataset_analysis_service import DatasetAnalysisService
from ..services.dataset_registry_service import DatasetRegistryService
from ..services.dataset_state_store import DatasetStateStore


API_PREFIX = "/api/v1/analysis"
PROVIDER_PREFIX = "/api/v1/provider"
CONFIG_PAGE_PATH = "/config"
CONFIG_PAGE_URL = f"{PROVIDER_PREFIX}{CONFIG_PAGE_PATH}"


def build_router(
    service: DatasetAnalysisService,
    provider_config_store: ProviderConfigStore,
    env_provider_config: ProviderConfig | None,
    dataset_registry: DatasetRegistryService,
    dataset_state_store: DatasetStateStore,
    deck_store: DeckStore,
) -> APIRouter:
    router = APIRouter()
    analysis_router = APIRouter(prefix=API_PREFIX, tags=["dataset-analysis"])
    datasets_router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])
    provider_router = APIRouter(prefix=PROVIDER_PREFIX, tags=["provider-config"])
    decks_router = APIRouter(prefix="/api/v1/decks", tags=["saved-decks"])

    def deck_or_404(deck_id: str) -> SavedDeck:
        try:
            return deck_store.get(deck_id)
        except DeckNotFoundError as error:
            raise HTTPException(status_code=404, detail="Saved deck not found") from error

    def provider_key_for_save(base_url: str, submitted_key: str, existing: ProviderConfig | None) -> str:
        api_key = submitted_key.strip()
        normalized_base_url = base_url.strip().rstrip("/")
        if not api_key and existing and normalized_base_url == existing.base_url.rstrip("/"):
            api_key = existing.api_key
        if not api_key:
            detail = "API key is required for first-time save"
            if existing:
                detail = "API key is required when changing the Base URL"
            raise HTTPException(status_code=400, detail=detail)
        return api_key

    def available_records() -> list[DatasetRecord]:
        return dataset_registry.list_datasets()

    def available_ids(records: list[DatasetRecord] | None = None) -> list[str]:
        return [record.dataset_id for record in (records if records is not None else available_records())]

    def reconciled_state(records: list[DatasetRecord] | None = None) -> DatasetState:
        return dataset_state_store.reconcile(dataset_state_store.load(), available_dataset_ids=available_ids(records))

    def dataset_list_response(records: list[DatasetRecord] | None = None, state: DatasetState | None = None) -> DatasetListResponse:
        records = records if records is not None else available_records()
        state = state if state is not None else reconciled_state(records)
        return DatasetListResponse(
            datasets=records,
            mounted_dataset_ids=state.mounted_dataset_ids,
            current_dataset_id=state.current_dataset_id,
        )

    def dataset_state_response(state: DatasetState) -> DatasetStateResponse:
        return DatasetStateResponse(mounted_dataset_ids=state.mounted_dataset_ids, current_dataset_id=state.current_dataset_id)

    def save_reconciled_state(state: DatasetState) -> DatasetState:
        reconciled = dataset_state_store.reconcile(state, available_dataset_ids=available_ids())
        dataset_state_store.save(reconciled)
        return reconciled

    def resolve_analysis_path(dataset_id: str | None = None) -> str:
        available = available_records()
        selected_dataset_id = dataset_id
        if selected_dataset_id is None:
            state = reconciled_state(available)
            selected_dataset_id = state.current_dataset_id
            if selected_dataset_id is None:
                raise HTTPException(status_code=400, detail="No current dataset is mounted and no dataset_id was provided")
        record = next((record for record in available if record.dataset_id == selected_dataset_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return record.analysis_path

    def get_active_provider_config() -> ProviderConfig | None:
        file_config = provider_config_store.load()
        if file_config and file_config.is_configured:
            return file_config
        if env_provider_config and env_provider_config.is_configured:
            return env_provider_config
        return None

    def build_provider(config: ProviderConfig | None) -> OpenAICompatibleProvider | None:
        if config is None:
            return None
        return OpenAICompatibleProvider(base_url=config.base_url, api_key=config.api_key, model=config.model)

    @datasets_router.get("", response_model=DatasetListResponse)
    def list_datasets() -> DatasetListResponse:
        records = available_records()
        state = reconciled_state(records)
        return dataset_list_response(records, state)

    @datasets_router.get("/mounted", response_model=DatasetStateResponse)
    def list_mounted_datasets() -> DatasetStateResponse:
        state = reconciled_state()
        return dataset_state_response(state)

    @datasets_router.post("/mount", response_model=DatasetStateResponse)
    def mount_dataset(request: DatasetIdRequest) -> DatasetStateResponse:
        if request.dataset_id not in available_ids():
            raise HTTPException(status_code=404, detail="Dataset not found")
        state = reconciled_state()
        mounted = list(state.mounted_dataset_ids)
        if request.dataset_id not in mounted:
            mounted.append(request.dataset_id)
        current = state.current_dataset_id or request.dataset_id
        saved = save_reconciled_state(DatasetState(mounted_dataset_ids=mounted, current_dataset_id=current))
        return dataset_state_response(saved)

    @datasets_router.post("/unmount", response_model=DatasetStateResponse)
    def unmount_dataset(request: DatasetIdRequest) -> DatasetStateResponse:
        state = reconciled_state()
        mounted = [dataset_id for dataset_id in state.mounted_dataset_ids if dataset_id != request.dataset_id]
        current = state.current_dataset_id if state.current_dataset_id in mounted else (mounted[0] if mounted else None)
        saved = save_reconciled_state(DatasetState(mounted_dataset_ids=mounted, current_dataset_id=current))
        return dataset_state_response(saved)

    @datasets_router.post("/current", response_model=DatasetStateResponse)
    def set_current_dataset(request: DatasetIdRequest) -> DatasetStateResponse:
        state = reconciled_state()
        if request.dataset_id not in state.mounted_dataset_ids:
            raise HTTPException(status_code=400, detail="Dataset must be mounted before it can be current")
        saved = save_reconciled_state(DatasetState(mounted_dataset_ids=state.mounted_dataset_ids, current_dataset_id=request.dataset_id))
        return dataset_state_response(saved)

    @analysis_router.get("/summary")
    def get_summary(dataset_id: str | None = None) -> dict:
        return service.get_summary(resolve_analysis_path(dataset_id))

    @analysis_router.post("/compare")
    def compare_deck(request: DeckCompareRequest) -> dict:
        return service.compare_deck(analysis_path=resolve_analysis_path(request.dataset_id), archetype=request.archetype, deck_payload=request.deck)

    @analysis_router.post("/explain", response_model=ExplainResponse)
    def explain(request: ExplainRequest) -> ExplainResponse:
        provider_config = get_active_provider_config()
        provider = build_provider(provider_config)
        if provider is None:
            raise HTTPException(status_code=501, detail="LLM provider is not configured")
        context = service.build_explain_context(analysis_path=resolve_analysis_path(request.dataset_id), archetype=request.archetype, deck_payload=request.deck)
        system_prompt = "You are a PTCG deck analysis assistant focused on mounted tournament meta interpretation."
        user_prompt = json.dumps({"question": request.question, "context": context}, ensure_ascii=False)
        result = provider.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        return ExplainResponse(provider=result["provider"], model=result["model"], answer=result["answer"], context=context)

    @decks_router.get("", response_model=list[SavedDeck])
    def list_saved_decks() -> list[SavedDeck]:
        return deck_store.list_decks()

    @decks_router.post("", response_model=SavedDeck, status_code=status.HTTP_201_CREATED)
    def create_saved_deck(request: DeckWrite) -> SavedDeck:
        return deck_store.create(request)

    @decks_router.get("/{deck_id}", response_model=SavedDeck)
    def get_saved_deck(deck_id: str) -> SavedDeck:
        return deck_or_404(deck_id)

    @decks_router.put("/{deck_id}", response_model=SavedDeck)
    def update_saved_deck(deck_id: str, request: DeckWrite) -> SavedDeck:
        try:
            return deck_store.update(deck_id, request)
        except DeckNotFoundError as error:
            raise HTTPException(status_code=404, detail="Saved deck not found") from error

    @decks_router.post("/{deck_id}/duplicate", response_model=SavedDeck, status_code=status.HTTP_201_CREATED)
    def duplicate_saved_deck(deck_id: str) -> SavedDeck:
        try:
            return deck_store.duplicate(deck_id)
        except DeckNotFoundError as error:
            raise HTTPException(status_code=404, detail="Saved deck not found") from error

    @decks_router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_saved_deck(deck_id: str) -> Response:
        try:
            deck_store.delete(deck_id)
        except DeckNotFoundError as error:
            raise HTTPException(status_code=404, detail="Saved deck not found") from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @provider_router.get("")
    def get_provider_config() -> dict[str, object]:
        return provider_settings_response()

    def provider_settings_response() -> dict[str, object]:
        active_config = get_active_provider_config()
        file_config = provider_config_store.load()
        return {
            "active": active_config.masked() if active_config else None,
            "file": file_config.masked() if file_config else None,
            "env": env_provider_config.masked() if env_provider_config else None,
        }

    @provider_router.get("/settings")
    def get_provider_settings() -> dict[str, object]:
        return provider_settings_response()

    @provider_router.put("/settings")
    def update_provider_settings(request: ProviderSettingsWrite) -> dict[str, str | bool]:
        existing = provider_config_store.load()
        final_api_key = provider_key_for_save(request.base_url, request.api_key, existing)
        saved = provider_config_store.save(
            base_url=request.base_url,
            api_key=final_api_key,
            model=request.model,
        )
        return saved.masked()

    @provider_router.post("/models")
    def discover_provider_models(request: ModelDiscoveryRequest) -> dict[str, object]:
        active = get_active_provider_config()
        base_url = request.base_url.strip() or (active.base_url if active else "")
        if not base_url:
            raise HTTPException(status_code=400, detail="Base URL is required to fetch models")
        api_key = request.api_key.strip()
        if not api_key and active and base_url.rstrip("/") == active.base_url.rstrip("/"):
            api_key = active.api_key
        if not api_key:
            detail = "API key is required to fetch models"
            if active and request.base_url.strip():
                detail = "API key is required when fetching models from a different Base URL"
            raise HTTPException(status_code=400, detail=detail)
        provider = OpenAICompatibleProvider(
            base_url=base_url,
            api_key=api_key,
            model=active.model if active else "model-discovery",
        )
        try:
            models = provider.list_models()
        except httpx.HTTPStatusError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Unable to fetch models from the configured provider (HTTP {error.response.status_code})",
            ) from error
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail="Unable to connect to the configured provider") from error
        except (ValueError, KeyError) as error:
            raise HTTPException(status_code=502, detail="The configured provider returned an invalid model list") from error
        return {"base_url": base_url, "models": models}

    @provider_router.get(CONFIG_PAGE_PATH, include_in_schema=False, response_class=HTMLResponse)
    def provider_page(saved: int = 0) -> str:
        file_config = provider_config_store.load()
        active_config = get_active_provider_config()
        base_url = file_config.base_url if file_config else ""
        model = file_config.model if file_config else ""
        api_key_placeholder = "已保存（重新填写可覆盖）" if file_config and file_config.api_key else ""
        status_message = '<p style="color: green;">配置已保存，后续 explain 请求会优先使用文件配置。</p>' if saved else ""
        active_summary = render_active_summary(active_config=active_config, env_provider_config=env_provider_config)
        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Deck Analysis Provider Config</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto; line-height: 1.5; }}
    label {{ display: block; margin-top: 16px; font-weight: 600; }}
    input {{ width: 100%; padding: 10px; margin-top: 6px; box-sizing: border-box; }}
    button {{ margin-top: 20px; padding: 10px 16px; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
    code {{ background: #f5f5f5; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>AI Provider 配置</h1>
  <div class="card">
    <p>配置文件路径：<code>{provider_config_store.config_path}</code></p>
    <p>页面保存后，<code>POST /api/v1/analysis/explain</code> 会优先使用这里的配置；没有文件配置时才 fallback 到 env。</p>
    {status_message}
    <form method="post" action="{CONFIG_PAGE_URL}">
      <label for="base_url">Custom base URL</label>
      <input id="base_url" name="base_url" type="text" value="{escape_attr(base_url)}" placeholder="https://api.kimi.com/coding" required />

      <label for="model">Custom model name</label>
      <input id="model" name="model" type="text" value="{escape_attr(model)}" placeholder="kimi-code" required />

      <label for="api_key">API key</label>
      <input id="api_key" name="api_key" type="password" value="" placeholder="{escape_attr(api_key_placeholder)}" />

      <button type="submit">保存配置</button>
    </form>
  </div>
  <div class="card">
    <h2>当前生效配置</h2>
    {active_summary}
    <p>JSON 查看接口：<code>/api/v1/provider</code></p>
  </div>
</body>
</html>
"""

    @provider_router.post(CONFIG_PAGE_PATH, include_in_schema=False)
    def save_provider_config(
        base_url: str = Form(...),
        model: str = Form(...),
        api_key: str = Form(""),
    ) -> RedirectResponse:
        existing = provider_config_store.load()
        final_api_key = provider_key_for_save(base_url, api_key, existing)
        provider_config_store.save(base_url=base_url, api_key=final_api_key, model=model)
        return RedirectResponse(url=f"{CONFIG_PAGE_URL}?saved=1", status_code=303)

    router.include_router(analysis_router)
    router.include_router(datasets_router)
    router.include_router(provider_router)
    router.include_router(decks_router)
    return router


def render_active_summary(active_config: ProviderConfig | None, env_provider_config: ProviderConfig | None) -> str:
    if not active_config:
        return "<p>当前没有可用 provider 配置。</p>"
    source_label = "持久化文件" if active_config.source == "file" else "环境变量"
    env_hint = "有" if env_provider_config and env_provider_config.is_configured else "无"
    masked = active_config.masked()
    return (
        "<ul>"
        f"<li>source: {source_label}</li>"
        f"<li>base_url: <code>{escape_html(str(masked['base_url']))}</code></li>"
        f"<li>model: <code>{escape_html(str(masked['model']))}</code></li>"
        f"<li>api_key: <code>{escape_html(str(masked['api_key']))}</code></li>"
        f"<li>env fallback: {env_hint}</li>"
        "</ul>"
    )


def escape_attr(value: str) -> str:
    return escape_html(value).replace('"', "&quot;")


def escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
