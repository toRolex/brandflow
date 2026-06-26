# CONTEXT.md — 滋元堂矩阵流水线 3.0 领域词汇表

本文件是项目领域的权威词汇表。所有代码、文档、PR 描述中的术语应与此处定义一致。

## 核心概念

### Job（任务）
一次短视频生产任务的完整生命周期。每个 Job 从 `queued` 开始，经过状态机的各个 Phase，最终到达 `completed` 或异常终态。Job 是控制面调度和 Worker 执行的最小单元。

### Phase（阶段）
Job 生命周期中的一个离散步骤。合法 Phase 值由 `domain_core.models.Phase` 定义，顺序由 `domain_core.state.PHASE_ORDER` 决定。Phase 只能通过 `next_phase()` 前进或 `rewind_from_phase()` 回退，不存在跳跃。

### Review Gate（审核门）
状态机中的 4 个人工审核检查点：`script_review`、`tts_review`、`asset_review`、`final_review`。Job 在审核门处暂停，等待审核员批准（approve）、驳回（reject）或覆盖（override）。`auto_approve=True` 时自动通过。

### Script（脚本）
用于短视频口播的文案文本。由 LLM 两段式生成（前半段 4 句 + 后半段 4 句），必须满足质检硬条件：150-200 字、品名出现 1 次、品牌"滋元堂"出现 1 次、包含"充分烹熟"、无 emoji、无医疗功效词。

### Asset（素材）
已索引的视频片段。原始视频经 ffmpeg 场景切片、Vision 模型分类后，按产品和 Category 归档到 SQLite 索引。素材在 `asset_retrieving` 阶段被检索并匹配到脚本句子。

### Category（素材分类）
素材片段的语义分类，由 `asset_library.models.Category` 枚举定义。包括：产地溯源、烹饪翻炒、产品特写等 10 个类别。分类由 Vision 模型（帧分类）和 LLM（句子分类）共同完成。

### Product（产品）
被推广的商品实体（如"羊肚菌""见手青"）。是 Job 的必填字段，贯穿脚本生成（品名校验）、素材检索（按产品筛选）、排期记录的全流程。

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
- `PhaseOrchestrator`（`packages/pipeline_services/phase_orchestrator.py`） — 单阶段执行编排器。通过策略 map 路由到 7 个 handler（script / tts / tts_review / subtitle / asset / video / final），构造函数注入依赖（script_bridge, subtitle_svc, video_svc, tts_provider, schedule_store）。`_auto_tick` 和 `WorkerLoop` 均通过 `run_phase(phase, ctx)` 调用。替代已删除的 `_phase_to_artifacts` 和 `_DefaultMediaBridge`。
- `LLMClient`（`packages/pipeline_services/llm_client.py`） — 通用 LLM HTTP 客户端
- `ScriptGenerator`（`packages/pipeline_services/script_service/`） — 脚本生成 service
- `MiMoTTSProvider`（扩展，`packages/pipeline_services/tts_provider.py`） — MiMo TTS 完整 service（HTTP + 响应 + 重试），minimax 不再使用
- `SubtitleService`（`packages/pipeline_services/`） — SRT 字幕生成
- `VideoService`（`packages/pipeline_services/`） — 视频组装与烧录
