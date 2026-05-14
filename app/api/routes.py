from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from ..models import DeckCompareRequest, ExplainRequest, ExplainResponse
from ..provider_config import ProviderConfig, ProviderConfigStore
from ..providers.openai_compatible import OpenAICompatibleProvider
from ..services.dataset_analysis_service import DatasetAnalysisService
from ..services.dataset_registry_service import DatasetRegistryService
from ..services.dataset_state_store import DatasetStateStore


API_PREFIX = "/api/v1/analysis"
CONFIG_PAGE_PATH = "/provider/config"
CONFIG_PAGE_URL = f"{API_PREFIX}{CONFIG_PAGE_PATH}"


def build_router(
    service: DatasetAnalysisService,
    provider_config_store: ProviderConfigStore,
    env_provider_config: ProviderConfig | None,
    dataset_registry: DatasetRegistryService,
    dataset_state_store: DatasetStateStore,
) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX, tags=["dataset-analysis"])

    def current_analysis_path() -> str:
        available = dataset_registry.list_datasets()
        state = dataset_state_store.reconcile(
            dataset_state_store.load(),
            available_dataset_ids=[record.dataset_id for record in available],
        )
        if not state.current_dataset_id:
            raise HTTPException(status_code=404, detail="No current dataset is mounted")
        record = next((record for record in available if record.dataset_id == state.current_dataset_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail="Current dataset not found")
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

    @router.get("/summary")
    def get_summary() -> dict:
        return service.get_summary(current_analysis_path())

    @router.post("/compare")
    def compare_deck(request: DeckCompareRequest) -> dict:
        return service.compare_deck(analysis_path=current_analysis_path(), archetype=request.archetype, deck_payload=request.deck)

    @router.post("/explain", response_model=ExplainResponse)
    def explain(request: ExplainRequest) -> ExplainResponse:
        provider_config = get_active_provider_config()
        provider = build_provider(provider_config)
        if provider is None:
            raise HTTPException(status_code=501, detail="LLM provider is not configured")
        context = service.build_explain_context(analysis_path=current_analysis_path(), archetype=request.archetype, deck_payload=request.deck)
        system_prompt = "You are a PTCG deck analysis assistant focused on mounted tournament meta interpretation."
        user_prompt = json.dumps({"question": request.question, "context": context}, ensure_ascii=False)
        result = provider.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        return ExplainResponse(provider=result["provider"], model=result["model"], answer=result["answer"], context=context)

    @router.get("/provider", tags=["provider-config"])
    def get_provider_config() -> dict[str, object]:
        active_config = get_active_provider_config()
        file_config = provider_config_store.load()
        return {
            "active": active_config.masked() if active_config else None,
            "file": file_config.masked() if file_config else None,
            "env": env_provider_config.masked() if env_provider_config else None,
        }

    @router.get(CONFIG_PAGE_PATH, include_in_schema=False, response_class=HTMLResponse, tags=["provider-config"])
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
    <p>JSON 查看接口：<code>/api/v1/analysis/prague/provider</code></p>
  </div>
</body>
</html>
"""

    @router.post(CONFIG_PAGE_PATH, include_in_schema=False, tags=["provider-config"])
    def save_provider_config(
        base_url: str = Form(...),
        model: str = Form(...),
        api_key: str = Form(""),
    ) -> RedirectResponse:
        existing = provider_config_store.load()
        final_api_key = api_key.strip() or (existing.api_key if existing else "")
        if not final_api_key:
            raise HTTPException(status_code=400, detail="API key is required for first-time save")
        provider_config_store.save(base_url=base_url, api_key=final_api_key, model=model)
        return RedirectResponse(url=f"{CONFIG_PAGE_URL}?saved=1", status_code=303)

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
