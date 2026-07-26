# API 参考

## Jobs

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects/{project_id}/jobs` | POST | 创建单个 Job；上传音频的 Job 先创建为草稿 |
| `/api/projects/{project_id}/jobs/batch` | POST | 批量创建 Job；当前仅支持 TTS 音频 |
| `/api/jobs/{job_id}/enqueue` | POST | 校验并将草稿入队 |
| `/api/jobs/{job_id}` | GET | 获取 Job 详情 |
| `/api/jobs/{job_id}/pause` | POST | 登记暂停请求；当前 handler 在安全边界完成后暂停 |
| `/api/jobs/{job_id}/resume` | POST | 从已暂停的 phase 继续 Job |
| `/api/jobs/{job_id}/cancel` | POST | 幂等登记取消请求；保留 Job、日志与已产物 |
| `/api/jobs/{job_id}/retry` | POST | 仅重试 `failed` 且 `execution.error.retryable=true` 的失败 phase；否则返回 409 并说明修复前置条件 |
| `/api/jobs/{job_id}` | DELETE | 仅删除 draft、paused、failed、cancelled 或 completed Job |
| `/api/jobs/{job_id}/rename` | PUT | 重命名 Job |
| `/api/jobs/{job_id}/logs` | GET | 获取 Job 日志 |
| `/api/jobs/{job_id}/script` | POST | 重新生成脚本 |
| `/api/jobs/{job_id}/audio` | POST | 为上传音频草稿上传音频；入队后不允许替换 |
| `/api/jobs/{job_id}/export` | GET | 导出 Job 产物打包 |
| `/api/music` | GET | 获取音乐列表 |
| `/api/cover-title/generate` | POST | 生成封面标题；限流时返回 `429` 和 `Retry-After` |

新建单个与批量 Job 均使用 `review_strategy`：`review_each`（默认）或 `fast_output`。新建请求不得传入历史字段 `auto_approve`；服务端会以 422 拒绝该字段。`fast_output` 只自动通过脚本和 TTS 审核，素材与最终审核仍须人工确认。

## Projects

> **Breaking change (#354):** All list endpoints now return a paginated envelope
> `{"items": [...], "total": N, "page": P, "page_size": S}` instead of bare
> arrays. `GET /api/projects/{project_id}` no longer embeds the full `jobs`
> array — use `GET /api/projects/{project_id}/jobs` for paginated Job summaries.

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects` | GET | 分页列出项目；参数 `page`(≥1, 默认1) / `page_size`(1–200, 默认50)；按 project_id 升序 |
| `/api/projects` | POST | 创建项目 |
| `/api/projects/{project_id}` | GET | 获取项目详情（不内嵌 jobs） |
| `/api/projects/{project_id}` | DELETE | 删除项目 |
| `/api/projects/{project_id}/jobs` | GET | 分页列出该项目 Job 摘要；新 Job 按不可变 `created_at` 创建顺序，历史 Job 按 `job_id` 确定性兼容排序，不受状态保存影响 |
| `/api/projects/{project_id}/upload` | POST | 上传文件到项目 |
| `/api/projects/{project_id}/assets` | GET | 列出项目素材 |
| `/api/projects/{project_id}/assets/indexed` | GET | 列出已索引素材 |
| `/api/projects/{project_id}/assets/index` | POST | 触发素材索引 |

## Assets（全局素材库）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/assets/upload` | POST | 上传素材 |
| `/api/assets/list` | GET | 列出素材 |
| `/api/assets/indexed` | GET | 列出已索引素材 |
| `/api/assets/index` | POST | 触发索引任务 |
| `/api/assets/index/{task_id}/status` | GET | 索引任务状态 |
| `/api/assets/index/{task_id}/logs` | GET | 索引任务日志 |
| `/api/assets/batch` | PATCH | 批量更新素材 |
| `/api/assets/batch-fields` | PATCH | 批量更新素材字段 |
| `/api/assets/batch` | DELETE | 批量删除素材 |
| `/api/assets/migrate` | POST | 素材迁移 |
| `/api/assets/{asset_id}` | PATCH | 更新单个素材 |
| `/api/assets/{asset_id}/fields` | PATCH | 更新素材字段 |
| `/api/assets/{asset_id}` | DELETE | 删除素材 |
| `/api/assets/{asset_id}/thumbnail` | GET | 获取素材缩略图 |
| `/api/assets/categories/suggest` | POST | 分类建议（AI） |
| `/api/assets/categories` | GET | 获取分类配置 |

## TTS

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/tts/config` | GET | 获取 TTS 配置 |
| `/api/tts/config` | PUT | 更新 TTS 配置 |
| `/api/tts/voices` | GET | 获取可用音色列表 |
| `/api/tts/metrics` | GET | TTS 用量统计 |
| `/api/tts/logs` | GET | TTS 日志 |
| `/api/tts/errors/distribution` | GET | TTS 错误分布 |
| `/api/tts/preview` | POST | TTS 预览 |
| `/api/tts/voice-clone-sample` | POST | 上传音色克隆样本（mp3/wav，上限 10MB） |

## Reviews

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/reviews/{job_id}/approve` | POST | 审核通过 |
| `/api/reviews/{job_id}/reject` | POST | 审核拒绝 |
| `/api/reviews/{job_id}/edit-script` | POST | 编辑脚本 |
| `/api/reviews/{job_id}/regenerate-with-prompt` | POST | 带提示词重新生成 |
| `/api/reviews/{job_id}/reject-clip` | POST | 拒绝单个片段 |

## 已废弃的 Workers 协议

以下端点只为历史部署兼容而保留。当前生产流程不启动 `runtime_worker`，也不应在新集成中调用这些端点。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/workers/poll` | POST | Worker 轮询取任务 |
| `/workers/tasks/{task_id}/input-bundle` | GET | 获取任务输入包 |
| `/workers/tasks/{task_id}/heartbeat` | POST | 任务心跳 |
| `/workers/tasks/{task_id}/artifacts` | POST | 上传产物 |
| `/workers/tasks/{task_id}/report` | POST | 上报执行结果 |

## 运行日志

> **Breaking change (#354):** `GET /api/logs/dates` 现返回分页信封。
> 新增 DELETE 端点，遵循安全规则：当天日志始终受保护，日期格式须为真实日历日期，
> 删除操作与日志写入使用同一文件锁。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/logs/error` | POST | 接收前端错误上报，请求体字段见下表；成功返回 `201` 与 `{ "ok": true }` |
| `/api/logs/dates` | GET | 分页日志日期列表；参数 `page` / `page_size`；按日期降序；每条含 `date` / `size_bytes` / `error_count` |
| `/api/logs/download?date=YYYY-MM-DD` | GET | 下载指定日期的 `.jsonl` 日志；`404` 当文件不存在 |
| `/api/logs/{date}` | DELETE | 删除单日日志；`200 {date, deleted}`；当天返回 `400`，文件不存在幂等返回 `deleted=false` |
| `/api/logs/batch` | DELETE | 批量删除；请求体 `{dates: ["YYYY-MM-DD"]}` (1–200)；返回 `{deleted, not_found, protected}`；当天日期置入 `protected` 不阻止其他处理 |
| `/api/logs/cleanup?before_days=N` | DELETE | 清理 N 天前的日志 (N ≥ 1)；返回 `{deleted: [...], deleted_count}`；当天永远受保护 |

### 日志删除安全规则

- "今天"使用与日志 writer 相同的系统本地时区定义
- 当天日志在所有删除操作中均受保护：单删返回 `400`，批量放入 `protected`
- `before_days` 必须 ≥ 1，不接受 0 或负数
- 日期字符串须通过 `date.fromisoformat()` 真实日历校验
- 删除前获取 `_LOG_LOCK`，与 writer 互斥
- 仅作用于日志目录中 `YYYY-MM-DD.jsonl` 命名规则的普通文件

`POST /api/logs/error` 请求体字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | `"frontend"` 或 `"backend"` |
| `level` | string | 是 | `"error"` 或 `"warn"` |
| `message` | string | 是 | 错误摘要 |
| `timestamp` | string | 否 | ISO 8601 时间；缺省由服务端写入 |
| `status_code` | int | 否 | HTTP 状态码（后端请求时） |
| `method` | string | 否 | 请求方法（后端请求时） |
| `path` | string | 否 | 请求路径（后端请求时） |
| `stack_trace` | string | 否 | 异常堆栈 |
| `request_body` | any | 否 | POST 请求体（后端请求时） |
| `request_params` | object | 否 | 查询参数（后端请求时） |
| `extra` | object | 否 | 扩展字段 |

## Config

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 获取系统配置 |
| `/api/config` | PUT | 更新系统配置 |
| `/api/config/options` | GET | 获取配置可选项 |
| `/api/config/product` | GET | 获取产品列表 |
| `/api/config/product` | PUT | 更新产品 |
| `/api/config/product` | DELETE | 删除产品 |
| `/api/config/templates` | GET | 获取脚本模板列表 |
| `/api/config/templates/{template_id}` | GET | 获取模板详情 |
| `/api/config/templates` | POST | 创建模板 |
| `/api/config/templates/{template_id}` | PUT | 更新模板 |
| `/api/config/templates/{template_id}` | DELETE | 删除模板 |
| `/api/config/templates/{template_id}/preview` | POST | 预览模板 |

## 其他

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查；`?deploy_check=true` 返回部署体检 |
| `/api/products` | GET | 获取产品列表 |
| `/api/products` | POST | 创建产品 |
| `/api/products/{product_id}` | PATCH | 更新产品 |
| `/api/products/{product_id}` | DELETE | 删除产品 |
| `/api/products/{product_id}/switch` | POST | 切换当前产品 |
| `/api/products/{product_id}/config` | GET | 获取产品配置 |
| `/api/products/{product_id}/config` | PUT | 更新产品配置 |
| `/api/schedule` | GET | 获取排期 |
| `/api/schedule/export` | GET | 导出排期 |
| `/api/scene/upload` | POST | 上传场景素材 |
| `/api/scene/folders` | GET | 列出场景文件夹 |
| `/api/scene/folders/{folder_name}/files` | GET | 列出文件夹内文件 |
| `/api/scene/folders/{folder_name}/files/{file_name}` | DELETE | 删除场景文件 |
| `/api/metrics/upload` | POST | 上传视频指标 |
| `/api/metrics/overview` | GET | 指标概览 |
| `/api/metrics/videos` | GET | 视频指标列表 |
| `/api/metrics/topics` | GET | 话题指标 |
| `/api/metrics/scan` | POST | 扫描数据源 |
| `/api/knowledge/upload` | POST | 上传知识库文档 |
| `/api/knowledge/documents` | GET | 列出文档 |
| `/api/knowledge/documents/{doc_id}/items` | GET | 文档知识条目 |
| `/api/knowledge/selling-points` | GET | 列出卖点 |
| `/api/knowledge/selling-points/{item_id}` | PUT | 更新卖点 |
| `/api/knowledge/refresh` | POST | 刷新知识库 |
