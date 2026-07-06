# 项目级规范

github 项目地址：
https://github.com/toRolex/ai-video-pipeline

**Windows 服务器：**
| 环境 | 用户 | 项目路径 |
|------|------|----------|
| 测试机（`100.121.152.103`） | `ziyua` | `C:\Users\ziyua\Documents\Code\ai-video-pipeline` |
| 生产机（`192.168.31.222`） | `zyt18` | 尚未部署（GitHub Actions 推 `main` 自动部署） |

## 项目上下文维护

**每次提交 git 前，必须检查并更新 `CLAUDE.md` 和 `README.md`，确保它们反映最新的项目状态。** 具体包括：
- 新增/移除的功能、API 端点、配置项
- 状态机或流程变更
- 依赖或技术栈变更
- 目录结构变更

## Git Flow 分支规范

**禁止直接在 `main` 和 `develop` 分支上提交任何修改。** 所有开发工作必须按 Git Flow 模型进行：

1. 从 `develop` 切出 `feature/<功能名>` 分支进行开发
2. 完成后合并回 `develop`（使用 `--no-ff`）
3. 发版时从 `develop` 创建 `release-<版本号>` 分支
4. 线上紧急修复从 `main` 切 `hotfix-<版本号>` 分支
5. 合并到 `main` / `develop` 必须使用 `--no-ff` 保留分支历史
6. 每次发布必须在 `main` 上打 tag
7. **每次合并 `release-*` 到 `main` 后，必须发布 Release Note**（使用 `gh release create` 或 `gh release edit`），格式按 Git Flow 规范的 Release Note 章节，包含新功能、问题修复、升级指南等
8. **每次发版前，同步三处版本号：** `pyproject.toml`、`apps/control_plane/app.py`（`/api/health` 接口）、`frontend/package.json`

详见 `/git-flow-conventions` 技能中的完整分支命名、commit message、PR 规范。

## 远程连接（SSH 密钥）

Mac 已配置 SSH 密钥认证到测试机，通过 `~/.ssh/config` 管理连接。

**SSH 配置（`~/.ssh/config`）：**
```
Host zyt
    HostName 100.121.152.103
    User zyt
    Port 22

Host prod-jump
    HostName 192.168.31.222
    User zyt18
    ProxyJump zyt@100.121.152.103
    StrictHostKeyChecking no
```

**快捷连接：**
```bash
# 测试机（直连，密钥认证）
ssh zyt@100.121.152.103 "cmd /c \"cd /d C:\Users\ziyua\Documents\Code\ai-video-pipeline && <命令>\""

# 生产机（跳板，密钥认证）
ssh prod-jump "<命令>"
```

**Windows 机器网络：**
| 机器 | 主机名 | IP | 说明 |
|------|--------|-----|------|
| 测试机 | — | `100.121.152.103:17890` | Tailscale 虚拟 IP，跨网段可用 |
| 测试机 | — | `192.168.31.158:17890` | 局域网直连 IP |
| 生产机 | `brandflow1` | `192.168.31.222:17890` | 局域网 IP，通过测试机跳板连接 |

- 默认只执行只读命令；高风险操作（修改配置、重启、删除）前必须先确认

## 项目概述

**Brandflow 短视频自动化系统 3.0** — `control-plane + runtime-worker` 短视频自动化生产系统。

- 控制面：`apps/control_plane/`（FastAPI + Web 看板，任务调度、审核）
- 执行器：`apps/runtime_worker/`（拉模式 worker，直接调用 `packages/pipeline_services/` 下的独立 service）
- 目标平台：抖音、小红书、视频号、快手
- 默认 LLM：DeepSeek `deepseek-v4-pro`
- 默认 TTS：Xiaomi MiMo（4 种模型，详见下方「LLM / TTS / Vision 架构」）
- 默认 Vision：Xiaomi `mimo-v2.5`

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 后端框架 | FastAPI + Uvicorn |
| 前端框架 | React 19 + TypeScript 5.7 + Tailwind CSS v4 |
| 前端构建 | Vite 6（react + tailwind 插件） |
| 数据模型 | Pydantic v2 |
| 数据持久化 | 文件系统 JSON（FileStore）+ SQLite（排期 + 素材管理） |
| 依赖管理 | uv（`pyproject.toml` + `uv.lock`） |
| 媒体引擎 | FFmpeg / ffprobe / whisper-cli |
| 排期汇聚 | openpyxl → `排期池.xlsx` |
| 测试 | pytest（pytest-asyncio 已安装但当前测试均为同步函数） |

**跨平台**：借鉴 Pixelle-Video 兼容方式，业务链路一致，平台差异通过 `runtime_adapters` 收口。mac 开发和联调、Windows 生产执行，同一条流水线。

## 配置

- 运行时统一通过 `AppConfigManager`（`packages/provider_config/app_config.py`）读取配置
- `get_llm_config()` / `get_tts_config()` / `get_vision_config()` 读取业务配置
- `get_llm_api_key()` / `get_api_key(provider)` / `get_vision_api_key()` 读取 secret
- `get_llm_endpoint()` / `get_api_base_url(provider)` / `get_vision_endpoint()` 读取 endpoint override
- 多产品管理：`switch_product(product_id)` / `list_products()` / `get_product_config(product_id)`
- 旧版单 product 格式自动迁移到新版 products 列表格式（`products` + `active_product_id`）

**环境变量（`.env`）— API Key 优先级：** provider 专用 → 通用回退 → `config/app_config.json` / `DEFAULTS`

| provider | 专用 Key | 通用回退 | 专用 Endpoint | 通用回退 |
|----------|----------|----------|---------------|----------|
| deepseek | `DEEPSEEK_API_KEY` | `LLM_API_KEY` | `DEEPSEEK_API_URL` | `LLM_API_URL` |
| kimi | `KIMI_API_KEY` | `LLM_API_KEY` | `KIMI_API_URL` | `LLM_API_URL` |
| mimo | `MIMO_API_KEY` | `TTS_API_KEY` | `MIMO_API_BASE_URL` | `TTS_API_URL` |
| minimax | `MINIMAX_API_KEY` | `TTS_API_KEY` | `MINIMAX_TTS_URL` | `TTS_API_URL` |
| xiaomi | `XIAOMI_VISION_API_KEY` | `VISION_API_KEY` | `XIAOMI_VISION_API_URL` | `VISION_API_URL` |

**额外环境变量：** `VISION_MODEL` / `XIAOMI_VISION_MODEL`（Vision model override）、`MINIMAX_GROUP_ID`（MiniMax 租户标识）

**Legacy 变量（未被 AppConfigManager 管理，仅在旧代码中直接 `os.getenv`）：**
- `VISION_PROVIDER`（`vision_client.py` L26）
- `EMBEDDING_API_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL`（`retrieval_embedding.py` L48-50）

**`load_provider_config()` 已 deprecated**，但前端配置路由（`routes/config.py`）和 `save_provider_config()` 仍在调用，属于半迁移状态。新代码必须用 `AppConfigManager`。

**`config/app_config.json`** 保存非 secret 业务配置（provider / model / voice / thinking / scene），与 `DEFAULTS` 深度合并。`providers.yaml` 是前端系统配置页兼容存储，保存时同步到 `app_config.json` 和 `.env`。

**Scene 配置（Import 模式）：**
```json
{
  "scene": {
    "folders": [
      {"name": "品牌开场", "path": "scene/brand-intro"},
      {"name": "产品展示", "path": "scene/product-show"}
    ],
    "transition_duration_ms": 500
  }
}
```
- `scene.folders`：场景素材文件夹列表（`path` 相对于 `workspace/` 目录）
- `scene.transition_duration_ms`：场景片段之间的交叉淡入淡出过渡时长（默认 500ms）
- 通过 `AppConfigManager.get_scene_config()` 读取

## 关键命令

### 控制面启动
```bash
# 启动 FastAPI + Web 看板（默认端口 17890）
uv run python -m apps.control_plane
```

### Worker 启动
```bash
# mac 本地开发
uv run python -m apps.runtime_worker

# 指定产品
PRODUCT=羊肚菌 uv run python -m apps.runtime_worker

# Windows 生产
packaging\windows\start_worker.bat
```

### 测试
```bash
uv run pytest tests/ -q          # 全量测试
uv run pytest tests/ -q --tb=short
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects/{id}/jobs` | POST | 创建单个 Job |
| `/api/projects/{id}/jobs/batch` | POST | 批量创建 Job（`BatchCreateRequest`：product、platforms、auto_approve、jobs 列表） |
| `/api/knowledge/upload` | POST | 上传 TXT/PDF/DOCX（上限 20MB），LLM 提取结构化知识，返回文档 ID + 提取摘要 |
| `/api/knowledge/documents` | GET | 列出已上传知识库文档 |
| `/api/knowledge/documents/{id}/items` | GET | 查询某文档的提取结果（items） |
| `/api/knowledge/selling-points` | GET | 列出卖点（支持 priority_min/max、tags 过滤） |
| `/api/knowledge/selling-points/{item_id}` | PUT | 更新卖点字段（title/content/priority/tags） |
| `/api/knowledge/refresh` | POST | 重新解析所有已上传文档并提取知识条目 |
| `/api/tts/voice-clone-sample` | POST | 上传音色克隆音频样本（mp3/wav，上限 10MB），自动更新 TTSConfig |
| `/api/tts/preview` | POST | TTS 预览（支持 voicedesign + optimize_text_preview + voiceclone） |
| `/workers/poll` | POST | Worker 轮询取任务 |
| `/workers/tasks/{id}/report` | POST | Worker 上报执行结果 |
| `/api/products` | GET | 列出所有产品摘要 `[{id, name}]` |
| `/api/products/{product_id}/switch` | POST | 切换活跃产品，不存在时自动创建 |
| `/api/products/{product_id}/config` | GET | 读取指定产品的完整配置 |
| `/api/products/{product_id}/config` | PUT | 更新指定产品的配置 |
| `/api/config/templates` | GET | 列出所有脚本模板 |
| `/api/config/templates` | POST | 创建脚本模板 |
| `/api/config/templates/{id}` | PUT | 更新脚本模板 |
| `/api/config/templates/{id}` | DELETE | 删除脚本模板 |
| `/api/config/templates/{id}/preview` | POST | 预览模板 + 变量填充结果 |

### 知识库（Issue #28）

- `packages/knowledge_store/`：知识库领域模型 + JSON 持久化 + LLM 提取。
  - `models.py`：`KnowledgeDocument` / `KnowledgeItem` / `KnowledgeConfig`。
  - `store.py`：`KnowledgeStore`，数据持久化到 `workspace/knowledge/documents.json` 与 `items.json`。
  - `extractor.py`：`KnowledgeExtractor`，按 2000 字符分块调用 `LLMClient` 提取卖点/规格/禁用词/品牌调性/使用场景。
  - `parsers.py`：TXT/PDF/DOCX 文本解析（TXT 直接 UTF-8 读取）。
- `ScriptGenerator.run(knowledge_config=...)` 启用时从 `KnowledgeStore` 按 priority 召回 top-K 卖点，追加到 system prompt；卖点为空时静默跳过。

### 脚本模板（Issue #33）

- `packages/script_template/`：脚本模板领域模型 + JSON 文件存储 + 渲染引擎。
  - `models.py`：`ScriptTemplate` / `TemplateSlot` / `TemplateVariable`。
  - `store.py`：`ScriptTemplateStore`，每个模板一个 JSON 文件存储在 `config/templates/` 下。
  - `renderer.py`：模板 + 变量值 → 渲染 `manual_script`。
- 前端路由：
  - `/system/config/templates` — 模板列表（CRUD）
  - `/system/config/templates/:id` — 模板编辑（slots / variables 编辑）
- Job 创建（Import 模式）：选择模板 → 填写变量 → 自动生成 `manual_script` → 写入 JobRecord。

### 多产品配置（Issue #34）

- `app_config.json` 的 `product` 单一段已扩展为 `products`（复数）+ `active_product_id`。
- `AppConfigManager`：
  - `switch_product(product_id)` — 切换当前活跃产品
  - `list_products()` — 返回所有产品配置摘要 `[{id, name}]`
  - `get_product_config(product_id=None)` — 取指定/当前产品配置
  - `save_product_config(product_id, config)` — 保存指定产品配置
- `POST /api/products/{id}/switch` 切换不存在的产品时会自动创建。
- 前端导航栏已集成全局产品选择器 dropdown，切换后所有配置页加载对应产品数据。
- 旧 `product` 单数段格式自动迁移到 `products` 列表格式。

## 目录结构

```
.
├── apps/
│   ├── control_plane/                # Phase 1 控制面（FastAPI + Web + 任务调度）
│   │   ├── app.py                    # FastAPI app factory
│   │   ├── routes/                   # projects, jobs, reviews, workers, knowledge, products, config, templates
│   │   ├── services/                 # dispatch.py, reconcile.py
│   │   └── templates/                # Jinja2 页面
│   └── runtime_worker/              # Phase 1 执行器（拉模式 worker）
│       ├── loop.py                   # WorkerLoop（poll → execute → report）
│       └── http_client.py            # WorkerHttpClient
│
├── packages/
│   ├── domain_core/                  # 领域模型、状态机、worker 协议
│   ├── file_store/                   # 文件系统轻持久化
│   ├── knowledge_store/              # 知识库：文档、items、LLM 提取（Issue #28）
│   │   ├── models.py                 # KnowledgeDocument / KnowledgeItem / KnowledgeConfig
│   │   ├── store.py                  # KnowledgeStore（documents.json / items.json）
│   │   ├── extractor.py              # KnowledgeExtractor（调用 LLMClient）
│   │   └── parsers.py                # TXT/PDF/DOCX 文本解析
│   ├── script_template/               # 脚本模板：模型、存储、渲染（Issue #33）
│   │   ├── models.py                  # ScriptTemplate / TemplateSlot / TemplateVariable
│   │   ├── store.py                   # ScriptTemplateStore（config/templates/*.json）
│   │   └── renderer.py               # 模板 + 变量 → manual_script
│   ├── pipeline_services/            # 业务能力（独立 service + phase runner）
│   │   ├── llm_client.py             # 通用 LLM HTTP 客户端
│   │   ├── script_service/           # 脚本生成
│   │   │   ├── generator.py          # ScriptGenerator 核心类
│   │   │   ├── prompts.py            # Prompt 模板构造
│   │   │   └── quality.py            # 脚本质检
│   │   ├── tts_provider.py           # TTS 语音合成（含 synthesize()）
│   │   ├── subtitle_service.py       # SRT 字幕生成
│   │   ├── video_service.py          # 视频组装与烧录
│   │   ├── media_utils.py            # 媒体工具（FFmpeg 路径解析等）
│   │   ├── legacy_script_bridge.py   # LegacyScriptBridge（已改写为使用 ScriptGenerator）
│   │   ├── asset_library/            # 素材库能力
│   │   ├── tts_monitor.py            # TTS 用量监控
│   │   ├── retrieval_contract.py     # 检索契约
│   │   ├── retrieval_embedding.py    # 向量检索
│   │   ├── retrieval_keyword.py      # 关键词检索
│   │   ├── phase_runner.py           # Phase 执行器
│   │   ├── phase_orchestrator.py     # PhaseOrchestrator：策略分发，每个 phase 一个 handler（含 scene_assembling / montage_assembling ffmpeg 实现）
│   │   └── job_tick_service.py       # Job 生命周期 tick 调度（双模式 _compute_transition）
│   ├── provider_config/              # AppConfigManager + provider 配置桥接
│   └── runtime_adapters/             # 平台适配（MacLocal / WindowsProd）
│
├── config/
│   ├── app_config.json               # 非 secret 业务配置（provider / model / voice / thinking）
│   ├── providers.yaml                # 系统配置页兼容存储，保存时同步到 app_config.json / .env
│   ├── defaults.yaml
│   └── profiles/                     # mac-local.yaml / windows-prod.yaml
│
├── packaging/windows/                # Windows 启动器
│
├── tests/                            # pytest 测试
│
├── llm_libraries/                    # LLM 阶段化能力库（script/packaging/correction）
│
├── pyproject.toml                    # uv 项目配置
├── uv.lock                           # uv 锁定依赖
├── .env / .env.example               # 环境变量（secret + 可选 override）
├── dynamic_rules.txt                 # LLM 动态规则库
├── 爆款对标_人工投放.txt              # 人工维护的爆款对标上下文
│
├── docs/                             # 文档（spec、plan、PRD）
└── tools/
    └── build_segment_index.py        # 检索索引构建脚本（skeleton）
```

## 状态机与任务流

### Job 主状态 `phase`（双模式）

```
Generate 模式：
queued → script_generating → script_review → tts_generating → tts_review → subtitle_generating
→ asset_retrieving → asset_review → video_rendering → final_rendering → final_review
→ completed

Import 模式：
queued → scene_assembling ←(parallel)── tts_generating
          ↓
       montage_assembling → asset_retrieving → asset_review → video_rendering
       (复用现有 clip → final_rendering → final_review → completed)
```

- **Generate 模式**：LLM 生成脚本 → TTS → 素材检索 → 视频合成
- **Import 模式**：从场景素材文件夹随机选取视频 → scene_assembling（与 TTS 并行）→ montage_assembling 拼接场景段和素材段 → 复用现有渲染流水线
- Import 模式自动跳过 `script_review` 和 `tts_review` 审核门
- `mode: "import" | "generate"` 字段在 JobRecord 上，创建时指定

异常出口：`failed` / `cancelled` / `paused`

**审核状态 `review_status`：** `none` → `pending` → `approved` / `rejected` / `overridden`

**第一阶段固定 4 个审核门：** `script_review` / `tts_review` / `asset_review` / `final_review`

**JobRecord 关键字段：**
- `skip_subtitle: bool = False` — 设为 True 时，`auto_tick` 跳过 `subtitle_generating` 阶段，最终视频不烧录字幕
- `auto_approve: bool = False` — 设为 True 时，`auto_tick` 自动审核通过所有 review gate，无需人工确认

### 控制面与 Worker 协议

- **拉模式**：worker 主动轮询 `POST /workers/poll` 取任务
- **Lease**：每次派发生成 `lease_id + attempt_id`，worker 需持有有效 lease
- **Report**：worker 通过 `POST /workers/tasks/{task_id}/report` 上报结果
- **Stale 保护**：`choose_report_outcome()` 拒绝过期 attempt/lease 的 report
- **状态真相**：control-plane 是唯一状态写入者，worker 只做副作用

### auto_tick 自动推进

- 控制面通过 `_auto_tick` 后台循环（默认 `DEV_AUTO_TICK=1`，间隔 3 秒）自动推进 job phase
- `skip_subtitle=True` 时，字幕阶段直接跳到下一阶段
- `auto_approve=True` 时，所有 review gate 自动设 `review_status=approved` 并推进
- `list_jobs` 按文件 mtime 排序，返回 `display_index`（格式如 `001`、`002`）
- 可通过环境变量 `DEV_AUTO_TICK=0` 关闭

## 前端系统配置页

Phase 5 新增运营人员配置面板：

| 路由 | 组件 | 说明 |
|------|------|------|
| `/system/config/product` | `ProductConfigForm` | 产品名/品牌/场景/素材/系统提示词表单 |
| `/system/config/templates` | `ScriptTemplateList` | 脚本模板列表（CRUD） |
| `/system/config/templates/:id` | `ScriptTemplateEditor` | 模板编辑（slots + variables） |
| `/system/config/categories` | `CategoryManager` | 素材分类管理（新增/编辑/删除/AI 建议） |
| `/system/config/quality` | `QualityRulesForm` | 质检规则（字数/禁词/emoji/恢复默认） |

所有页面已使用 CSS 变量适配暗色模式。

## 前端智能素材库筛选

智能素材库（`SmartAssetLibrary.tsx`）支持多维度前端内存筛选：

- **分类**（dropdown）、**状态**（dropdown：可用/已禁用/待审核）
- **时长**（双端滑块，动态范围从数据计算）
- **关键词**（file_path / tags 子串匹配）
- **置信度**（min/max 数字输入，0-1，步长 0.1，折叠面板）
- **使用次数**（min/max 整数输入，折叠面板）

筛选类型定义在 `frontend/src/types/index.ts` 的 `AssetFilters` 接口。所有筛选为纯前端过滤，AND 逻辑组合。

## 项目命名规则
- Phase 1 新系统不再沿用旧的 `001xxx` 目录结构，项目数据统一落在 `workspace/projects/{project_id}/`
- 旧规则（`001见手青` 等旧项目已在清理中移除）

## LLM / TTS / Vision 架构
- 文本能力支持 `deepseek`、`kimi`、`openai`，默认值见 `AppConfigManager.DEFAULTS["llm"]`
- TTS 能力支持 `mimo`、`minimax`，默认值见 `AppConfigManager.DEFAULTS["tts"]`
- TTS 模型支持 4 种模式：`mimo-v2.5-tts`（预置音色）、`mimo-v2.5-tts-voicedesign`（音色设计）、`mimo-v2.5-tts-voiceclone`（音色克隆）、`mimo-v2-tts`（V2 预置），默认音色池 `Mia` / `Dean`
- TTS 配置新增字段：`voice_clone_sample_path`（克隆样本路径）、`voice_clone_mime_type`（样本 MIME）、`optimize_text_preview`（voicedesign 文本优化预览，默认 `False`）
- TTS 音频格式默认值为 `wav`
- Vision 能力支持 `xiaomi`、`openai`、`claude` 兼容接口，默认值见 `AppConfigManager.DEFAULTS["vision"]`
- 运行时优先通过 `get_llm_config()`、`get_tts_config()`、`get_vision_config()` 读取业务配置，通过 `get_llm_api_key()`、`get_api_key(provider)`、`get_vision_api_key()` 读取 secret
- 旧的 `SCRIPT_LLM_PROVIDER`、`PACKAGING_LLM_PROVIDER`、`CORRECTION_LLM_PROVIDER` 仅属于 legacy fallback，不应作为新配置入口
- 脚本生成：两段式（前半段 4 句 + 后半段 4 句），最多 3 次重试，失败后选最短稿特殊放行

## 脚本质检硬条件
- 150-200 字（`compact_len`）
- 品名出现 1 次（品名由 Job 的 `product` 字段动态指定，无硬编码默认值）
- 品牌名出现 1 次（仅在 `brand` 字段非空时检查，`brand` 为空时跳过品牌计数）
- ~~包含"充分烹熟"~~（已移除，安全短语不再硬编码）
- 禁 emoji、禁医疗功效词（治疗/治愈/疗效/降血糖/降血压/抗癌/药到病除）
- 已取消"首句≤20 字、尾句≤20 字"硬条件
- **粤语版**：宽松规则，品名/品牌仅检查是否出现（不限制次数），无烹熟同义词要求

## 重要约束

- **API Key 安全**：secret 只放本机 `.env`，不得写入代码、文档、报告或聊天
- **TTS 配额**：MiniMax 日额度有限，MiMo 需关注用量
- **媒体路径**：默认值以 `AppConfigManager.DEFAULTS` 与部署环境覆盖为准；Windows 可通过环境变量或 profile 覆盖。Whisper 在 Windows 下对中文路径敏感
- **Python 版本**：需要 Python 3.11+（通过 `uv run` / `uv sync` 管理）
- **平台**：Phase 1 架构已支持跨平台（mac 开发 + Windows 生产），平台差异收口在 `runtime_adapters` 层

## 模块化计划

**Phase 1 架构拆分已完成。旧核心文件（`main_controller.py`、`kimi_two_stage_script.py`）及 LegacyBridge（`legacy_media_bridge.py`、`legacy_schedule_bridge.py`）已全部移除。**

当前状态：
- 所有能力已迁移至 `packages/pipeline_services/` 下的独立 service：
  - `script_service/`（脚本生成：generator.py + prompts.py + quality.py）
  - `tts_provider.py`（TTS 语音合成，含 `synthesize()`）
  - `subtitle_service.py`（SRT 字幕生成）
  - `video_service.py`（视频组装与烧录）
  - `phase_orchestrator.py`（PhaseOrchestrator：策略分发，覆盖 Generate/Import 双模式，含 scene_assembling ffmpeg xfade 交叉淡入淡出和 montage_assembling concat 拼接）
  - `llm_client.py`（通用 LLM HTTP 客户端）
  - `job_tick_service.py`（Job 生命周期 tick 调度：_compute_transition 纯函数 + JobTickService，支持 import-mode parallel dispatch）
- `legacy_script_bridge.py` 保留，已改写为使用 `ScriptGenerator`

## Agent skills

### Issue tracker

GitHub Issues（`gh` CLI）。See `docs/agents/issue-tracker.md`.

### Triage labels

五个标准角色：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context：`CONTEXT.md`（根目录）+ `docs/adr/`。See `docs/agents/domain.md`.

<!-- superpowers-zh:begin (do not edit between these markers) -->
# Superpowers-ZH 中文增强版

本项目已安装 superpowers-zh 技能框架（20 个 skills）。

## 核心规则

1. **收到任务时，先检查是否有匹配的 skill** — 哪怕只有 1% 的可能性也要检查
2. **设计先于编码** — 收到功能需求时，先用 brainstorming skill 做需求分析
3. **测试先于实现** — 写代码前先写测试（TDD）
4. **验证先于完成** — 声称完成前必须运行验证命令

## 可用 Skills

Skills 位于 `.claude/skills/` 目录，每个 skill 有独立的 `SKILL.md` 文件。

- **brainstorming**: 在任何创造性工作之前必须使用此技能——创建功能、构建组件、添加功能或修改行为。在实现之前先探索用户意图、需求和设计。
- **chinese-code-review**: 中文 review 沟通参考——话术模板、分级标注（必须修复/建议修改/仅供参考）、国内团队常见反模式应对。仅在用户显式 /chinese-code-review 时调用，不要根据上下文自动触发。
- **chinese-commit-conventions**: 中文 commit 与 changelog 配置参考——Conventional Commits 中文适配、commitlint/husky/commitizen 中文模板、conventional-changelog 中文配置。仅在用户显式 /chinese-commit-conventions 时调用，不要根据上下文自动触发。
- **chinese-documentation**: 中文文档排版参考——中英文空格、全半角标点、术语保留、链接格式、中文文案排版指北约定。仅在用户显式 /chinese-documentation 时调用，不要根据上下文自动触发。
- **chinese-git-workflow**: 国内 Git 平台配置参考——Gitee、Coding.net、极狐 GitLab、CNB 的 SSH/HTTPS/凭据/CI 接入差异与镜像同步配置。仅在用户显式 /chinese-git-workflow 时调用，不要根据上下文自动触发。
- **dispatching-parallel-agents**: 当面对 2 个以上可以独立进行、无共享状态或顺序依赖的任务时使用
- **executing-plans**: 当你有一份书面实现计划需要在单独的会话中执行，并设有审查检查点时使用
- **finishing-a-development-branch**: 当实现完成、所有测试通过、需要决定如何集成工作时使用——通过提供合并、PR 或清理等结构化选项来引导开发工作的收尾
- **mcp-builder**: MCP 服务器构建方法论 — 系统化构建生产级 MCP 工具，让 AI 助手连接外部能力
- **receiving-code-review**: 收到代码审查反馈后、实施建议之前使用，尤其当反馈不明确或技术上有疑问时——需要技术严谨性和验证，而非敷衍附和或盲目执行
- **requesting-code-review**: 完成任务、实现重要功能或合并前使用，用于验证工作成果是否符合要求
- **subagent-driven-development**: 当在当前会话中执行包含独立任务的实现计划时使用
- **systematic-debugging**: 遇到任何 bug、测试失败或异常行为时使用，在提出修复方案之前执行
- **test-driven-development**: 在实现任何功能或修复 bug 时使用，在编写实现代码之前
- **using-git-worktrees**: 当需要开始与当前工作区隔离的功能开发，或在执行实现计划之前使用——通过原生工具或 git worktree 回退机制确保隔离工作区存在
- **using-superpowers**: 在开始任何对话时使用——确立如何查找和使用技能，要求在任何响应（包括澄清性问题）之前调用 Skill 工具
- **verification-before-completion**: 在宣称工作完成、已修复或测试通过之前使用，在提交或创建 PR 之前——必须运行验证命令并确认输出后才能声称成功；始终用证据支撑断言
- **workflow-runner**: 在 Claude Code / OpenClaw / Cursor 中直接运行 agency-orchestrator YAML 工作流——无需 API key，使用当前会话的 LLM 作为执行引擎。当用户提供 .yaml 工作流文件或要求多角色协作完成任务时触发。
- **writing-plans**: 当你有规格说明或需求用于多步骤任务时使用，在动手写代码之前
- **writing-skills**: 当创建新技能、编辑现有技能或在部署前验证技能是否有效时使用

## 如何使用

当任务匹配某个 skill 时，使用 `Skill` 工具加载对应 skill 并严格遵循其流程。绝不要用 Read 工具读取 SKILL.md 文件。

如果你认为哪怕只有 1% 的可能性某个 skill 适用于你正在做的事情，你必须调用该 skill 检查。
<!-- superpowers-zh:end -->
