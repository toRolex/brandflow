# 版本号注册表

项目当前版本：**0.7.14**（`pyproject.toml` 第 4 行，唯一事实来源）

## 需随发版更新的版本号

| 文件 | 行 | 当前值 | 用途 |
|------|-----|--------|------|
| `pyproject.toml` | 4 | `0.7.14` | ✅ 项目版本（事实来源） |
| `frontend/package.json` | 4 | `0.7.14` | ✅ 前端版本（与 pyproject 同步） |
| `CONTEXT.md` | 132 | `v0.7.14` | ✅ 架构状态版本引用（同步脚本自动更新） |

## worker_version

Worker 注册时向控制面声明的版本标识。当前值 `0.1.0`，独立于项目版本。

| 文件 | 行 | 值 |
|------|-----|------|
| `apps/runtime_worker/loop.py` | 198 | `0.1.0` |
| `apps/runtime_worker/http_client.py` | 11 | `0.1.0`（构造器取 `loop.py` 传入值） |
| `tests/runtime_worker/test_loop.py` | 192 | `0.1.0` |
| `tests/control_plane/test_worker_routes.py` | 36, 54, 77, 103, 134 | `0.1.0` |
| `tests/e2e/test_protocol_smoke.py` | 31 | `0.1.0` |

## 数据 schema 版本（非项目版本，不改）

| 文件 | 行 | 值 | 含义 |
|------|-----|------|------|
| `tools/export_metrics_json.py` | 39 | `1` | 快照数据格式版本 |
| `packages/pipeline_services/export_service.py` | 257 | `1.0` | 时间线 JSON 格式版本 |
| `tests/pipeline_services/test_export_service.py` | 348, 365 | `1.0` | 时间线格式测试断言 |
| `packages/pipeline_services/asset_library/vision_client.py` | 178 | `2023-06-01` | Anthropic API 版本标头 |

## 发版清单

每次发版（bump `pyproject.toml` version）后，检查并更新：

- [ ] `frontend/package.json` → 与 `pyproject.toml` 一致
- [ ] `CONTEXT.md` → 架构状态中的 v0.x.x 引用
- [ ] 运行 `uv run python tools/sync_version.py` → 自动同步上述两项
