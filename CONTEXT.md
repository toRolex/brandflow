# CONTEXT.md — Brandflow 短视频自动化系统 3.0 领域词汇表

本文件是项目领域的权威词汇表。所有代码、文档、PR 描述中的术语应与此处定义一致。

## 核心概念

### Instance（实例）
一次独立的 toB 部署。每个客户拥有独立的系统实例（独立进程、独立素材库、独立配置），实例之间不共享数据。零食公司部署和滋元堂部署是不同的 Instance。

### Job（任务）
一次短视频生产任务的完整生命周期。每个 Job 从 `queued` 开始，经过状态机的各个 Phase，最终到达 `completed` 或异常终态。Job 是控制面调度和 Worker 执行的最小单元。

### Phase（阶段）
Job 生命周期中的一个离散步骤。系统根据脚本来源模式使用不同的状态机：

**Import 模式状态机**（预写脚本导入）：
```
queued → scene_assembling ──────────────────────┐
       → tts_generating → subtitle_generating ──┤
                                                 ↓
                            montage_assembling ←─┘
                                                 ↓
                            video_rendering
                                                 ↓
                            final_review → completed
```
- `scene_assembling` 和 `tts_generating` 并行：场景拼接只操作视频文件，TTS 只处理配音，互不依赖
- `montage_assembling` 依赖 TTS 完成（脚本正文决定素材分类匹配，TTS 音频时长决定每个素材展示时长）
- `subtitle_generating` 依赖 TTS 完成（需要音频做时间对齐）

**Generate 模式状态机**（LLM 生成，保留旧流程）：
```
queued → script_generating → script_review → tts_generating → tts_review
       → subtitle_generating → asset_retrieving → asset_review
       → video_rendering → final_review → completed
```

### Review Gate（审核门）
状态机中的人工审核检查点。审核门的行为取决于脚本来源模式：

- **Import 模式（预写脚本导入）** — 精简为 `asset_review`（素材匹配质量确认）和 `final_review`（最终视频验收）两个门。`script_review` 和 `tts_review` 自动跳过，因为脚本内容由客户团队自行把控。
- **Generate 模式（LLM 生成）** — 保留完整四门：`script_review`、`tts_review`、`asset_review`、`final_review`，LLM 输出需要人工验证。

`auto_approve=True` 时所有审核门自动通过，实现全自动生产。

### Script（脚本）
一条口播文案，对应一个待生产的短视频。脚本有两种来源，由 Job 的 `mode` 字段显式控制：

- **Import 模式（`mode="import"`）** — 通过 `BatchJobItem.manual_script` 字段直接传入预写文案。系统跳过 LLM 生成，直接进入 TTS、字幕和视频生产。
- **Generate 模式（`mode="generate"`）** — 系统通过 LLM 两段式生成脚本。保留旧系统的质检能力。`manual_script` 为空时自动使用此模式。

### Asset（素材）
已索引的视频片段。原始视频经 ffmpeg 场景切片、Vision 模型分类后，按产品和 Category 归档到 SQLite 索引。素材在 `asset_retrieving` 阶段被检索并匹配到脚本句子。

### Category（素材分类）
素材片段的语义分类，由 Instance 级配置定义（而非硬编码枚举）。每个 Instance 拥有自己的分类体系。分类有两种建立方式：
- **运营手动配置** — 部署时在配置中定义分类名和对应的 Vision prompt，AI 按此规则自动标注素材
- **AI 自动建议** — 系统扫描素材库全部视频后，自动归纳出一套分类体系，运营人员审核确认后启用

分类由 Vision 模型（帧分类）和 LLM（文本匹配）协作完成。脚本通过文本语义自动匹配对应分类检索素材。

### Scene Asset（场景素材）
用于 Scene Segment 的独立视频文件，不经过素材库切片和分类流程。运营人员通过 Web 界面上传到 Instance 配置的场景文件夹，系统在 Scene Segment 阶段从各文件夹随机选取。Scene Asset 保持原始完整时长，不裁剪。

### Production Mode（生产模式）
一个 Job 包含两种串联的视频生产阶段，最终合成一个完整视频：

**Scene Segment（场景段）** — 视频前半部分，纯视频拼接，无需配音和字幕。从 Instance 级配置的 N 个素材文件夹中各随机选取一个 Scene Asset，按文件夹顺序拼接。片段之间使用 crossfade 转场（默认 0.5s），转场类型和时长由 Instance 配置决定。Scene Asset 不裁剪，保持原始时长。

**Montage Segment（混剪段）** — 视频后半部分，需要配音、字幕和素材检索。沿用旧系统句子级匹配逻辑：脚本按句拆分，每句匹配一个 Category，从对应分类中检索素材片段。素材展示时长由 TTS 对应的句子时长决定。唯一的改动是将 Category 数据源从硬编码枚举切换为 Instance 配置的分类体系。

Scene Segment 和 Montage Segment 的 TTS/字幕阶段可并行执行，最终在 `video_rendering` 阶段合成。

### Export Bundle（导出包）
一个 Job 完成后产出的完整产物集合，供二次剪辑使用：

- **最终视频** — 合成的完整 MP4
- **原始素材** — 所有被选中的源视频片段（场景段 + 混剪段），未经裁剪和转场处理
- **独立音轨** — TTS 生成的配音音频（WAV），未与视频合成
- **字幕文件** — SRT 格式字幕，未烧录到视频
- **时间线描述** — JSON 格式的剪辑决策文件，记录每段素材的入出点、转场类型、音频对齐信息

产物打包为 ZIP，目录结构清晰，可直接导入 DaVinci Resolve / Premiere Pro 进行二次精剪。

### Control Plane（控制面）
FastAPI Web 应用，负责任务调度、状态管理、审核流程、前端看板。是 Job 状态的唯一写入者。入口：`apps/control_plane/`。

### Runtime Worker（执行器）
拉模式 Worker，通过轮询 `POST /workers/poll` 获取任务，执行后上报结果。通过 lease + attempt 机制与控制面协调。入口：`apps/runtime_worker/`。

### Auto-Tick（自动推进）
开发模式下的后台循环（默认 3 秒间隔），自动推进 Job 的 Phase 并执行对应副作用。通过 `DEV_AUTO_TICK=1` 启用，生产环境应关闭。

## 配置体系

### AppConfigManager
配置的唯一真相来源。读取 `config/app_config.json`（业务配置）并合并 `DEFAULTS`，通过环境变量读取 API Key 和 Endpoint。**下一版本起也负责加载 `.env` 文件。**

### Provider（服务提供者）
AI 能力的供应商。LLM 支持 deepseek/kimi/openai；TTS 仅使用 mimo（minimax 代码已废弃）；Vision 支持 xiaomi/openai/claude。每个 Provider 有独立的环境变量命名规则。

### Legacy Bridge（遗留桥接层）
包装旧核心文件（`main_controller.py`、`kimi_two_stage_script.py`）的适配器。包括 `LegacyScriptBridge`、`LegacyMediaBridge`、`LegacyScheduleBridge`。**下一版本将随旧核心文件一起删除。**

## 架构状态（v0.3.x → v0.4.0 迁移中）

### 已确认废弃的能力
- `_phase_to_artifacts()`（`app.py`） — 285 行单体函数，已由 `PhaseOrchestrator` 替代并删除
- `_DefaultMediaBridge`（`loop.py`） — Worker 的 media 适配器包装层，已由 `PhaseOrchestrator` 替代并删除
- `main_controller.py` — 3600 行单体控制器，全部能力将迁移至独立 service
- `kimi_two_stage_script.py` — 旧脚本生成器，将被 `ScriptGenerator` 替代
- `LegacyScriptBridge` / `LegacyMediaBridge` / `LegacyScheduleBridge` — 随旧文件一起删除
- `ScheduleWriter`（xlsx） — 被 `ScheduleStore`（SQLite）替代
- `HeartbeatStore` — 新系统 Worker 协议有独立心跳机制
- `TaskState` 枚举 — 被 `domain_core.models.Phase` 替代

### 新增的 service
- `PhaseOrchestrator`（`packages/pipeline_services/phase_orchestrator.py`） — 单阶段执行编排器。通过策略 map 路由到 8 个 handler（script / tts / tts_review / subtitle / asset / video / final_rendering / final_review），构造函数注入依赖（script_bridge, subtitle_svc, video_svc, tts_provider, schedule_store）。`_auto_tick` 和 `WorkerLoop` 均通过 `run_phase(phase, ctx)` 调用。替代已删除的 `_phase_to_artifacts` 和 `_DefaultMediaBridge`。
- `LLMClient`（`packages/pipeline_services/llm_client.py`） — 通用 LLM HTTP 客户端
- `ScriptGenerator`（`packages/pipeline_services/script_service/`） — 脚本生成 service
- `MiMoTTSProvider`（扩展，`packages/pipeline_services/tts_provider.py`） — MiMo TTS 完整 service（HTTP + 响应 + 重试），minimax 不再使用
- `SubtitleService`（`packages/pipeline_services/`） — SRT 字幕生成
- `VideoService`（`packages/pipeline_services/`） — 视频组装与烧录
