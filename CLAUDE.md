# 项目级规范

github 项目地址：
https://github.com/toRolex/ai-video-pipeline

windows服务器项目路径：进入"C:\Users\ziyua\Documents\Code\old video pipeline"文件夹

## 远程连接（sshpass）

- 需要连接远程服务器时，统一使用 `sshpass` 的非交互命令模式。
- 优先使用环境变量传递密码（`SSHPASS` + `-e`），避免在命令参数里明文使用 `-p`。
- 远程连接模板示例（优先用WSL而不是Powershell或者cmd）：
```bash
SSHPASS='123456' sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 zyt@100.121.152.103 "cmd /c \"cd /d C:\Users\ziyua\Documents\Code\old
      video pipeline && cd && dir\""
```


- 默认只执行只读命令（如 `pwd`、`ls`、`cat`）；涉及修改系统配置、重启服务、删除文件等高风险操作前必须先确认。
repository.

## 项目概述

**滋元堂矩阵流水线 3.0** — Pixelle 风格的 `control-plane + runtime-worker` 短视频自动化生产系统。Phase 1 已完成架构骨架，62 测试全绿。

- 控制面：`apps/control_plane/`（FastAPI + Web 看板，负责状态管理、任务调度、人工审核）
- 执行器：`apps/runtime_worker/`（拉模式 worker，通过 legacy bridge 调用旧核心能力）
- 旧核心（仍被 bridge 引用）：`main_controller.py`（TTS/字幕/视频） + `kimi_two_stage_script.py`（脚本生成）
- 目标平台：抖音、小红书、视频号、快手
- 当前 LLM 提供商：DeepSeek `deepseek-v4-pro`
- 当前 TTS 提供商：Xiaomi MiMo `mimo-v2.5-tts`，随机音色池 `Mia` / `Dean`

## 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Web 框架 | FastAPI + uvicorn + Jinja2 |
| 数据模型 | Pydantic v2 |
| 依赖管理 | uv（`pyproject.toml` + `uv.lock`） |
| 媒体引擎 | FFmpeg / ffprobe / whisper-cli |
| Python 依赖 | `python-dotenv`, `requests`, `httpx`, `fastapi`, `uvicorn`, `jinja2`, `pydantic`, `pyyaml`, `openpyxl`, `Pillow` |
| 排期汇聚 | `openpyxl` 写入 `排期池.xlsx` |
| 测试 | pytest + pytest-asyncio（62 测试） |

**跨平台**：借鉴 Pixelle-Video 兼容方式，业务链路一致，平台差异通过 `runtime_adapters` 收口。mac 开发和联调、Windows 生产执行，同一条流水线。

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
uv run pytest tests/ -q          # 全量 62 测试
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
│   └── runtime_adapters/             # 平台适配（MacLocal / WindowsProd）
│
├── config/
│   ├── defaults.yaml
│   └── profiles/                     # mac-local.yaml / windows-prod.yaml
│
├── packaging/windows/                # Windows 启动器
│
├── tests/                            # 11 个测试文件，62 测试
│
├── main_controller.py                # 旧核心（LegacyMediaBridge 仍在引用）
├── kimi_two_stage_script.py          # 旧脚本生成器（LegacyScriptBridge 仍在引用）
├── llm_libraries/                    # LLM 阶段化能力库（script/packaging/correction）
│
├── pyproject.toml                    # uv 项目配置
├── uv.lock                           # uv 锁定依赖
├── .env / .env.example               # 环境配置（API Key 仅放 .env）
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

## LLM 架构
- 文本任务：DeepSeek `deepseek-v4-pro`（`thinking.type=disabled`）
- TTS 任务：Xiaomi MiMo `mimo-v2.5-tts`
- 可按能力维度配置不同 provider：`SCRIPT_LLM_PROVIDER`、`PACKAGING_LLM_PROVIDER`、`CORRECTION_LLM_PROVIDER`
- 支持 `deepseek`、`kimi`、`openai` 三个 provider
- 脚本生成：两段式（前半段 4 句 + 后半段 4 句），最多 3 次重试，失败后选最短稿特殊放行

## 脚本质检硬条件
- 150-200 字（`compact_len`）
- 品名出现 1 次、品牌"滋元堂"出现 1 次
- 包含"充分烹熟"
- 禁 emoji、禁医疗功效词（治疗/治愈/疗效/降血糖/降血压/抗癌/药到病除）
- 已取消"首句≤20 字、尾句≤20 字"硬条件

## 重要约束

- **API Key 安全**：只放本机 `.env`，不得写入代码、文档、报告或聊天
- **TTS 配额**：MiniMax 日额度有限，MiMo 需关注用量
- **媒体路径**：ffmpeg/ffprobe/whisper 默认走 `tools/bin/`；Whisper 在 Windows 下对中文路径敏感
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
└── runtime_adapters/              # 平台适配（mac / Windows）
```

旧核心文件 (`main_controller.py` + `kimi_two_stage_script.py`) 通过 `Legacy*Bridge` 过渡桥接，后续 Phase 将逐步替换为独立 service。
