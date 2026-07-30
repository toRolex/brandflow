# CONTEXT.md — Brandflow 短视频自动化系统 3.0 领域词汇表

本文件是项目领域的权威词汇表。所有代码、文档、PR 描述中的术语应与此处定义一致。

## 核心概念

### Instance（实例）
一次独立的 toB 部署。每个客户拥有独立的系统实例（独立进程、独立素材库、独立配置），实例之间不共享数据。

### Job（任务）
一次短视频生产任务的完整生命周期。每个 Job 从 `queued` 开始，经过状态机的各个 Phase，最终到达 `completed` 或异常终态。Job 是控制面通过 AutoTickScheduler 调度的最小单元。

### Phase（阶段）
Job 生命周期中的一个离散步骤。系统根据脚本来源模式使用不同的状态机；Import 模式与 Generate 模式共享同一套 phase vocabulary，但跳过的阶段不同。

### Review Gate（审核门）
状态机中的人工审核检查点。Import 模式主要使用 `asset_review` 与 `final_review`；Generate 模式还包括 `script_review` 与 `tts_review`。

### WorkspaceLayout（工作区布局）
`packages/file_store/layout.py` 中的 project-tree 路径 seam。它以显式的语义方法解析 `workspace/projects/<project_id>/` 下的控制面、运行时、审核、报告、日志、音频和素材路径；其它生产模块不得重新拼接这些布局片段。全局 `shared_assets` 与 `music_library` 不属于此 seam。

### InvalidWorkspacePath（无效工作区路径）
`WorkspaceLayout` 抛出的 `ValueError` 子类。当标识符或相对路径为空、为绝对路径、包含路径分隔符或包含 `..` 逃逸片段时使用。所有布局级输入校验共享此异常类型。

### AmbiguousJobError（任务 ID 歧义）
布局级异常。当同一个 `job_id` 在多个 Project 中同时存在时由 `FileStoreRepository.find_project_for_job()` 抛出。路由层将其映射为 HTTP 409，并返回 `AMBIGUOUS_JOB_ID` 错误码。

### Pin / 置顶
Project 与 Job 共有的置顶标记。`JobRecord` 携带 `is_pinned: bool` 与 `pinned_at: str`（ISO 时间戳）；Project 通过 `project_meta.json` 持久化同名字段。置顶条目始终排列在列表首位（最近置顶优先），`display_index` 在置顶/取消置顶时保持不变。API 端点：`POST /api/projects/{id}/pin` 与 `POST /api/jobs/{id}/pin` toggle 状态。

## 配置体系

### ConfigReader
唯一非 secret 配置读取器，读取 `config/app_config.json` 并合并 catalog/业务默认配置及 product 级覆盖。旧 TTS model-only 配置会一次性补齐一致的 provider。
系统配置页的 AI Provider 与运行参数表单均由 catalog 描述；当前运行参数包括 Embedding、媒体工具、素材分类建议和场景导入。

### ProductStore
product 级配置的 CRUD 存储，与 `ConfigReader` 协同持久化并刷新配置缓存。

### SecretStore
Secret 解析器。API key 只从环境变量读取；endpoint 环境变量仅作为旧配置缺省时的兼容回退，不覆盖 `app_config.json`。

### Provider（服务提供者）
AI 能力的供应商。LLM、TTS 与 Vision provider 各自拥有独立的模型和凭据配置；provider 是运行时路由字段，model 必须属于该 provider。

### TTSConfig（TTS 配置数据模型）
`packages/provider_config/tts_config.py` 中的 `TTSConfig` dataclass 是 TTS 配置的单一数据模型，同时服务于配置持久化（`TTSConfigManager`）与运行时合成（`tts_provider.create_tts_provider()`）。#386 已将 TTSConfigShim 移除，Provider 连接参数（speed、vol、pitch、emotion、group_id、endpoint 等）已扁平合并入 TTSConfig 自身。

### TTS 配置入口（#386）
所有 TTS 配置统一到 `/tts-config` 页面单一入口。系统配置页 `/config` 不再包含 TTS 标签；`PUT /api/tts/config` 是 TTS 配置的唯一写 API。旧 `provider_profiles.tts` 在 ConfigReader 首次加载时自动迁移至 `tts` 根节。preset voice 列表定义在 `catalog.json` 各 provider 的 `preset_voices` 字段中，不再硬编码于路由文件。

## 架构状态（v0.7.31）

WorkspaceLayout seam 已接入 FileStoreRepository、控制面路由、Auto-Tick 与 pipeline phase handlers。所有 project-tree 路径通过布局的显式方法解析；`shared_assets`、`music_library` 等全局库保持各自的路径所有权。

### TTS 音频兼容

- Qwen TTS 返回的 WAV 使用流式 RIFF/data 长度哨兵；预览校验会在临时副本中按实际载荷长度解析，不修改返回的原始音频。

### WorkspaceLayout seam 收口

- `FileStoreRepository` 不再持有 `root` 属性；项目树路径一律通过 `repo.layout` 的显式方法访问。
- `FileStoreRepository.find_project_for_job(job_id)` 在多个 Project 同时持有同一 `job_id` 时抛 `AmbiguousJobError`，路由层在 `jobs/` 与 `reviews/` 子模块统一通过 `_resolve_job_project(repo, job_id)` 调用，返回 404 / 409。

### 路由与 phase handler 拆分

- `apps/control_plane/routes/jobs/` 按 Job 用例拆分为 CRUD、TTS、导出、内容、metadata 和 migration 子路由。
- `packages/pipeline_services/phases/` 为每个 phase 提供独立 handler；`PhaseContext` 携带 `WorkspaceLayout`。

## 常用命令

```bash
uv run pytest tests/ -q
npm run typecheck
npm run test
```
