# CONTEXT.md — Brandflow 短视频自动化系统 3.0 领域词汇表

本文件是项目领域的权威词汇表。所有代码、文档、PR 描述中的术语应与此处定义一致。

## 核心概念

### Instance（实例）
一次独立的 toB 部署。每个客户拥有独立的系统实例（独立进程、独立素材库、独立配置），实例之间不共享数据。

### Job（任务）
一次短视频生产任务的完整生命周期。每个 Job 从 `queued` 开始，经过状态机的各个 Phase，最终到达 `completed` 或异常终态。Job 是控制面调度和 Worker 执行的最小单元。

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

## 配置体系

### ConfigReader
纯配置读取器，读取 `config/app_config.json` 并合并默认配置及 product 级覆盖。

### ProductStore
product 级配置的 CRUD 存储，与 `ConfigReader` 协同持久化并刷新配置缓存。

### SecretStore
环境变量 API key 与 endpoint 解析器，不依赖配置文件。

### Provider（服务提供者）
AI 能力的供应商。LLM、TTS 与 Vision provider 各自拥有独立的模型和凭据配置。

## 架构状态（v0.7.30）

WorkspaceLayout seam 已接入 FileStoreRepository、控制面路由、Auto-Tick、pipeline phase handlers 与 Runtime Worker。所有 project-tree 路径通过布局的显式方法解析；`shared_assets`、`music_library` 等全局库保持各自的路径所有权。

### WorkspaceLayout seam 收口

- `FileStoreRepository` 不再持有 `root` 属性；项目树路径一律通过 `repo.layout` 的显式方法访问。
- `FileStoreRepository.find_project_for_job(job_id)` 在多个 Project 同时持有同一 `job_id` 时抛 `AmbiguousJobError`，路由层在 `jobs/` 与 `reviews/` 子模块统一通过 `_resolve_job_project(repo, job_id)` 调用，返回 404 / 409。

### 路由与 phase handler 拆分

- `apps/control_plane/routes/jobs/` 按 Job 用例拆分为 CRUD、TTS、导出、内容、metadata 和 migration 子路由。
- `packages/pipeline_services/phases/` 为每个 phase 提供独立 handler；`PhaseContext` 携带 `WorkspaceLayout`。
- `apps/runtime_worker/loop.py` 独立持有 `WorkspaceLayout`，不依赖控制面 repository 状态。

## 常用命令

```bash
uv run pytest tests/ -q
npm run typecheck
npm run test
```
