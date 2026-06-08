# 项目级规范

github 项目地址：
https://github.com/toRolex/ai-video-pipeline

windows服务器项目路径：进入"C:\Users\ziyua\Documents\Code\ai-video-pipeline"文件夹

## 远程连接（sshpass）

- 需要连接远程服务器时，统一使用 `sshpass` 的非交互命令模式。
- 优先使用环境变量传递密码（`SSHPASS` + `-e`），避免在命令参数里明文使用 `-p`。
- 远程连接模板示例（优先用WSL而不是Powershell或者cmd）：
```bash
SSHPASS='123456' sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 zyt@100.121.152.103 "cmd /c \"cd /d C:\Users\ziyua\Documents\Code\ai-video-pipeline && cd && dir\""
```

- 默认只执行只读命令（如 `pwd`、`ls`、`cat`）；涉及修改系统配置、重启服务、删除文件等高风险操作前必须先确认。

## 项目概述

**滋元堂矩阵流水线 3.0** — Pixelle 风格的 `control-plane + runtime-worker` 短视频自动化生产系统。Phase 1 已完成架构骨架。

- 控制面：`apps/control_plane/`（FastAPI + Web 看板，负责状态管理、任务调度、人工审核）
- 执行器：`apps/runtime_worker/`（拉模式 worker，通过 legacy bridge 调用旧核心能力）
- 旧核心（仍被 bridge 引用）：`main_controller.py`（TTS/字幕/视频） + `kimi_two_stage_script.py`（脚本生成）
- 目标平台：抖音、小红书、视频号、快手
- 默认 LLM 配置（见 `AppConfigManager.DEFAULTS`）：DeepSeek `deepseek-v4-pro`，`thinking=disabled`
- 默认 TTS 配置（见 `AppConfigManager.DEFAULTS`）：Xiaomi MiMo，支持 4 种模型：`mimo-v2.5-tts`（预置音色）、`mimo-v2.5-tts-voicedesign`（音色设计）、`mimo-v2.5-tts-voiceclone`（音色克隆）、`mimo-v2-tts`（V2 预置），默认音色池 `Mia` / `Dean`
- 默认 Vision 配置（见 `AppConfigManager.DEFAULTS`）：Xiaomi `mimo-v2.5`

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 后端框架 | FastAPI + Uvicorn |
| 前端框架 | React 19 + TypeScript 5.7 + Tailwind CSS v4 |
| 前端构建 | Vite 6（react + tailwind 插件） |
| 数据模型 | Pydantic v2 |
| 数据持久化 | 文件系统 JSON（FileStore）+ SQLite（排期） |
| 依赖管理 | uv（`pyproject.toml` + `uv.lock`） |
| 媒体引擎 | FFmpeg / ffprobe / whisper-cli |
| 排期汇聚 | openpyxl → `排期池.xlsx` |
| 测试 | pytest + pytest-asyncio |

**跨平台**：借鉴 Pixelle-Video 兼容方式，业务链路一致，平台差异通过 `runtime_adapters` 收口。mac 开发和联调、Windows 生产执行，同一条流水线。

## 核心环境变量

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | 当前 LLM provider 的通用回退 key |
| `TTS_API_KEY` | 当前 TTS provider 的通用回退 key |
| `VISION_API_KEY` | 当前 Vision provider 的通用回退 key |
| `DEEPSEEK_API_KEY` / `KIMI_API_KEY` | provider 专用 LLM key |
| `MIMO_API_KEY` / `MINIMAX_API_KEY` | provider 专用 TTS key |
| `MINIMAX_GROUP_ID` | MiniMax TTS 额外租户标识（legacy 代码仍直接读取） |
| `XIAOMI_VISION_API_KEY` | Xiaomi Vision 专用 key |
| `LLM_API_URL` / `TTS_API_URL` / `VISION_API_URL` | 通用 endpoint override |
| `DEEPSEEK_API_URL` / `KIMI_API_URL` / `MIMO_API_BASE_URL` / `MINIMAX_TTS_URL` / `XIAOMI_VISION_API_URL` | provider 专用 endpoint override |
| `VISION_MODEL` / `XIAOMI_VISION_MODEL` | Vision model override |

## 配置系统架构

- 运行时统一通过 `packages/provider_config/app_config.py` 中的 `AppConfigManager` 读取配置。
- `get_llm_config()`、`get_tts_config()`、`get_vision_config()` 读取业务配置；`get_llm_api_key()`、`get_api_key(provider)`、`get_vision_api_key()` 读取 secret。
- `config/app_config.json` 保存 provider、model、voice、thinking 等非 secret 业务配置，并与 `AppConfigManager.DEFAULTS` 深度合并。
- `.env` 保存 API Key 与可选环境变量覆盖；优先级为 provider 专用环境变量 → 通用环境变量 → `config/app_config.json` / `DEFAULTS`。
- 前端 `/api/config` 仍经 `apps/control_plane/routes/config.py` 调用 `packages/provider_config/store.py` 兼容 `providers.yaml`。
- `load_provider_config()` 已 deprecated；`save_provider_config()` 保存时会把 secret 同步到 `.env`，把业务配置同步到 `config/app_config.json`。
- 新代码读取配置时优先使用 `AppConfigManager`，不要把 `providers.yaml`、`tts_config.json` 或零散 `os.getenv(...)` 当作主入口。

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

### 旧工具（仍可用，legacy bridge 链路）
```bash
# 文案生成（独立工具）
uv run --project . kimi_two_stage_script.py 见手青 --mock
uv run --project . kimi_two_stage_script.py 羊肚菌 --interval-seconds 10
```

## 目录结构

```
.
├── apps/
│   ├── control_plane/                # Phase 1 控制面（FastAPI + Web + 任务调度）
│   │   ├── app.py                    # FastAPI app factory
│   │   ├── routes/                   # projects, jobs, reviews, workers
│   │   ├── services/                 # dispatch.py, reconcile.py
│   │   └── templates/                # Jinja2 页面
│   └── runtime_worker/              # Phase 1 执行器（拉模式 worker）
│       ├── loop.py                   # WorkerLoop（poll → execute → report）
│       └── http_client.py            # WorkerHttpClient
│
├── packages/
│   ├── domain_core/                  # 领域模型、状态机、worker 协议
│   ├── file_store/                   # 文件系统轻持久化
│   ├── pipeline_services/            # 业务能力（bridge、检索、phase runner）
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
├── main_controller.py                # 旧核心（LegacyMediaBridge 仍在引用）
├── kimi_two_stage_script.py          # 旧脚本生成器（LegacyScriptBridge 仍在引用）
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

### Phase 1 状态机（`packages/domain_core/`）

**Job 主状态 `phase`：**
```
queued → script_generating → script_review → tts_generating → subtitle_generating
→ asset_retrieving → asset_review → video_rendering → final_review
→ schedule_writing → completed
```

异常出口：`failed` / `cancelled` / `paused`

**审核状态 `review_status`：** `none` → `pending` → `approved` / `rejected` / `overridden`

**第一阶段固定 3 个审核门：** `script_review` / `asset_review` / `final_review`

### 控制面与 Worker 协议

- **拉模式**：worker 主动轮询 `POST /workers/poll` 取任务
- **Lease**：每次派发生成 `lease_id + attempt_id`，worker 需持有有效 lease
- **Report**：worker 通过 `POST /workers/tasks/{task_id}/report` 上报结果
- **Stale 保护**：`choose_report_outcome()` 拒绝过期 attempt/lease 的 report
- **状态真相**：control-plane 是唯一状态写入者，worker 只做副作用

### 旧 TaskState（main_controller.py，legacy bridge 仍引用）
```
init → api_assets_done → video_base_done → srt_corrected → burn_completed
```

## 项目命名规则
- Phase 1 新系统不再沿用旧的 `001xxx` 目录结构，项目数据统一落在 `workspace/projects/{project_id}/`
- 旧规则（`001见手青` 等旧项目已在清理中移除）

## LLM / TTS / Vision 架构
- 文本能力支持 `deepseek`、`kimi`、`openai`，默认值见 `AppConfigManager.DEFAULTS["llm"]`
- TTS 能力支持 `mimo`、`minimax`，默认值见 `AppConfigManager.DEFAULTS["tts"]`
- Vision 能力支持 `xiaomi`、`openai`、`claude` 兼容接口，默认值见 `AppConfigManager.DEFAULTS["vision"]`
- 运行时优先通过 `get_llm_config()`、`get_tts_config()`、`get_vision_config()` 读取业务配置，通过 `get_llm_api_key()`、`get_api_key(provider)`、`get_vision_api_key()` 读取 secret
- 旧的 `SCRIPT_LLM_PROVIDER`、`PACKAGING_LLM_PROVIDER`、`CORRECTION_LLM_PROVIDER` 仅属于 legacy fallback，不应作为新配置入口
- 脚本生成：两段式（前半段 4 句 + 后半段 4 句），最多 3 次重试，失败后选最短稿特殊放行

## 脚本质检硬条件
- 150-200 字（`compact_len`）
- 品名出现 1 次、品牌"滋元堂"出现 1 次
- 包含"充分烹熟"
- 禁 emoji、禁医疗功效词（治疗/治愈/疗效/降血糖/降血压/抗癌/药到病除）
- 已取消"首句≤20 字、尾句≤20 字"硬条件

## 重要约束

- **API Key 安全**：secret 只放本机 `.env`，不得写入代码、文档、报告或聊天
- **TTS 配额**：MiniMax 日额度有限，MiMo 需关注用量
- **媒体路径**：默认值以 `AppConfigManager.DEFAULTS` 与部署环境覆盖为准；Windows 可通过环境变量或 profile 覆盖。Whisper 在 Windows 下对中文路径敏感
- **Python 版本**：需要 Python 3.11+（通过 `uv run` / `uv sync` 管理）
- **平台**：Phase 1 架构已支持跨平台（mac 开发 + Windows 生产），平台差异收口在 `runtime_adapters` 层

## 关键常量（main_controller.py）

| 常量 | 值 | 含义 |
|------|---|------|
| `DEFAULT_BATCH_SIZE` | 10 | 默认批次大小 |
| `TARGET_FINAL_VIDEO_MIN_SECONDS` | 35 | 目标视频最短时长 |
| `TARGET_FINAL_VIDEO_MAX_SECONDS` | 45 | 目标视频最长时长 |
| `MIN_VIDEO_SCRIPT_CHARS` | 150 | 脚本最短字数 |
| `MAX_VIDEO_SCRIPT_CHARS` | 200 | 脚本最长字数 |
| `MIN_REQUIRED_SOURCE_SECONDS` | 300 | 原素材累计最小时长 |
| `CLIP_DURATION_SECONDS` | 5 | 单切片时长 |
| `CLIPS_PER_GROUP` | 5 | 每组切片数 |
| `SLICE_GROUP_COUNT` | 9 | 切片组数 |
| `MAX_CLIP_REUSE` | 2 | 单一切片最大复用次数 |
| `SCRIPT_GENERATION_MAX_ATTEMPTS` | 3 | 脚本最大重试次数 |
| `MEDIA_MAX_RETRY` | 3 | 媒体操作最大重试 |

## 模块化计划

~~当前单体文件 `main_controller.py` 约 199KB，计划拆分为：~~  **已完成（Phase 1）。**

Phase 1 已将架构拆分为 `control-plane + runtime-worker + shared-core`：

```
apps/                              # 双应用
├── control_plane/                 # FastAPI + Web + 任务调度 + 人工审核
└── runtime_worker/                # 拉模式 worker（poll → execute → report）

packages/                          # 共享核心
├── domain_core/                   # 领域模型 + 状态机 + worker 协议
├── file_store/                    # 文件系统轻持久化
├── pipeline_services/             # 业务能力 + legacy bridge
├── provider_config/               # LLM/TTS provider 配置与路由
└── runtime_adapters/              # 平台适配（mac / Windows）
```

旧核心文件 (`main_controller.py` + `kimi_two_stage_script.py`) 通过 `Legacy*Bridge` 过渡桥接，后续 Phase 将逐步替换为独立 service。

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
