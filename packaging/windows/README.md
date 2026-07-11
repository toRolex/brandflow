# Brandflow Windows 部署包

本目录包含 Windows 环境下的初始化、启动与运维脚本。

## 目录职责

部署包解压后，项目根目录应保持以下结构：

| 目录/文件 | 职责 |
|-----------|------|
| `tools/bin/` | 存放外部原生工具（`ffmpeg.exe`、`ffprobe.exe`、`whisper-cli.exe`）。运行时优先于系统 PATH 被加载。 |
| `config/` | 业务配置目录。`app_config.json` 保存 provider / model / voice / thinking / scene 等业务配置；`providers.yaml` 是前端“系统配置”页面的兼容存储。 |
| `workspace/` | 工作目录。项目数据、素材、输出视频、知识库、检索索引等均落在此处。 |
| `logs/` | 日志目录。`init.bat` 写入 `init.log`，`start.bat` 写入 `backend.log` 与 `frontend.log`。 |
| `.env` | API Key 与可选环境变量覆盖。由 `init.bat` 从 `.env.example` 自动生成模板，需人工填入真实密钥。 |
| `frontend/` | React 前端源码与 `node_modules`。 |

## 随部署包必须带走的外部工具

以下二进制需要预先放置在 `tools/bin/` 中，或配置环境变量指向它们：

| 工具 | 文件名 | 环境变量覆盖 | 说明 |
|------|--------|--------------|------|
| FFmpeg | `ffmpeg.exe` | `FFMPEG_PATH` | 视频剪辑、转码、拼接、烧录字幕。 |
| FFprobe | `ffprobe.exe` | `FFPROBE_PATH` | 读取媒体时长、分辨率、码率等元数据。 |
| whisper.cpp | `whisper-cli.exe` | `WHISPER_CLI_PATH` | 本地语音转文字，用于 TTS 后字幕对齐。 |

解析优先级：环境变量 > `tools/bin/` > 系统 PATH。`packages/pipeline_services/media_utils.py` 统一负责路径解析。

## 可选工具

| 工具 | 说明 |
|------|------|
| Git | 用于后续拉取代码升级。 |
| Node.js 20+ + npm | 前端开发服务器依赖。`setup-prereq.bat` 可以一次性安装 uv、nvm-windows、Node.js、pnpm、FFmpeg、NSSM。 |
| NSSM | 用于将后端/Worker 注册为 Windows 服务（生产部署）。 |

## 部署步骤

1. 将部署包解压到目标目录，例如 `D:\brandflow`。
2. 把 `ffmpeg.exe`、`ffprobe.exe`、`whisper-cli.exe` 复制到 `tools/bin/`。
3. 双击或在终端运行：
   ```cmd
   packaging\windows\init.bat
   ```
   该脚本会：
   - 检查 Python 3.11+ 和 uv 是否可用；
   - 创建 `tools/bin/`、`config/`、`workspace/`、`logs/`；
   - 运行 `uv run python -m packages.deploy_health` 输出部署体检结果；
   - 从 `.env.example` 生成 `.env` 模板；
   - 提示还需补齐的工具与配置。
4. 编辑 `.env`，填入真实的 LLM / TTS / Vision API Key。
5. 安装前端依赖（仅首次）：
   ```cmd
   cd frontend
   npm install
   cd ..
   ```
6. 启动后端与前端：
   ```cmd
   packaging\windows\start.bat
   ```
   脚本会同时启动：
   - 后端：`uv run python -m apps.control_plane`（端口 17890）
   - 前端：`npm run dev`（端口 5173）

   日志分别写入 `logs/backend.log` 与 `logs/frontend.log`。
7. 验证：
   - 后端健康接口：`http://127.0.0.1:17890/api/health`
   - 前端首页：`http://127.0.0.1:5173`

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `init.bat` | 初始化部署目录、体检、生成 `.env` 模板。 |
| `start.bat` | 同时启动后端和前端，日志写入固定路径，按任意键停止服务。 |
| `start_worker.bat` | 单独启动 runtime worker。 |
| `setup-prereq.bat` | 以管理员身份一次性安装 uv / nvm / Node.js / pnpm / FFmpeg / NSSM。 |
| `deploy.bat` | 生产环境拉取最新代码、构建前端、重启 NSSM 服务并健康检查。 |
| `setup-nssm.bat` | 使用 NSSM 注册后端与 worker 为 Windows 服务。 |

## 故障排查

| 现象 | 排查方式 |
|------|----------|
| init.bat 报错 | 查看 `logs/init.log`。 |
| 后端启动失败 | 查看 `logs/backend.log`，常见原因：端口 17890 被占用、`.env` 密钥无效、FFmpeg 未找到。 |
| 前端启动失败 | 查看 `logs/frontend.log`，常见原因：端口 5173 被占用、`node_modules` 未安装。 |
| 体检报工具缺失 | 将对应 `.exe` 放入 `tools/bin/`，或设置 `FFMPEG_PATH` / `FFPROBE_PATH` / `WHISPER_CLI_PATH`。 |

## 约束

- `start.bat` 不会修改 `uv.lock`、`package-lock.json` 或任何源码文件；它只启动已安装好的服务。
- 如需升级，请使用 `deploy.bat`（生产环境）或 Git 手动拉取后重新执行 `init.bat`。
