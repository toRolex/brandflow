# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-06-04

### New Features

- **feat**: 支持手动输入文案和上传音频，跳过LLM/TTS生成
  - 允许用户直接输入文案，无需 DeepSeek 脚本生成
  - 允许上传音频文件，跳过 MiMo TTS 合成步骤

### Bug Fixes

- **fix**: 修复测试中的路径问题并添加启动脚本

## [0.1.1] - 2026-06-02

### Bug Fixes

#### Video Processing
- **fix(indexer)**: 修复视频切片损坏问题，改用重新编码确保关键帧对齐
  - 将 `_scene_detect_and_cut()` 和 `_split_long_clip()` 中的 `-c copy` 改为 `-c:v libx264`
  - 添加 `-preset fast`, `-crf 23`, `-pix_fmt yuv420p`, `-force_key_frames` 参数
  - 解决 ffmpeg concat 时报错 `No start code is found` 的问题

#### UI/UX
- **fix(clip-review)**: 修复素材卡片布局问题，防止按钮被挤出可视区域
  - 给文件名容器添加 `overflow-hidden` 类
  - 给 asset_id 添加 `truncate` 类
  - 将按钮文字从"打回换素材"改为"打回检索"
  
- **fix(clip-review)**: 彻底修复卡片溢出问题，确保按钮始终可见
  - 给卡片添加 `max-w-full` 类
  - 给句子文本添加 `break-words` 类
  - 给素材列表容器添加 `overflow-x-hidden` 类

- **fix(clip-review)**: 彻底修复按钮在窄屏幕下被挡住的问题
  - 将 ClipReviewCard 布局改为垂直结构，按钮独占一行且全宽显示
  - 移除 JobPipeline 外层容器的 `overflow-hidden`，改为 `overflow-x-auto`

#### Windows Compatibility
- **fix**: 解析相对路径的ffmpeg工具路径
  - 添加 `_resolve_tool_path()` 函数，将相对路径转换为绝对路径
  - 添加 `_get_default()` 函数，根据操作系统自动选择默认路径
  
- **fix**: 修复 Windows 上 subprocess 编码错误
  - 在所有 `subprocess.run` 调用中添加 `encoding="utf-8"` 和 `errors="ignore"`

- **fix**: 修复async参数名冲突
  - 将参数名从 `async` 改为 `async_mode`

#### Indexing
- **fix**: 索引完成后自动隐藏进度条
  - 任务完成 2 秒后自动隐藏进度条

### Features

- **feat**: 支持跨平台工具路径配置
  - 更新 `.env.example`，提供跨平台配置模版

- **feat**: 实现异步索引和实时进度显示
  - 后端改为异步索引，立即返回 `task_id`
  - 添加 `/api/assets/index/{task_id}/status` 轮询端点
  - 添加 `/api/assets/index/{task_id}/logs` SSE 日志流端点
  - 前端使用轮询获取真实进度，每秒更新

### Tests

- **test(indexer)**: 添加视频切片功能的TDD测试
  - 测试 `_scene_detect_and_cut()` 生成的切片可以正常concat
  - 测试 `_split_long_clip()` 生成的切片可以正常concat
  - 验证每个切片都以关键帧(I-frame)开始

## [0.1.0] - 2026-05-31

### Initial Release

- Phase 1 架构骨架
- 控制面：FastAPI + Web 看板
- 执行器：拉模式 worker
- 76 测试全绿
