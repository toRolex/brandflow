# Brandflow Windows 部署包

本目录包含 Windows 环境的部署脚本。

## 项目目录结构

| 目录/文件 | 职责 |
|-----------|------|
| `config/` | 业务配置目录。`app_config.json` 保存 provider / model / voice / thinking / scene 等配置；`providers.yaml` 是前端系统配置页兼容存储。 |
| `workspace/` | 工作目录。项目数据、素材、输出视频、知识库、检索索引等。 |
| `logs/` | 日志目录。`deploy.log`、`control-plane.log`、`worker.log`。 |
| `.env` | API Key 与可选环境变量覆盖。由 `deploy.bat` 从 `.env.example` 自动生成模板。 |
| `frontend/` | React 前端源码。 |

## 部署步骤

### 首次部署（新机器）

以管理员身份运行一键部署脚本：

```cmd
packaging\windows\deploy.bat
```

脚本自动完成：
1. **安装前置工具**（幂等）— uv / nvm / Node.js 20 / pnpm / FFmpeg / NSSM
2. **初始化目录** — 创建 `config/`、`workspace/`、`logs/`
3. **生成 `.env` 模板** — 从 `.env.example` 复制，需手动填入 API Key
4. **拉取最新代码** — `git fetch --tags` + `git pull`
5. **编译前端** — `pnpm install` + `pnpm build`
6. **注册 Windows 服务** — 通过 NSSM 注册控制面与 worker 为自动启动服务
7. **重启服务 + 健康检查** — 失败自动回滚到上一个部署版本

首次部署后，编辑 `.env` 填入真实 API Key，然后重新运行 `deploy.bat` 重启服务。

### 日常更新

```cmd
packaging\windows\deploy.bat
```

自动拉取最新代码、编译、重启服务、健康检查，失败自动回滚。

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `deploy.bat` | **一站式部署**：装工具 → 初始化 → 拉代码 → 编译 → 注册/重启服务 → 健康检查 + 回滚。首次部署和日常更新用同一个命令。 |
| `start.bat` | 开发调试：同时启动后端和前端，日志写入 `logs/`，按任意键停止。 |
| `start_worker.bat` | 单独启动 runtime worker。 |
| `deploy_analytics.bat` | 单独部署分析服务。 |

## 外部工具

FFmpeg / FFprobe / NSSM 由 `deploy.bat` 首次运行时通过 winget 自动安装到系统 PATH。

如需手动配置路径，设置环境变量覆盖（优先级高于系统 PATH）：

| 工具 | 环境变量 |
|------|----------|
| FFmpeg | `FFMPEG_PATH` |
| FFprobe | `FFPROBE_PATH` |
| whisper.cpp | `WHISPER_CLI_PATH` |

## 故障排查

| 现象 | 排查方式 |
|------|----------|
| 部署失败 | 查看 `logs/deploy.log`。 |
| 后端启动失败 | 查看 `logs/control-plane.log`，常见原因：端口 17890 被占用、`.env` 密钥无效、FFmpeg 未找到。 |
| 前端编译失败 | 检查 Node.js 版本（需 20+），查看终端输出的错误信息。 |
| 工具找不到 | 运行 `where ffmpeg` 确认是否在 PATH 上，或设置 `FFMPEG_PATH` 环境变量。 |

## 约束

- `start.bat` 只启动已安装好的服务，不修改任何源码或锁文件。
- 生产环境升级使用 `deploy.bat`，开发环境手动 `git pull` 后重启 `start.bat`。
