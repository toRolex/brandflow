# Brandflow Windows 部署包

## 快速开始

### 首次部署（新机器）

以管理员身份双击运行：

```
packaging\windows\deploy.bat
```

自动完成：
1. 安装前置工具（uv、Node.js 20、pnpm、FFmpeg、NSSM）
2. 初始化目录（config/、workspace/、logs/）
3. 生成 .env 模板（需手动填入 API Key）
4. 拉取最新代码
5. 安装 Python 依赖 + 编译前端
6. 注册 NSSM 服务（开机自启）
7. 健康检查

首次部署后，编辑 `D:\brandflow\.env` 填入 API Key，再运行一次 `deploy.bat`。

### 日常使用

| 操作 | 脚本 |
|------|------|
| 启动 | `start.bat` — 启动 NSSM 服务并自动打开浏览器 |
| 停止 | `stop.bat` — 停止 NSSM 服务 |
| 重启 | `restart.bat` — 停止后重新启动服务并做健康检查 |
| 更新 | `update.bat` — 拉取最新代码、更新依赖、编译前端、重启服务（前端更新按钮调用） |
| 完整部署 | `deploy.bat` — 首次部署或重装环境 |

## 项目目录（D:\brandflow）

| 目录/文件 | 说明 |
|-----------|------|
| `config/` | 业务配置（app_config.json、providers.yaml） |
| `workspace/` | 工作数据（项目、素材、输出视频、知识库） |
| `logs/` | 日志（deploy.log、control-plane.log） |
| `.env` | API Key 和环境变量 |
| `frontend/` | React 前端源码 |

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `deploy.bat` | 一键部署：装工具 → 初始化 → 拉代码 → 编译 → 注册服务 → 健康检查。首次部署和重新部署用同一个命令。 |
| `start.bat` | 启动 NSSM 服务并打开浏览器。 |
| `stop.bat` | 停止 NSSM 服务。 |
| `restart.bat` | 停止后重新启动 NSSM 服务，并执行健康检查。 |
| `update.bat` | 由前端 API 调用，执行：拉代码 → 装依赖 → 编译前端 → 重启服务。进度写入 `progress.json`。 |

## 外部工具

由 `deploy.bat` 通过 winget 自动安装：

| 工具 | 安装方式 | 环境变量覆盖 |
|------|----------|-------------|
| FFmpeg | `winget install Gyan.FFmpeg` | `FFMPEG_PATH` |
| FFprobe | 随 FFmpeg 安装 | `FFPROBE_PATH` |
| NSSM | `winget install NSSM` | — |
| whisper.cpp | 手动安装 | `WHISPER_CLI_PATH` |

## 故障排查

| 问题 | 解决 |
|------|------|
| 部署失败 | 查看 `logs/deploy.log` |
| 后端启动失败 | 查看 `logs/control-plane.log`，检查端口 17890 是否被占用 |
| 前端编译失败 | 确认 Node.js 20+ 已安装 |
| 工具找不到 | 运行 `where ffmpeg` 确认 PATH，或设置环境变量覆盖 |

`deploy.bat` 会把 CPython 3.11 安装到部署目录的 `.uv-python/`，避免
GitHub Actions runner 与 NSSM 服务账户使用不同用户级 Python。依赖先构建到
`.venv-deploy/`；构建成功后才短暂停止控制面，将其原子切换为 `.venv/`。
新环境健康检查失败时，脚本会恢复上一份虚拟环境并重新启动原服务。
Node.js 20 同样安装到 `.node/` 并显式加入部署进程 PATH，避免服务账户无法
执行 pnpm lifecycle 脚本。
