# 前端 React 改造设计 Spec

> 决策日期: 2026-05-19
> 状态: 已确认，待实施

## 1. 背景

当前前端为极简 Jinja2 模板（4 个 HTML 页面），几乎无 CSS/JS，仅有 layout.html 在 Phase 2 worktree 中加入基础样式。工作人员为非技术人员，需要在浏览器中完成视频生产的全流程操作，包括文件上传、脚本审核、中间产物预览、排期管理等。

## 2. 技术选型

| 层 | 选择 | 理由 |
|------|------|------|
| 前端框架 | React 19 + TypeScript | 用户技术栈参考，长期维护 |
| 构建工具 | Vite | 快速 HMR，TypeScript 原生支持 |
| CSS | Tailwind CSS v4 | 快速开发，无需手写 CSS |
| 后端 | FastAPI（保持现有） | 已有成熟链路 |
| 排期存储 | SQLite | Python 内置，零部署成本，支持 SQL 查询，可导出 Excel |
| 通信 | REST `/api/*` | 前后端分离，清晰接口契约 |

## 3. 页面架构：4 页

| 页面 | 路由 | 功能 |
|------|------|------|
| 项目列表 | `/` | 所有项目列表，新建/打开项目 |
| 项目工作台 | `/projects/:id` | 创建 Job、上传素材、Job 列表、素材库 |
| 流水线详情 | `/jobs/:id` | 9 步流水线 + 审核操作 + 产物预览 |
| 系统配置 | `/config` | Provider 配置（复用 Phase 2 的 config API） |

排期管理作为工作台内的 Tab 或区域，不单独成页。

## 4. 核心页面设计

### 4.1 项目工作台

三个区域合一页：

- **创建 Job**：产品下拉选择、文件拖拽/点击上传、目标平台多选（抖音/小红书/视频号/快手）、"创建并开始生产"按钮
- **Job 列表**：表格展示（Job ID、产品、状态、进度 ③/⑨、操作链接）。状态用颜色标签：待审核黄、已完成绿、失败红
- **素材库**：视频卡片网格（缩略图占位、文件名、时长、分辨率）。支持预览和删除，绿色边框标记"当前使用中"，末尾有"上传新素材"入口

交互流程：创建 Job → 自动跳转流水线详情页

### 4.2 流水线详情

左侧步骤条 + 右侧详情（用户选择的方案 A）。

**左侧 9 步垂直步骤条：**
1. 上传素材
2. 生成脚本
3. 脚本审核（审核门）
4. 生成包装
5. TTS 配音
6. 转录字幕
7. 底包拼接
8. 封面·烧录（审核门）
9. 排期发布

步骤状态：✓ 已完成（蓝底）、! 待审核（黄底，当前）、数字 待执行（灰字）、✗ 失败（红色）

底部全局操作：暂停、重试当前、查看日志

**右侧详情按步骤切换：**

| 步骤 | 预览区 | 操作按钮 |
|------|------|------|
| ① 素材 | 视频播放器 + 文件信息 | 更换视频 |
| ② 脚本 | 脚本全文 + 质检结果（字数/品牌/品名/充分烹熟/禁词） | 通过 / 打回 / 重生成 |
| ③ 审核 | 同 ② | 通过 / 打回 |
| ④ 包装 | 标题 + 简介 + 标签（可编辑 input） | 保存修改 / 重生成 |
| ⑤ 配音 | 音频播放器 | 重生成 / 切换音色 |
| ⑥ 转录 | 字幕文本编辑器 | 重转录 |
| ⑦ 底包 | 视频播放器 | 重拼接 |
| ⑧ 封面·烧录 | 封面图预览 + 最终视频播放器 | 通过 / 打回 / 重生成封面 / 重新烧录 |
| ⑨ 排期 | 各平台标题+简介 + 状态 | 确认发布 |

审核门（③⑧）用黄色高亮边框区分，需要人工确认才继续。

### 4.3 排期管理

- 作为项目工作台内的一个 Tab
- 表格：视频、平台、标题、简介、状态
- 筛选：按平台、按状态
- 一键导出 Excel
- SQLite 存储，表结构：
  - `schedule_entries(id, job_id, platform, title, description, status, created_at, updated_at)`

### 4.4 系统配置

复用 Phase 2 worktree 中已有的 config 页面设计（provider 选择 + 字段配置 + 密钥清空），迁移为 React 组件。

## 5. 后端 API 扩展

所有新路由使用 `/api/*` 前缀，与 Jinja 模板路由分离。

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/api/projects` | 项目列表 | 新增 |
| `POST` | `/api/projects` | 创建项目 | 新增 |
| `GET` | `/api/projects/{id}` | 项目详情 + Job 列表 | 新增 |
| `POST` | `/api/projects/{id}/upload` | 上传视频到 source_assets | 新增 |
| `GET` | `/api/projects/{id}/assets` | 素材列表 | 新增 |
| `DELETE` | `/api/projects/{id}/assets/{name}` | 删除素材 | 新增 |
| `POST` | `/api/projects/{id}/jobs` | 创建 Job 并入队 dispatch | 新增 |
| `GET` | `/api/jobs/{id}` | Job 详情含产物路径和中间状态 | 扩展 |
| `POST` | `/api/jobs/{id}/pause` | 暂停 Job | 新增 |
| `POST` | `/api/jobs/{id}/retry` | 从当前阶段重试 | 新增 |
| `GET` | `/api/jobs/{id}/logs` | 获取运行日志 | 新增 |
| `POST` | `/api/reviews/{id}/approve` | 审核通过（需真实状态变更） | 扩展 |
| `POST` | `/api/reviews/{id}/reject` | 审核打回（需真实状态变更） | 扩展 |
| `GET` | `/api/schedule` | 排期数据（支持 ?project_id=&platform=） | 新增 |
| `GET` | `/api/schedule/export` | 导出 Excel | 新增 |

已有路由（保留）：
- `POST /workers/poll` — worker 拉取任务
- `GET /workers/tasks/{id}/input-bundle` — 下载输入包
- `POST /workers/tasks/{id}/heartbeat` — 心跳
- `POST /workers/tasks/{id}/artifacts` — 上传产物
- `POST /workers/tasks/{id}/report` — 上报结果
- `GET/PUT /api/config` — 系统配置（Phase 2）

## 6. 目录结构

```
frontend/                          # 新增
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts                 # proxy /api → localhost:17890
├── tailwind.config.ts
└── src/
    ├── main.tsx
    ├── App.tsx                    # React Router 路由
    ├── api/
    │   └── client.ts              # fetch 封装，所有 /api/* 调用
    ├── pages/
    │   ├── ProjectList.tsx
    │   ├── ProjectWorkbench.tsx
    │   ├── JobPipeline.tsx
    │   └── ConfigPage.tsx
    ├── components/
    │   ├── PipelineSidebar.tsx     # 左侧步骤条
    │   ├── ScriptPreview.tsx       # 脚本展示 + 质检结果
    │   ├── MediaPlayer.tsx         # 视频/音频播放器
    │   ├── SubtitleEditor.tsx      # 字幕文本编辑器
    │   ├── FileDropzone.tsx        # 拖拽上传
    │   ├── AssetCard.tsx           # 素材卡片
    │   ├── JobTable.tsx            # Job 列表表格
    │   ├── ScheduleTable.tsx       # 排期表格
    │   └── StatusBadge.tsx         # 状态彩色标签
    └── types/
        └── index.ts               # TypeScript 类型定义
```

## 7. 现有 Jinja2 模板处理

逐步替换策略：

- 开发期间 Vite dev server proxy 到 FastAPI，React 页面走 Vite，API 走 FastAPI
- Jinja2 模板暂时保留不删，用于 worker 协议端点返回（那些是 API 不是页面）
- 全部 React 页面就绪后，移除 Jinja2 模板和 `templates/` 目录
- `layout.html` 中的 CSS 变量设计可融入 Tailwind theme

## 8. 与 Phase 2 的衔接

- Phase 2 worktree 中的 `packages/provider_config/` 和 `/api/config` 路由先合并到 main
- Phase 2 的 `config.html` 被 React `ConfigPage.tsx` 替代
- Phase 2 的 `project_detail.html` 被 React `ProjectWorkbench.tsx` 替代
- Phase 2 的 `job_detail.html` 被 React `JobPipeline.tsx` 替代
- Provider config API 保持契约不变，React 前端直接调用

## 9. 非目标

- 不做用户登录 / 权限系统（内部单机工具）
- 不做多品牌扩展
- 不做数据库迁移系统（SQLite 从零开始）
- 不做 SSR / SSG
- 不做 PWA / 移动端适配（桌面浏览器即可）
- 不引入状态管理库（React Context + useState 足够）

## 10. 成功标准

- 工作人员不需要命令行，全流程通过浏览器按钮完成
- 视频文件通过拖拽/点击上传，无需手动复制到目录
- 每一步中间产物（脚本/音频/字幕/视频/封面）都能在页面预览
- 审核操作（通过/打回）有明确视觉反馈
- 排期数据可查看、筛选、导出 Excel
