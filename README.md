# Deck Analysis Service

最小 standalone service，先只承接 Prague 0062 的卡组构筑 AI 分析。

## 当前范围

- Prague 0062 / MA 已生成分析 JSON 的读取
- metagame summary API
- archetype vs user deck diff API
- OpenAI-compatible provider 抽象（当前默认指向 Kimi Code）
- explain API（优先使用持久化 provider 配置；无配置时 fallback 到 env）
- 最小 HTTP 配置页（保存 custom base URL / model / API key）

## 目录

- `app/main.py` FastAPI 入口
- `app/config.py` 环境变量配置
- `app/provider_config.py` provider 配置读写与 mask
- `app/services/prague_analysis_service.py` Prague 报告读取与复用现有脚本逻辑
- `app/providers/openai_compatible.py` 自定义 OpenAI-compatible endpoint 抽象
- `app/api/routes.py` API routes + 配置页

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r services/deck_analysis_service/requirements.txt
uvicorn services.deck_analysis_service.app.main:app --reload --port 8010
```

可选环境变量：

```bash
export PROVIDER_CONFIG_PATH=/data/config/provider.json
export OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/
export OPENAI_COMPATIBLE_API_KEY=your_key
export OPENAI_COMPATIBLE_MODEL=kimi-code
```

> `POST /api/v1/analysis/prague/explain` 会优先读 `PROVIDER_CONFIG_PATH` 指向的 JSON 文件；如果文件不存在或不完整，再 fallback 到 env。

## Docker

默认约定：

- 配置文件：`/data/config/provider.json`
- 容器内挂载目录：`/data`
- Web 配置页：`/api/v1/analysis/prague/provider/config`

### build

```bash
docker build -f services/deck_analysis_service/Dockerfile -t ptcg-deck-analysis .
```

### run

```bash
docker run --rm -p 8010:8010 \
  -v $(pwd)/services/deck_analysis_service/data:/data \
  -e PRAGUE_ANALYSIS_REPORT_PATH=tmp/limitless_reports/limitless_0062_MA_analysis.json \
  -e PROVIDER_CONFIG_PATH=/data/config/provider.json \
  -e OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/ \
  -e OPENAI_COMPATIBLE_API_KEY=$OPENAI_COMPATIBLE_API_KEY \
  -e OPENAI_COMPATIBLE_MODEL=kimi-code \
  ptcg-deck-analysis
```

即使传了 env，后续你也可以在浏览器页面里改成别的 base URL / model / key；保存后 explain 会优先使用文件配置。

## API

- `GET /health`
- `GET /api/v1/analysis/prague/summary`
- `POST /api/v1/analysis/prague/compare`
- `POST /api/v1/analysis/prague/explain`
- `GET /api/v1/analysis/prague/provider`：查看当前 active/file/env provider（API key 已 mask）
- `GET /api/v1/analysis/prague/provider/config`：HTML 配置页
- `POST /api/v1/analysis/prague/provider/config`：保存配置表单

### 浏览器配置方式

1. 启动服务
2. 打开 `http://localhost:8010/api/v1/analysis/prague/provider/config`
3. 填写：
   - custom base URL
   - custom model name
   - API key
4. 点击“保存配置”
5. 后续调用 `POST /api/v1/analysis/prague/explain` 会自动使用该配置

如果已经保存过 API key，后续只改 base URL / model 时可以把 API key 输入框留空，服务会保留旧 key。

### compare request example

```json
{
  "archetype": "Dragapult",
  "deck": {
    "pokemon": [{"name": "Dreepy", "count": 4}],
    "trainer": [{"name": "Buddy-Buddy Poffin", "count": 4}],
    "energy": [{"name": "Psychic Energy", "count": 3}]
  }
}
```

## 未来扩展位

- metagame summary prompt builder
- skeleton/core-common-tech 摘要 prompt
- user deck diff + explain 联动
- deck chat / conversational analysis
