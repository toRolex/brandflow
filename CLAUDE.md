# 项目级规范

## 项目概述

**Brandflow 短视频自动化系统 3.0** — `control-plane + runtime-worker` 短视频自动化生产系统。

- 控制面：`apps/control_plane/`（FastAPI + Web 看板，任务调度、审核）
- 执行器：`apps/runtime_worker/`（拉模式 worker，调用 `packages/pipeline_services/`）
- 目标平台：抖音、小红书、视频号、快手
- 默认 LLM：DeepSeek `deepseek-v4-pro`
- 默认 TTS：Xiaomi MiMo（4 种模型）
- 默认 Vision：Xiaomi `mimo-v2.5`

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 后端框架 | FastAPI + Uvicorn |
| HTTP 客户端 | `requests`（同步），`httpx`（dev，仅供 `TestClient`） |
| 前端框架 | React 19 + TypeScript 5.7 + Tailwind CSS v4 |
| 前端路由 | react-router-dom v7 |
| 前端图表 | ECharts 6（echarts-for-react） |
| 前端构建 | Vite 6 |
| 前端测试 | Vitest 4 + Testing Library |
| 数据模型 | Pydantic v2 |
| 数据持久化 | 文件系统 JSON（FileStore）+ SQLite |
| 依赖管理 | uv（`pyproject.toml` + `uv.lock`） |
| 媒体引擎 | FFmpeg / ffprobe / whisper-cli |
| 文档解析 | PyMuPDF + python-docx |
| 测试 | pytest + fastapi.testclient.TestClient |

跨平台：mac 开发 + Windows 生产，平台差异收口在 `runtime_adapters` 层。

## 关键命令

```bash
uv run python -m apps.control_plane          # 启动控制面（端口 17890）
uv run python -m apps.runtime_worker         # 启动 Worker
uv run pytest tests/ -q                      # 全量测试
```

> 部署、SSH 连接、Windows 启动等完整命令见 [`docs/deployment.md`](docs/deployment.md)。

## 目录结构

```
.
├── apps/
│   ├── control_plane/              # 控制面（FastAPI + Web + 任务调度）
│   │   ├── app.py                  # FastAPI app factory
│   │   ├── routes/                 # 14 个路由模块（jobs, projects, assets, tts, reviews, workers, config, products, schedule, scene, metrics, knowledge, templates, category_suggestion）
│   │   └── services/               # dispatch.py, reconcile.py
│   └── runtime_worker/             # 执行器（拉模式 worker）
│       ├── loop.py                 # WorkerLoop（poll → execute → report）
│       └── http_client.py          # WorkerHttpClient
│
├── packages/
│   ├── domain_core/                # 领域模型、状态机、worker 协议
│   ├── file_store/                 # 文件系统轻持久化
│   ├── deploy_health/              # 部署体检（Issue #76）
│   ├── knowledge_store/             # 知识库文档解析与卖点管理
│   ├── pipeline_services/          # 业务能力（独立 service）
│   │   ├── script_service/         # 脚本生成（generator + prompts + quality）
│   │   ├── tts_provider.py         # TTS 语音合成
│   │   ├── subtitle_service.py     # SRT 字幕生成
│   │   ├── video_service.py        # 视频组装与烧录
│   │   ├── phase_orchestrator.py   # PhaseOrchestrator（Generate/Import 双模式）
│   │   ├── job_tick_service.py     # Job 生命周期 tick 调度
│   │   ├── llm_client.py           # 通用 LLM HTTP 客户端
│   │   └── asset_library/          # 素材库能力
│   ├── provider_config/            # AppConfigManager + provider 配置桥接
│   ├── runtime_adapters/           # 平台适配（MacLocal / WindowsProd）
│   └── script_template/            # 脚本模板引擎
│
├── config/
│   ├── app_config.json             # 非 secret 业务配置
│   ├── providers.yaml              # 系统配置页兼容存储
│   └── defaults.yaml
│
├── tests/                          # pytest 测试
├── pyproject.toml / uv.lock        # uv 项目配置
├── .env / .env.example             # 环境变量（secret）
├── docs/                           # 项目文档
└── packaging/windows/              # Windows 启动器
```

## 配置与约束

- 配置统一通过 `AppConfigManager`（`packages/provider_config/app_config.py`）读取
- API Key 优先链：provider 专用 env → 通用回退 → `config/app_config.json` / `DEFAULTS`
- 完整配置说明、环境变量表、Scene 配置、LLM/TTS/Vision 架构 → [`docs/configuration.md`](docs/configuration.md)
- **API Key 安全**：secret 只放本机 `.env`，不得写入代码、文档或聊天

## 状态机

双模式：**Generate**（LLM 脚本 → TTS → 素材检索 → 视频合成）和 **Import**（场景素材 + TTS 并行 → 拼接 → 复用渲染）。

四个审核门：`script_review` / `tts_review` / `asset_review` / `final_review`。Worker 拉模式，control-plane 是唯一状态写入者。

> 完整状态流转、审核状态、Worker 协议、auto_tick 机制 → [`docs/state-machine.md`](docs/state-machine.md)。
> API 端点列表 → [`docs/api-reference.md`](docs/api-reference.md)。

## Git Flow 分支规范

所有开发在 `feature/<功能名>` 分支进行，禁止直接在 `main`/`develop` 提交。合并使用 `--no-ff`。

> 完整分支命名、commit message、PR 规范详见 `/git-flow-conventions` skill。

## 项目上下文维护

每次提交 git 前，检查并更新 `CLAUDE.md` 和 `README.md`，确保反映最新状态（新增功能、API、配置、流程变更、依赖变更）。

## 核心规则

1. **收到任务时，先检查是否有匹配的 skill** — 哪怕只有 1% 的可能性也要检查
2. **设计先于编码** — 先用 grill-with-docs skill 做需求分析
3. **测试先于实现** — 写代码前先写测试（TDD）
4. **验证先于完成** — 声称完成前必须运行验证命令

当任务匹配某个 skill 时，使用 `Skill` 工具加载对应 skill 并严格遵循其流程。绝不要用 Read 工具读取 SKILL.md 文件。如果你认为哪怕只有 1% 的可能性某个 skill 适用，你必须调用该 skill 检查。

## 文档索引

| 文档 | 内容 |
|------|------|
| [`docs/deployment.md`](docs/deployment.md) | SSH 配置、Windows 机器、启动命令、部署体检 |
| [`docs/configuration.md`](docs/configuration.md) | AppConfigManager、环境变量、Scene 配置、LLM/TTS/Vision 架构、脚本质检 |
| [`docs/state-machine.md`](docs/state-machine.md) | Job 状态流转、审核状态、Worker 协议、auto_tick |
| [`docs/api-reference.md`](docs/api-reference.md) | API 端点、前端素材库筛选 |
