# Brandflow 短视频自动化系统 3.0

AI 驱动的短视频自动化生产系统，基于 `control-plane + runtime-worker` 架构。工作人员通过 Web 前端完成全流程操作，无需命令行。

## 快速启动

### macOS / Linux

```bash
# 1. 安装后端依赖
uv sync

# 2. 配置 API Key（复制 .env.example 为 .env，填入密钥）
cp .env.example .env

# 3. 安装前端依赖
cd frontend && npm install && cd ..
```

### Windows

```cmd
# 1. 初始化目录、体检、生成 .env 模板
packaging\windows\init.bat

# 2. 编辑 .env 填入 API Key

# 3. 安装前端依赖
cd frontend && npm install && cd ..

# 4. 同时启动后端和前端
packaging\windows\start.bat
```

### 启动

**macOS / Linux 需要同时开两个终端窗口** — 一个跑后端，一个跑前端。

**终端 1 — 后端：**
```bash
uv run python -m apps.control_plane
```
看到 `Uvicorn running on http://127.0.0.1:17890` 即成功。

**终端 2 — 前端：**
```bash
cd frontend && npm run dev
```
看到 `Local: http://localhost:5173/` 即成功。

**Windows** 直接运行 `packaging\windows\start.bat`，后端日志写入 `logs/backend.log`，前端日志写入 `logs/frontend.log`。

然后打开浏览器访问 **http://localhost:5173**。

> 如果前端还没装依赖，先在 `frontend/` 目录执行 `npm install`。

### 关闭

分别在两个终端窗口按 `Ctrl+C`（同时按住 Control 键和 C 键），等待进程停止即可。

> **如果终端已关或 Ctrl+C 不响应**，逐端口杀进程：
> ```bash
> kill $(lsof -ti:17890)   # 停后端
> kill $(lsof -ti:5173)   # 停前端
> ```

## 技术栈

| 层 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Vite + Tailwind CSS v4 |
| 后端 | Python 3.11+ / FastAPI / Pydantic v2 |
| 依赖管理 | uv |
| 媒体引擎 | FFmpeg（ffmpeg-full） / ffprobe / whisper-cli |
| LLM | DeepSeek / Kimi / OpenAI（默认实现见 `DEFAULTS`） |
| TTS | Xiaomi MiMo / MiniMax（支持 preset / voicedesign / voiceclone 三种模式，见 `DEFAULTS`） |
| Vision | Xiaomi / OpenAI / Claude 兼容接口（默认实现见 `DEFAULTS`） |
| 排期存储 | SQLite |
| 目标平台 | 抖音、小红书、视频号、快手 |

## 配置

运行时统一通过 `packages/provider_config/config_reader.py` 中的 `ConfigReader` / `SecretStore` 读取配置。

```bash
# 复制示例文件并填入真实密钥
cp .env.example .env
```

配置职责：
- `.env` — 保存 API Key 与可选环境变量覆盖
- `config/app_config.json` — 保存 provider、model、voice、thinking 等业务配置
- `config/providers.yaml` — 前端“系统配置”页面的兼容存储；保存时会同步到 `app_config.json` 与 `.env`

常见配置项：
- `LLM_API_KEY` / `TTS_API_KEY` / `VISION_API_KEY` — 通用 key，适合单 provider 场景
- `DEEPSEEK_API_KEY` / `MIMO_API_KEY` / `XIAOMI_VISION_API_KEY` — provider 专用 key，优先级高于通用 key
- provider、model、voice、thinking 等业务参数 — 通常通过前端”系统配置”页面写入 `config/app_config.json`

TTS 配置新增项（`config/app_config.json` 的 `tts` 节）：
- `voice_clone_sample_path` — 音色克隆样本路径（由上传接口自动写入）
- `voice_clone_mime_type` — 样本 MIME 类型（`audio/mpeg` 或 `audio/wav`）
- `optimize_text_preview` — voicedesign 模式下是否启用文本优化预览（默认 `false`）
- `audio_format` — 音频格式（默认 `wav`）

配置优先级：
1. provider 专用环境变量
2. 通用环境变量
3. `config/app_config.json`
4. 代码默认值（`packages/provider_config/app_config.py` 中的 `DEFAULTS`）

## 核心概念

```
工作人员 → Web 前端（React SPA）
                │
           FastAPI 控制面（任务调度 + 状态管理 + 审核门）
                │
           Runtime Worker（拉模式，拉取任务 → 执行 → 上报）
                │
           独立 Service（脚本生成 / TTS / 字幕 / 视频 / FFmpeg）
```

### Job 生命周期（10 步流水线）

```
生成脚本 → [脚本审核] → TTS 配音 → [TTS 审核] → 转录字幕
→ 素材检索 → [素材审核] → 底包拼接 → [终审·烧录] → 已完成
```

`[]` 标记的是人工审核门，需要工作人员在前端确认才能继续。四个审核门：脚本审核、TTS 审核、素材审核、终审·烧录。

**高级选项：**
- **skip_subtitle**：Job 可跳过字幕生成阶段，最终视频不烧录字幕（适用于无字幕输出场景）
- **auto_approve**：Job 可自动跳过所有审核门，实现全自动流水线
- **批量模式**：支持一次性创建多个 Job（`POST /api/projects/{id}/jobs/batch`），每个 Job 可独立配置脚本模式和字幕选项

**Import 模式音画对齐（Issue #179）：** 含场景段的 Job 在 `video_rendering` 阶段把 TTS 配音与字幕整体偏移到混剪段起点（场景段无配音/字幕，仅可有背景音乐），并持久化权威 Final Timeline（`final_timeline.json`，渲染时生成、带稳定内容指纹，记录每段 kind/精确起止/来源），导出包优先嵌入该时间线。

**精确 MP4 分块导出（Issue #181）：** 导出包 `final/` 同时含 `final.mp4` 与按 Final Timeline 精确切分的连续编号 `seg_NNN.mp4`（重编码保证精确边界，每段含对应最终音频/字幕/标题/音乐/视觉，独立可播放）。`timeline.json` 升级为平坦播放顺序的 2.0（每段 `rendered_file` → `seg_NNN.mp4`，montage 段另含可选 `source_file`）。无 Final Timeline 的历史 Job 拒绝导出并要求重渲染（不再回退 legacy 目录推算）。

### Phase 执行状态与重试（Issue #169 / #170）

Job API 响应包含 `execution` 字段（`PhaseExecutionState`），暴露当前 phase 的执行生命周期：`pending / running / retrying / failed / succeeded`、attempt 计数（`current_attempt` / `max_attempts`，默认最多 3 次重试，即最多 4 次总尝试）与结构化错误（`code` / `message` / `retryable`）。结构化 phase 结果模型定义于 `packages/domain_core/phase_execution.py`。

Import 模式媒体 phase 失败时：retryable 错误自动重试至耗尽 attempt，确定性错误立即终态并记录 `failed_phase`。`POST /api/jobs/{id}/retry` 会先 revalidate 失败阶段输入，通过则从失败阶段恢复（保留已有 artifacts）；不通过返回 409 + 结构化 detail。存量失败 job（无 `failed_phase`）回退为重置 `queued` 重试。
## 知识库 API（Issue #28）

上传产品介绍文档，LLM 自动提取结构化知识并注入脚本生成 system prompt。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/knowledge/upload` | POST | 上传 TXT/PDF/DOCX（上限 20MB），返回文档 ID + 提取摘要 |
| `/api/knowledge/documents` | GET | 列出已上传文档 |
| `/api/knowledge/documents/{id}/items` | GET | 查询文档提取结果 |
| `/api/knowledge/selling-points` | GET | 列出卖点，支持 priority/tag 过滤 |
| `/api/knowledge/selling-points/{id}` | PUT | 更新卖点 |
| `/api/knowledge/refresh` | POST | 重新提取所有文档 |

持久化：`workspace/knowledge/documents.json` + `items.json`。

### 脚本模板（Issue #33）

创建可复用的脚本模板，Job 创建时选择模板并填充变量后自动生成 `manual_script`；Import 与 Generate 模式下均可填写或粘贴口播文案，非空时跳过 LLM 生成。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/config/templates` | GET | 列出所有模板 |
| `/api/config/templates` | POST | 创建模板 |
| `/api/config/templates/{id}` | PUT | 更新模板 |
| `/api/config/templates/{id}` | DELETE | 删除模板 |
| `/api/config/templates/{id}/preview` | POST | 预览模板渲染结果 |

持久化：`config/templates/` 目录下的独立 JSON 文件。

```
.
├── apps/
│   ├── control_plane/       # FastAPI 控制面（Web + API + 任务调度）
│   │   ├── routes/           # API 路由聚合层与子路由包
│   │   │   ├── api_jobs.py   # Job 路由聚合层，include routes/jobs/*
│   │   │   ├── api_assets.py # Asset 路由聚合层，include routes/assets/*
│   │   │   ├── jobs/         # Job 子路由（crud / tts / export / content / metadata / migration / cover_title）
│   │   │   ├── assets/       # Asset 子路由（query / index / reclassify / thumbnails / status / ...）
│   │   │   ├── api_projects.py
│   │   │   ├── reviews.py
│   │   │   ├── workers.py
│   │   │   ├── knowledge.py
│   │   │   ├── products.py
│   │   │   ├── config.py
│   │   │   ├── templates.py
│   │   │   ├── tts.py
│   │   │   ├── metrics.py
│   │   │   ├── category_suggestion.py
│   │   │   └── version_check.py
│   │   ├── services/         # 调度器、排期存储
│   │   └── templates/        # 旧 Jinja2 模板（逐步淘汰中）
│   └── runtime_worker/      # 拉模式 worker（poll → execute → report）
│
├── frontend/                 # React 前端（新）
│   └── src/
│       ├── pages/            # 5 个页面
│       ├── components/       # 16 个复用组件
│       ├── api/              # 按领域拆分的 API 客户端（jobs / assets / tts / ...）
│       ├── types/            # 按领域拆分的 TypeScript 类型定义
│       ├── hooks/            # 复用状态逻辑
│       └── context/          # 全局状态上下文
│
├── packages/
│   ├── domain_core/          # 领域模型 + 状态机 + worker 协议
│   ├── file_store/           # 文件系统轻持久化
│   ├── deploy_health/        # 部署体检：CLI + /api/health?deploy_check=true（Issue #76）
│   ├── knowledge_store/      # 知识库：文档、items、LLM 提取（Issue #28）
│   ├── pipeline_services/    # 业务能力（独立 service：脚本/TTS/字幕/视频）
│   │   └── phases/           # Phase handler 实现（由 PhaseOrchestrator 策略表派发）
│   ├── provider_config/      # 统一配置入口与 provider 配置桥接
│   └── runtime_adapters/     # 平台适配（Mac / Windows）
│
├── config/
│   ├── app_config.json       # 业务配置（provider / model / voice / thinking）
│   ├── providers.yaml        # 系统配置页兼容存储，保存时同步到 app_config.json / .env
│   ├── defaults.yaml
│   └── profiles/             # mac-local.yaml / windows-prod.yaml
│
├── tests/                    # pytest 测试
│
└── llm_libraries/            # LLM 能力库（script/packaging/correction）
```

**路由与编排说明：**

- `api_jobs.py` 与 `api_assets.py` 不再包含具体 handler，仅作为 `APIRouter` 聚合层按顺序 `include_router` 子路由；注意子路由的注册顺序（更具体的 `/jobs/{job_id}/...` 路径优先于动态路径 `/jobs/{job_id}`），以避免路径遮蔽。
- `PhaseOrchestrator` 维护 `_handlers` 策略表，将 10 个 phase 派发到 `packages/pipeline_services/phases/` 下对应的 handler；控制面 `auto_tick` 与 `runtime_worker` 共用同一套编排逻辑。

## 可用命令

```bash
# 部署体检（Issue #76）
uv run python -m packages.deploy_health            # CLI 输出 JSON 体检结果

# 健康接口
# GET /api/health?deploy_check=true  — 健康检查，返回 version（pyproject.toml 实时读取）
# GET /api/check-version            — 检查更新，返回 {current, latest, update_available}

# 测试
uv run pytest tests/ -q                # 全量测试

# 构建前端（生产）
cd frontend && npm run build
```

## 前端视觉设计

采用方案 A（左侧步骤条 + 右侧详情），核心色板：

| 角色 | 颜色 | 用途 |
|------|------|------|
| 蓝 | `#0969da` | 完成态步骤、进行中步骤、操作按钮 |
| 黄 | `#e8b931` | 审核高亮步骤 |
| 红 | `#d1242f` | 创建按钮、失败状态、打回操作 |
| 绿 | `#1a7f37` | 已完成状态、质检通过 |
| 灰 | `#59636e` / `#eff2f5` / `#393f46` | 背景、边框、待执行步骤 |

## 智能素材库筛选

智能素材库（全局 `/api/assets`）支持多维度前端筛选：分类、状态、时长（滑块）、关键词、置信度、使用次数。置信度和使用次数在"更多筛选"折叠面板中。支持结果计数、一键清除和空状态提示。

> 旧版 per-project 素材端点（`/{project_id}/assets/*`）已标记为 DEPRECATED，请迁移到全局 `/api/assets` 端点。

## 产品配置

`/system/config/product` 页面支持产品分类管理，包含 AI 智能推荐分类功能：系统根据已有业务数据调用 LLM 建议分类，支持勾选确认后自动合并到现有分类列表。每个分类可配置名称、描述和 Vision Prompt。
