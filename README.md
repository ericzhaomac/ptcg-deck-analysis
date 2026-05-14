# Deck Analysis Service

Standalone FastAPI service for PTCG tournament deck-analysis datasets.

## 当前范围

- Dataset discovery from a mounted data directory
- Mounted/current dataset state API
- Generic metagame summary, deck compare, and explain APIs
- OpenAI-compatible provider abstraction（当前默认指向 Kimi Code）
- Neutral HTTP provider 配置页（保存 custom base URL / model / API key）

## 目录

- `app/main.py` FastAPI 入口
- `app/config.py` 环境变量配置
- `app/provider_config.py` provider 配置读写与 mask
- `app/services/dataset_analysis_service.py` dataset 报告读取与分析逻辑
- `app/providers/openai_compatible.py` 自定义 OpenAI-compatible endpoint 抽象
- `app/api/routes.py` API routes + 配置页

## Dataset directory convention

`DATA_ROOT` 下按以下约定放置已生成的 analysis JSON：

```text
DATA_ROOT/
  <year>/
    <event>/
      <division>/
        analysis.json
```

示例：`data/2026/Prague/MA/analysis.json` 会被识别为 dataset id `2026-prague-ma`。

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

可选环境变量：

```bash
export DATA_ROOT=/data
export DATASET_STATE_PATH=/data/config/dataset_state.json
export PROVIDER_CONFIG_PATH=/data/config/provider.json
export OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/
export OPENAI_COMPATIBLE_API_KEY=your_key
export OPENAI_COMPATIBLE_MODEL=kimi-code
```

- `DATA_ROOT`：dataset discovery 根目录，默认 `data`。
- `DATASET_STATE_PATH`：mounted/current dataset 状态文件，默认 `data/config/dataset_state.json`。
- `PROVIDER_CONFIG_PATH`：provider 配置文件，默认 `/data/config/provider.json`。

`POST /api/v1/analysis/explain` 会优先读 `PROVIDER_CONFIG_PATH` 指向的 JSON 文件；如果文件不存在或不完整，再 fallback 到 env。

## Docker

默认约定：

- dataset 挂载目录：`/data`
- dataset 状态文件：`/data/config/dataset_state.json`
- provider 配置文件：`/data/config/provider.json`
- Web 配置页：`/api/v1/provider/config`

### build

```bash
docker build -t ptcg-deck-analysis .
```

### run

```bash
docker run --rm -p 8010:8010 \
  -v $(pwd)/data:/data \
  -e DATA_ROOT=/data \
  -e DATASET_STATE_PATH=/data/config/dataset_state.json \
  -e PROVIDER_CONFIG_PATH=/data/config/provider.json \
  -e OPENAI_COMPATIBLE_BASE_URL=https://api.kimi.com/coding/ \
  -e OPENAI_COMPATIBLE_API_KEY=$OPENAI_COMPATIBLE_API_KEY \
  -e OPENAI_COMPATIBLE_MODEL=kimi-code \
  ptcg-deck-analysis
```

即使传了 env，后续你也可以在浏览器页面里改成别的 base URL / model / key；保存后 explain 会优先使用文件配置。

## API

- `GET /health`
- `GET /api/v1/datasets`：列出 available datasets 与 mounted/current 状态
- `GET /api/v1/datasets/mounted`：查看 mounted/current 状态
- `POST /api/v1/datasets/mount`：挂载 dataset
- `POST /api/v1/datasets/unmount`：卸载 dataset
- `POST /api/v1/datasets/current`：设置 current dataset
- `GET /api/v1/analysis/summary`：读取 current dataset summary；也可传 `dataset_id`
- `POST /api/v1/analysis/compare`：对比用户 deck 与 dataset archetype
- `POST /api/v1/analysis/explain`：基于 dataset context 调用 provider 解释
- `GET /api/v1/provider`：查看当前 active/file/env provider（API key 已 mask）
- `GET /api/v1/provider/config`：HTML 配置页
- `POST /api/v1/provider/config`：保存配置表单

### 浏览器配置方式

1. 启动服务
2. 打开 `http://localhost:8010/api/v1/provider/config`
3. 填写：
   - custom base URL
   - custom model name
   - API key
4. 点击“保存配置”
5. 后续调用 `POST /api/v1/analysis/explain` 会自动使用该配置

如果已经保存过 API key，后续只改 base URL / model 时可以把 API key 输入框留空，服务会保留旧 key。

### compare request example

```json
{
  "dataset_id": "2026-prague-ma",
  "archetype": "Dragapult",
  "deck": {
    "pokemon": [{"name": "Dreepy", "count": 4}],
    "trainer": [{"name": "Buddy-Buddy Poffin", "count": 4}],
    "energy": [{"name": "Psychic Energy", "count": 3}]
  }
}
```

`dataset_id` is optional when a current dataset is mounted.
