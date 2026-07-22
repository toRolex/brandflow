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
       → tts_generating → subtitle_generating ──┤（subtitle_generating 可跳过）
                                                 ↓
                            montage_assembling ←─┘
                                                 ↓
                            asset_retrieving → asset_review
                                                 ↓
                            video_rendering → final_rendering → final_review → completed
```
- `scene_assembling` 和 `tts_generating` 并行：场景拼接只操作视频文件，TTS 只处理配音，互不依赖
- `montage_assembling` 依赖 TTS 完成（脚本正文决定素材分类匹配，TTS 音频时长决定每个素材展示时长）
- `subtitle_generating` 依赖 TTS 完成（需要音频做时间对齐），可通过 `skip_subtitle=True` 跳过

**Generate 模式状态机**（LLM 生成，保留旧流程）：
```
queued → script_generating → script_review → tts_generating → tts_review
       → subtitle_generating → asset_retrieving → asset_review
       → video_rendering → final_rendering → final_review → completed
```

### Review Gate（审核门）
状态机中的人工审核检查点。审核门的行为取决于脚本来源模式：

- **Import 模式（预写脚本导入）** — 精简为 `asset_review`（素材匹配质量确认）和 `final_review`（最终视频验收）两个门。`script_review` 和 `tts_review` 自动跳过，因为脚本内容由客户团队自行把控。
- **Generate 模式（LLM 生成）** — 保留完整四门：`script_review`、`tts_review`、`asset_review`、`final_review`，LLM 输出需要人工验证。

`auto_approve=True` 时所有审核门自动通过，实现全自动生产。

### Execution State（执行状态）
JobRecord 的 `execution` 字段（`PhaseExecutionState`），对外暴露当前 phase 执行的生命周期：`pending / running / retrying / failed / succeeded`，附带 attempt 计数（`current_attempt` / `max_attempts`，默认最多 3 次 attempt）与结构化错误 `ExecutionFailure`（`code` / `message` / `retryable`）。不变量：`failed` 必须携带 error；`retrying` 可携带导致重试的 retryable error（便于 Tick 无需解析字符串即可应用重试策略）；其余状态不携带 error。Job API 响应通过 `execution` 字段原样返回。结构化 phase 结果模型（`PhaseExecutionSuccess` / `PhaseExecutionFailure` 判别联合）与旧 handler 兼容适配器定义于 `packages/domain_core/phase_execution.py`。

### Phase Retry（阶段重试）
Import 模式媒体 phase 通过结构化执行结果驱动重试：retryable 失败自动重试至耗尽 `max_attempts`（默认 3 次 attempt），确定性失败立即终态。终态失败记录 `failed_phase`，`POST /api/jobs/{id}/retry` 先用同一校验契约（`validate_phase_input`）revalidate 输入，通过则从失败阶段恢复并保留已有 artifacts（不重跑有效上游产物，如 tts_audio）；校验失败返回 409 + 结构化 detail，前端原样展示。存量失败 job（无 `failed_phase`）保留旧的重置为 `queued` 重试行为。

### Script（脚本）
一条口播文案，对应一个待生产的短视频。脚本有两种来源，由 Job 的 `mode` 字段显式控制：

- **Import 模式（`mode="import"`）** — 通过 `BatchJobItem.manual_script` 字段直接传入预写文案。系统跳过 LLM 生成，直接进入 TTS、字幕和视频生产。
- **Generate 模式（`mode="generate"`）** — 默认由 LLM 两段式生成脚本；当 `manual_script` 非空时，直接使用该文案并跳过 LLM 生成，继续走 TTS、字幕和智能素材检索的完整流水线。保留旧系统的质检能力。`manual_script` 为空时自动使用 LLM 生成。

### Asset（素材）
已索引的视频片段。原始视频经 ffmpeg 场景切片、Vision 模型分类后，按产品和 Category 归档到 SQLite 索引。素材在 `asset_retrieving` 阶段被检索并匹配到脚本句子。

SmartAssetLibrary 前端页面支持全选当前筛选结果、取消全选和清空选择，已选数量实时显示。批量操作（启用/禁用/编辑/删除）作用于当前已选素材 ID。ProjectList 前端页面同样支持复选框多选、表头全选/半选、批量删除与部分失败汇总。

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

Montage 拼接使用 ``MediaCompositor.concat_two``，会将 scene segment 和 base video 统一归一化到 720×1280 再拼接，输出始终符合管道目标规格，不受输入分辨率影响（单个源文件复制时不做归一化）。

Scene Segment 和 Montage Segment 的 TTS/字幕阶段可并行执行，最终在 `video_rendering` 阶段合成。

**音画对齐（issue #179）** — Scene Segment 占视频前半 `[0, scene_ms)`，无 TTS/字幕（允许背景音乐）；TTS 配音与字幕整体偏移 `scene_ms` 到 Montage Segment 起点。`video_rendering` 在拼接 `base.mp4` 后产出 `audio_aligned.mp3`（`adelay`+`apad` 对齐到 base 全长）、`subtitles_offset.srt`（时间戳整体偏移）与 `final_timeline.json`；`final_rendering` 优先消费这些对齐产物。对齐失败时回退原始音频并在时间线标记 `aligned: false`。

**Final Timeline（权威时间线）** — 渲染时由 `final_timeline.build_final_timeline` 从实际渲染输入（scene 实测时长 + 复用 `build_base_video` 的 trim 参数）生成并持久化为 `final_timeline.json`，禁止目录推算。每段记录 `kind`（scene/montage/blank）、精确 `start_ms`/`end_ms`、`sentence_index`、`text` 与来源追溯（`asset_id`/`file_path`），分段连续不重叠（交叉淡化完整归后段）。携带稳定内容指纹（hash 渲染输入内容与文件名，不含绝对路径与输出字节），对齐失败重渲染同输入产生相同时间线。

### Export Bundle（导出包）
一个 Job 完成后产出的完整产物集合，供二次剪辑使用：

- **最终视频** — 合成的完整 MP4，外加按 Final Timeline 精确切分的 `final/seg_NNN.mp4` 分块（每段对应一个 timeline segment，重编码保证精确边界，issue #181）
- **原始素材** — 所有被选中的源视频片段（场景段 + 混剪段），未经裁剪和转场处理
- **独立音轨** — TTS 生成的配音音频（WAV），未与视频合成
- **字幕文件** — SRT 格式字幕，未烧录到视频
- **时间线描述** — JSON 格式的剪辑决策文件。由权威 `final_timeline.json`（渲染时生成，见上）投影为平坦播放顺序的 timeline 2.0（`version: "2.0"`，每段含 `rendered_file` → `final/seg_NNN.mp4`，montage 段另含可选 `source_file` 源素材名）。无 Final Timeline 的 legacy Job 拒绝导出，要求重渲染（不再回退 legacy 推算）。

产物打包为 ZIP，目录结构清晰，可直接导入 DaVinci Resolve / Premiere Pro 进行二次精剪。

**后台 Export Task（Issue #180）** — 导出从同步下载改为持久化后台任务。`POST /api/jobs/{id}/export` 返回任务标识（202，非阻塞），由 `app.state.export_executor` 后台构建；`GET .../export/status` 暴露 `queued/running/failed/ready/stale` 与进度；`GET .../export/download` 仅 ready 时提供 ZIP。任务以 Final Timeline 指纹为键缓存复用；重渲染（重写 `final_timeline.json`）自动使旧任务 stale 并清理旧包；重启后中断任务重新排队，完整校验产物被复用，损坏输出先删再重建。ZIP 全部文件校验后原子发布（staging 目录 + rename），失败不留半成品。无 Final Timeline 的 legacy Job 返回 409 rerender-required。实现：`packages/pipeline_services/export_task.py`（ExportTaskService），路由 `apps/control_plane/routes/api_jobs.py`。`EXPORT_SYNC=1` 时同步执行（测试/单进程开发）。

### Control Plane（控制面）
FastAPI Web 应用，负责任务调度、状态管理、审核流程、前端看板。是 Job 状态的唯一写入者。入口：`apps/control_plane/`。

### Runtime Worker（执行器）
拉模式 Worker，通过轮询 `POST /workers/poll` 获取任务，执行后上报结果。通过 lease + attempt 机制与控制面协调。入口：`apps/runtime_worker/`。

### Auto-Tick（自动推进）
开发模式下的后台循环（默认 3 秒间隔），自动推进 Job 的 Phase 并执行对应副作用。通过 `DEV_AUTO_TICK=1` 启用，生产环境应关闭。

## 配置体系

### ConfigReader
纯配置读取器，带构建期热缓存。读取 `config/app_config.json`，合并 `packages/provider_config/config_constants.py` 中的 `DEFAULTS`，并按 product 应用覆盖。所有 `get_*()` 方法在构建后均为 O(1) 字典查找。路径：`packages/provider_config/config_reader.py`。内部包含 `ProductStore`（product 级 CRUD 存储）和 `ConfigResolver`（面向 phase handler 的配置查询）。

### ConfigResolver
面向 pipeline phase handler 的高层配置查询接口。封装 `ConfigReader` + `SecretStore`，提供 `tts()`、`llm()`、`categories()` 方法。位于 `config_reader.py`。

### ProductStore
product 级配置的 CRUD 存储。与 `ConfigReader` 协同，所有写入通过 `config_io.save_config()` 持久化，并调用 `ConfigReader.reload()` 刷新热缓存。支持 product 创建、切换、重命名、删除，以及 product 级配置覆盖写入。位于 `config_reader.py`。

### SecretStore
纯环境变量解析器，负责 API key 与 endpoint 解析，不依赖配置文件。支持 provider 专用环境变量与类别级回退（`LLM_API_KEY` / `TTS_API_KEY` / `VISION_API_KEY` 等）。路径：`packages/provider_config/secret_store.py`。

### DEFAULTS
默认配置常量，位于 `packages/provider_config/config_constants.py`。包含 `llm`、`tts`、`vision`、`media`、`video`、`asset_library`、`scene`、`product` 的出厂默认值，被 `ConfigReader` 作为合并基线。

### Provider（服务提供者）
AI 能力的供应商。LLM 支持 deepseek（默认 `deepseek-v4-pro`）/ kimi / openai；TTS 同时支持 qwen 与 mimo，用户通过 TTS 配置页选择模型即完成 provider 切换（模型 ID 前缀决定 provider），出厂默认为 qwen（`qwen3-tts-flash` / 音色 `Cherry`，minimax 代码已废弃）；Vision 支持 xiaomi（默认 `mimo-v2.5`）/ claude。每个 Provider 有独立的环境变量命名规则。

TTS 默认配置的唯一权威来源是 `config_constants.DEFAULTS["tts"]`——TTS 配置页与流水线 `tts_generating` 阶段共用该基线，页面所见即流水线所用。TTS 配置按 product 作用域绑定（每个 product 可有独立音色）：配置页编辑当前激活 product 的配置，Job 运行时使用其创建时记录的 product 配置，二者在界面上均显式标注所属 product 以避免歧义。

## 架构状态（v0.7.16）

v0.7.16 已完成控制面 + 执行器 + pipeline service 的分层重构，配置体系由 `ConfigReader` / `ProductStore` / `SecretStore` / `DEFAULTS` 接管，`PhaseOrchestrator` 统一调度 10 个 phase handler。

### 路由与 phase handler 拆分（近期重构）

近期提交对控制面路由、前端 API/type 以及 `PhaseOrchestrator` 做了按领域拆分，当前结构如下：

- **`apps/control_plane/routes/jobs/`** — Job 相关 handler 按用例拆分为 `crud.py`（创建/查询/暂停/删除/重命名）、`tts.py`（TTS 预览/音色更新）、`export.py`（导出任务）、`content.py`（脚本/封面内容）、`metadata.py`、`migration.py`、`cover_title.py`。共享的创建校验、响应构造与 TTS 解析逻辑放在 `helpers.py` / `models.py`。`api_jobs.py` 仅作为 `APIRouter` 聚合层，按顺序 `include_router` 上述子路由；为避免动态路径遮蔽，更具体的 job-level 子路径先于 `/jobs/{job_id}` 注册。
- **`apps/control_plane/routes/assets/`** — Asset 相关 handler 按用例拆分为 `query.py`、`index.py`、`reclassify.py`、`thumbnails.py`、`status.py`、`source.py`、`categories.py`、`fields.py`、`delete.py`、`migrate.py`。`api_assets.py` 仅作为 `APIRouter` 聚合层 include 上述子路由。
- **`packages/pipeline_services/phases/`** — 10 个 phase handler 的实现从单体 `phase_orchestrator.py` 迁出，每个 phase 对应独立模块（`script.py`、`tts.py`、`subtitle.py`、`asset.py`、`video_rendering.py`、`final_rendering.py`、`final_review.py`、`scene_assembly.py`、`montage_assembly.py`），公共依赖与上下文定义放在 `config.py` / `shared.py`。`PhaseOrchestrator` 仍通过 `_handlers` 策略表派发，控制面 `auto_tick` 与 `runtime_worker` 共用同一份策略表。
- **`frontend/src/api/` / `frontend/src/types/`** — 原 `client.ts` 与 `types/index.ts` 按领域拆分为 `jobs.ts`、`assets.ts`、`tts.ts`、`config.ts` 等模块；`JobPipeline.tsx` 拆分为 shell + phase panels。

**注意：** 当前 `routes/jobs/helpers.py` 与 `routes/assets/helpers.py` 仍承担多个领域的辅助职责（校验、序列化、导出、TTS 预览等），建议在后续迭代中继续按用例拆分；`PhaseOrchestrator` 与 phase handler 之间仍存在双向耦合（handler 通过 `config.py` 反向访问 orchestrator 私有配置），建议逐步改为通过显式 `PhaseContext` / 窄接口注入依赖。

### 已确认废弃的能力
- `AppConfigManager` — 已被 `ConfigReader` + `ProductStore` + `SecretStore` + `DEFAULTS` 替代（#246 已删除 `app_config.py`）
- `BaseRuntimeAdapter` / `MacLocalRuntimeAdapter` / `WindowsProdRuntimeAdapter` — 合并为单一 `RuntimeAdapter` 类（#246）
- `ConfigResolver` — 已移入 `config_reader.py` 作为内部类（#246）
- `_phase_to_artifacts()`（`app.py`） — 285 行单体函数，已由 `PhaseOrchestrator` 替代并删除
- `_DefaultMediaBridge`（`loop.py`） — Worker 的 media 适配器包装层，已由 `PhaseOrchestrator` 替代并删除
- `main_controller.py` — 3600 行单体控制器，全部能力已迁移至独立 service
- `kimi_two_stage_script.py` — 旧脚本生成器，已被 `ScriptGenerator` 替代
- `LegacyScriptBridge` / `LegacyMediaBridge` / `LegacyScheduleBridge` — 旧桥接层已删除或已收敛
- `ScheduleWriter`（xlsx） — 被 `ScheduleStore`（SQLite）替代
- `HeartbeatStore` — 新系统 Worker 协议有独立心跳机制
- `TaskState` 枚举 — 被 `domain_core.models.Phase` 替代
- Per-project 素材端点（`/{project_id}/assets/*`） — 全局 `/api/assets` 已替代，旧端点标记 DEPRECATED

### 核心 service
- `PhaseOrchestrator`（`packages/pipeline_services/phase_orchestrator.py`） — 单阶段执行编排器。通过策略 map 路由到 10 个 handler（`script_generating`、`tts_generating`、`tts_review`、`subtitle_generating`、`asset_retrieving`、`video_rendering`、`final_rendering`、`final_review`、`scene_assembling`、`montage_assembling`），构造函数注入依赖（`script_bridge`、`subtitle_svc`、`video_svc`、`schedule_store`、`config_reader`、`secret_store`）。`_auto_tick` 和 `WorkerLoop` 均通过 `run_phase(phase, ctx)` 调用。替代已删除的 `_phase_to_artifacts` 和 `_DefaultMediaBridge`。
- `ConfigReader`（`packages/provider_config/config_reader.py`） — 纯配置读取器，合并 `DEFAULTS`、root 配置与 product 级覆盖
- `ProductStore`（`packages/provider_config/product_store.py`） — product 级配置 CRUD
- `SecretStore`（`packages/provider_config/secret_store.py`） — 环境变量 API key / endpoint 解析
- `LLMClient`（`packages/pipeline_services/llm_client.py`） — 通用 LLM HTTP 客户端
- `ScriptGenerator`（`packages/pipeline_services/script_service/`） — 脚本生成 service
- `MiMoTTSProvider` / `QwenTTSProvider`（`packages/pipeline_services/tts_provider.py`） — TTS provider 动态选择（qwen 默认，mimo 兼容）
- `SubtitleService`（`packages/pipeline_services/subtitle_service.py`） — SRT 字幕生成
- `VideoService`（`packages/pipeline_services/video_service.py`） — 视频组装与烧录
- `final_timeline`（`packages/pipeline_services/final_timeline.py`） — 音画对齐与权威 Final Timeline 生成（`shift_srt`/`align_audio`/`compute_scene_offset_ms`/`build_final_timeline`，issue #179）
- `segment_export`（`packages/pipeline_services/segment_export.py`） — 精确 MP4 分块（`segment_final_video` 重编码切分 `seg_NNN.mp4`）与 timeline.json 2.0 投影（`build_timeline_2`，issue #181）
- `ScheduleStore`（`apps/control_plane/services/schedule_store.py`） — SQLite 排期存储
- `KnowledgeStore`（`packages/knowledge_store/`） — 知识库文档解析与卖点管理
- `AssetRepository` / `AssetRetriever`（`packages/pipeline_services/asset_library/`） — 素材库索引与检索

### 近期主要功能
- #28 知识库
- #33 脚本模板
- #56 Import subtitle 跳过修复
- #57 / #59 product 级配置覆盖
- #58 asset product 参数
- #62 前端通用化
- #63 Category 字符串化
- #64 默认值通用化
- #65 分类回退移除
- #66 keyword_map 配置化
- #67 mock 模板通用化
- #76 部署体检
- #99 仓库清理
- per-project 素材端点废弃，迁移至全局 `/api/assets`
- ProductConfigForm 新增 AI 分类建议 + vision_prompt
- `tests/regression/` — 回归测试目录，当前包含 project delete 一致性校验
- `packaging/windows/start_worker.ps1` / `manage-task.ps1` — Windows worker 启动与计划任务管理脚本


