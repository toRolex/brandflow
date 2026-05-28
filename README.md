# 滋元堂短视频矩阵流水线 3.0

AI 驱动的短视频自动化生产系统，基于 `control-plane + runtime-worker` 架构。工作人员通过 Web 前端完成全流程操作，无需命令行。

## 快速启动

```bash
# 1. 安装后端依赖
uv sync

# 2. 配置 API Key（复制 .env.example 为 .env，填入密钥）
cp .env.example .env

# 3. 安装前端依赖
cd frontend && npm install && cd ..
```

### 启动

**需要同时开两个终端窗口** — 一个跑后端，一个跑前端。

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
| 媒体引擎 | FFmpeg / ffprobe / whisper-cli |
| LLM | DeepSeek `deepseek-v4-pro` |
| TTS | Xiaomi MiMo `mimo-v2.5-tts` |
| 排期存储 | SQLite |
| 目标平台 | 抖音、小红书、视频号、快手 |

## 核心概念

```
工作人员 → Web 前端（React SPA）
                │
           FastAPI 控制面（任务调度 + 状态管理 + 审核门）
                │
           Runtime Worker（拉模式，拉取任务 → 执行 → 上报）
                │
           旧核心能力（脚本生成 / TTS / 字幕 / FFmpeg）
```

### Job 生命周期（8 步流水线）

```
生成脚本 → [脚本审核] → TTS 配音 → 转录字幕
→ 底包拼接 → [终审·烧录] → 已完成
```

`[]` 标记的是人工审核门，需要工作人员在前端确认才能继续。两个审核门：脚本审核、终审·烧录。

## 目录结构

```
.
├── apps/
│   ├── control_plane/       # FastAPI 控制面（Web + API + 任务调度）
│   │   ├── routes/           # API 路由（projects/jobs/reviews/workers）
│   │   ├── services/         # 调度器、排期存储
│   │   └── templates/        # 旧 Jinja2 模板（逐步淘汰中）
│   └── runtime_worker/      # 拉模式 worker（poll → execute → report）
│
├── frontend/                 # React 前端（新）
│   └── src/
│       ├── pages/            # 4 个页面
│       ├── components/       # 复用组件
│       ├── api/              # API 客户端
│       └── types/            # TypeScript 类型定义
│
├── packages/
│   ├── domain_core/          # 领域模型 + 状态机 + worker 协议
│   ├── file_store/           # 文件系统轻持久化
│   ├── pipeline_services/    # 业务能力（legacy bridge）
│   ├── provider_config/      # Provider 配置管理
│   └── runtime_adapters/     # 平台适配（Mac / Windows）
│
├── config/
│   ├── defaults.yaml
│   └── profiles/             # mac-local.yaml / windows-prod.yaml
│
├── tests/                    # 76 个测试（pytest）
│
├── main_controller.py        # 旧核心（通过 LegacyBridge 过渡引用）
├── kimi_two_stage_script.py  # 旧脚本生成器
└── llm_libraries/            # LLM 能力库（script/packaging/correction）
```

## 可用命令

```bash
# 测试
uv run pytest tests/ -q                # 全量 76 测试

# 构建前端（生产）
cd frontend && npm run build

# 旧工具（仍可用）
uv run --project . kimi_two_stage_script.py 羊肚菌 --mock
```

## 项目状态

| 阶段 | 状态 |
|------|------|
| Phase 1（架构骨架） | 已完成 |
| Phase 2（Provider 配置 + 前端改造） | 已完成 |
| Phase 2.5（前端视觉适配 mockup 方案 A） | 已完成 |
| Phase 3（智能素材库 + AI 标注） | 规划中 |

当前 `feature/frontend-redesign` 分支包含完整的前端 React 改造 + 视觉适配，等待合并到 main。

## 前端视觉设计

采用方案 A（左侧步骤条 + 右侧详情），核心色板：

| 角色 | 颜色 | 用途 |
|------|------|------|
| 蓝 | `#0969da` | 完成态步骤、进行中步骤、操作按钮 |
| 黄 | `#e8b931` | 审核高亮步骤 |
| 红 | `#d1242f` | 创建按钮、失败状态、打回操作 |
| 绿 | `#1a7f37` | 已完成状态、质检通过 |
| 灰 | `#59636e` / `#eff2f5` / `#393f46` | 背景、边框、待执行步骤 |
