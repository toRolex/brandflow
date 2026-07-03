# Phase 2: toB 内容无关化 — 场景拼接 + 混剪通用化 + 导出包

## Problem Statement

Phase 1 移除了硬编码的"滋元堂/荔枝菌/充分烹熟"品牌引用，但系统本质上仍然是一个"LLM 生成食品短视频"的流水线。要部署给零食公司或其他行业的 toB 客户，存在三个根本性差距：

1. **视频生产模式单一** — 只支持 LLM 生成脚本 + 素材库混剪。toB 客户需要额外的"固定场景拼接"能力：从预设文件夹随机取素材、简单拼接加转场，不需要配音和字幕。
2. **素材分类是硬编码的** — 10 个食品类 Category（产地溯源、烹饪翻炒…）对零食/3C/服装行业毫无意义。每个 Instance 需要自己的分类体系。
3. **产物不完整** — 只输出最终 MP4。toB 客户需要中间产物（原始素材、独立音轨、字幕、EDL 时间线）用于二次精剪。

另外，Import 模式（预写脚本）和 Generate 模式（LLM 生成）的切换目前靠 `manual_script` 非空来隐式判断，缺少显式控制。审核流程和状态机也未根据模式区分。

## Solution

### 核心变更

**1. 双模式显式切换**

Job 新增 `mode` 字段（`"import"` | `"generate"`）。模式决定状态机、审核门和生产行为：

- **Import 模式**：脚本由 `manual_script` 提供，Scene Segment + Montage Segment 两段生产
- **Generate 模式**：LLM 生成脚本，仅 Montage Segment（保留旧流程）

**2. Scene Segment — 固定场景拼接**

Import 模式下，视频前半部分从 N 个场景文件夹中各随机选取一个视频，按序拼接，片段间 crossfade 转场。不需要 TTS 配音和字幕。Scene Segment 和 TTS/字幕可并行执行。

**3. Instance 级素材分类体系**

Category 从硬编码枚举变为 Instance 配置文件。每个 Instance 定义自己的分类名、描述和 Vision prompt。AI 可扫描素材库自动建议分类，运营人员审核确认。混剪段的句子级匹配逻辑不变，仅数据源替换。

**4. Export Bundle — 完整产物导出包**

除最终 MP4 外，导出原始素材、独立音轨（WAV）、字幕文件（SRT）、EDL 时间线 JSON，打包为 ZIP 供 DaVinci Resolve / Premiere Pro 二次精剪。

**5. Web 场景素材上传**

前端提供上传界面，运营人员通过浏览器上传视频到场景文件夹，无需操作服务器文件系统。

## User Stories

### 模式与状态机

1. As a pipeline operator, I want to create a job in Import mode with a pre-written script, so that the system skips LLM generation and goes straight to video production.
2. As a pipeline operator, I want to create a job in Generate mode when I don't have a script ready, so that LLM generates the script for me.
3. As a pipeline operator, I want the system to use different production pipelines for Import vs Generate mode, so that pre-written scripts get Scene+Montage processing while LLM scripts follow the existing flow.
4. As a pipeline operator, I want the Scene Segment and TTS generation to run in parallel in Import mode, so that total job time is reduced.

### 场景拼接

5. As a content operator, I want the system to randomly pick one video from each of N configured scene folders, so that each video gets a unique scene opening without manual selection.
6. As a content operator, I want scene clips to be concatenated in folder order with crossfade transitions, so that the opening sequence feels professional and smooth.
7. As an Instance deployer, I want to configure scene folders and transition duration per deployment, so that a snack company and a 3C company can have different scene structures.
8. As a content operator, I want to upload scene videos through the web UI into specific scene folders, so that I don't need server filesystem access.
9. As a content operator, I want the Scene Segment video to have no voiceover or subtitles, so that it serves as a clean visual opening before the narrated Montage Segment.

### 素材分类通用化

10. As an Instance deployer, I want to define my own asset categories (name, description, Vision prompt) instead of using hardcoded food categories, so that the system works for any industry.
11. As an Instance deployer, I want the AI to scan all imported assets and suggest a category system automatically, so that I don't have to design categories from scratch.
12. As a content operator, I want the Montage Segment to use my Instance's categories for clip matching, so that retrieved footage matches my product domain.

### 混剪通用化

13. As a content operator, I want the Montage Segment to match script sentences to asset categories using the existing sentence-level logic, so that clip selection quality is maintained.
14. As a content operator, I want each Montage clip's display duration to be driven by TTS audio timing, so that visuals sync with voiceover.
15. As a content operator, I want the Montage Segment to include TTS voiceover and burned-in subtitles, so that the second half of the video is fully narrated.

### 导出包

16. As a video editor, I want to download the original source clips (scene + montage) separately from the final MP4, so that I can re-edit them in professional software.
17. As a video editor, I want the TTS audio track as a separate WAV file, so that I can replace or remix the voiceover.
18. As a video editor, I want the SRT subtitle file without burned-in rendering, so that I can adjust subtitle styling or timing.
19. As a video editor, I want a JSON timeline description (EDL) recording each clip's in/out points and transition types, so that I can import the edit into DaVinci Resolve or Premiere Pro.
20. As a pipeline operator, I want all export artifacts packaged in a single ZIP with a clear directory structure, so that download and handoff is simple.

### 审核流程

21. As a pipeline operator, I want Import mode to only require asset_review and final_review gates, so that I don't waste time reviewing pre-written scripts.
22. As a pipeline operator, I want Generate mode to keep all four review gates, so that LLM-generated content still gets human verification.
23. As a pipeline operator, I want auto_approve to skip all review gates when enabled, regardless of mode, so that fully automated production runs remain possible.

### 前端

24. As a frontend user, I want to see a mode toggle (Import / Generate) when creating jobs, so that I explicitly control which pipeline runs.
25. As a frontend user, I want to paste or upload script text in Import mode, so that I can feed pre-written content to the pipeline.
26. As a frontend user, I want to upload scene videos to specific scene folders through the browser, so that I don't need server access.
27. As a frontend user, I want to download the Export Bundle ZIP from the job detail page, so that I can access all intermediate products.
28. As a frontend user, I want the script preview panel to adapt based on mode — showing manual script review in Import mode and generated script review in Generate mode.

## Implementation Decisions

### 状态机重构

**Import 模式 Phase 顺序**（并行分支通过 `PhaseOrchestrator` 的并发调度实现）：
```
queued → scene_assembling ──────────────────────┐
       → tts_generating → subtitle_generating ──┤
                                                 ↓
                            montage_assembling ←─┘
                                                 ↓
                            video_rendering
                                                 ↓
                            final_review → completed
```

- `scene_assembling` 和 `tts_generating` 无数据依赖，可并行
- `montage_assembling` 依赖 TTS 完成（脚本正文决定分类匹配，TTS 音频时长决定素材展示时长）
- `subtitle_generating` 依赖 TTS 完成（音频时间对齐）

**Generate 模式 Phase 顺序**（保留现有一维流程）：
```
queued → script_generating → script_review → tts_generating → tts_review
       → subtitle_generating → asset_retrieving → asset_review
       → video_rendering → final_review → completed
```

### PhaseOrchestrator 并行调度

`PhaseOrchestrator` 新增 `run_phases_parallel(phases: list[str], ctx)` 方法，接收一组无依赖关系的 phase，使用 `concurrent.futures.ThreadPoolExecutor` 并行执行各自的 handler。控制面 `_auto_tick` 在 Import 模式下检测到 `scene_assembling` 和 `tts_generating` 同时处于 pending 时，调用并行调度。

Worker 端保持单 phase 拉取模式不变 — 并行调度在控制面侧完成，Worker 仍然拉取单个 phase 执行。

### 数据模型变更

**JobRecord 新增字段**：
- `mode: str = "import"` — 生产模式（`"import"` | `"generate"`）
- `scene_folder_ids: list[str] = []` — Job 级场景文件夹覆盖（空则用 Instance 默认）
- `transition_duration_ms: int = 500` — 转场时长（毫秒），可用于 Job 级覆盖

**SceneFolder 配置结构**（`app_config.json`）：
```json
{
  "scene": {
    "folders": [
      {"name": "品牌开场", "path": "scene/brand-intro"},
      {"name": "产品展示", "path": "scene/product-showcase"},
      {"name": "使用场景", "path": "scene/usage"}
    ],
    "transition_duration_ms": 500
  }
}
```

**Category 配置结构**（`app_config.json`，替代硬编码枚举）：
```json
{
  "asset_library": {
    "categories": [
      {"id": "product_display", "name": "产品展示", "vision_prompt": "Identify product close-up shots...", "description": "产品特写和展示镜头"},
      {"id": "lifestyle_scene", "name": "生活场景", "vision_prompt": "Identify lifestyle usage scenes...", "description": "产品使用场景"}
    ]
  }
}
```

### PhaseContext 变更

PhaseContext 新增字段：
- `mode: str` — 当前 Job 的生产模式
- `scene_folder_paths: list[str]` — 解析后的场景文件夹绝对路径
- `transition_duration_ms: int` — 转场时长

### API 变更

**BatchCreateRequest 新增字段**：`mode: str = "import"`

**BatchJobItem 新增字段**：`scene_folder_ids: list[str] = []`

**新建 API 端点**：
- `POST /api/scene/upload` — 上传场景素材到指定文件夹（multipart form）
- `GET /api/scene/folders` — 获取 Instance 的场景文件夹列表
- `GET /api/jobs/{id}/export` — 下载 Export Bundle ZIP
- `POST /api/assets/categories/suggest` — AI 扫描素材库建议分类

### Scene Assembling Handler

新 handler `_run_scene_assembly(ctx: PhaseContext)`：
1. 从 `ctx.scene_folder_paths` 读取场景文件夹列表
2. 每个文件夹随机选一个视频文件（支持 mp4/mov/avi）
3. 使用 ffmpeg `concat` filter + `xfade` filter 按序拼接
4. 输出拼接后的场景段视频（无音轨）
5. 返回 `ArtifactPointer` 指向场景段视频

### Export Bundle 生成

`video_rendering` handler 在合成最终 MP4 时，额外生成：
1. 复制所有被选中的原始素材到 `raw_clips/` 子目录
2. 复制 TTS WAV 音轨到 `audio/` 子目录
3. 复制 SRT 字幕到 `subtitle/` 子目录
4. 生成 `timeline.json` — EDL 时间线描述
5. 打包为 `{job_id}_export.zip`

**timeline.json 结构**：
```json
{
  "version": "1.0",
  "segments": [
    {
      "type": "scene",
      "clips": [
        {"file": "raw_clips/scene_001.mp4", "duration_ms": 5000, "transition": "crossfade", "transition_duration_ms": 500}
      ]
    },
    {
      "type": "montage",
      "clips": [
        {"file": "raw_clips/montage_042.mp4", "in_point_ms": 0, "out_point_ms": 3200, "sentence_index": 0}
      ]
    }
  ],
  "audio": {"file": "audio/tts.wav", "duration_ms": 45000},
  "subtitle": {"file": "subtitle/script.srt"}
}
```

### AI 分类建议

`POST /api/assets/categories/suggest` 端点：
1. 从素材库随机采样 N 个视频（默认 20）
2. 对每个视频取一帧，调用 Vision 模型获取描述
3. 将所有描述汇总，调用 LLM 归纳为 5-15 个分类
4. 为每个分类生成 `vision_prompt`（用于后续自动标注）
5. 返回分类建议列表，运营人员在前端确认后写入 `app_config.json`

### from_hardcoded 到 from_config 的过渡

`asset_library/models.py` 中的 `Category` 枚举保留但标记 deprecated。新增 `CategoryConfig` 数据类从 `app_config.json` 加载分类。`asset_library/` 中所有引用 `Category` 枚举的模块改为使用 `CategoryConfig`。

## Testing Decisions

### 最高测试接缝

**状态机过渡测试** — 验证 Import 模式和 Generate 模式的 Phase 顺序正确：
- Import mode: `queued` → `scene_assembling` + `tts_generating` 并行 → `montage_assembling` → `video_rendering` → `final_review` → `completed`
- Generate mode: 保留现有顺序
- 测试不关心具体 handler 实现，只验证 Phase 转换逻辑

### 中间测试接缝

**Handler 输出测试** — 每个新 handler 接受 `PhaseContext`，返回 `list[ArtifactPointer]`：
- `_run_scene_assembly`: 验证返回的 ArtifactPointer 指向合法视频文件，且 segments 数量等于文件夹数量
- Export Bundle 生成: 验证 ZIP 包含所有必需文件和 `timeline.json`
- Category 配置加载: 验证 `AppConfigManager` 正确读取 `asset_library.categories`

### 已有接缝复用

- `tests/smoke/test_package_layout.py` — 确保新模块可导入
- `tests/smoke/test_phase1_brand_regression.py` — 确保无品牌引用回归
- `tests/provider_config/test_app_config.py` — 扩展验证新配置结构

### 好测试标准

- 测试外部行为（"Import mode Job 不会触发 script_generating"），不测试实现细节
- 测试数据隔离 — 使用临时目录作为场景文件夹和素材库
- 不调用真实 LLM/TTS API — 使用 mock 或 fixture

### 不再新增端到端测试

全链路 LLM/TTS 测试依赖外部 Provider，保持当前做法：在开发环境手工验证。

## Out of Scope

- 多租户数据隔离（SaaS multi-tenancy）
- 品牌级前端配置面板（品牌色、TTS 音色 UI、脚本风格模板）
- 产品知识库上传和自动卖点提取
- TTS Provider 抽象扩展
- 素材库关键词映射通用化（`keyword_map.json`）
- Vision prompt 模板通用化
- 场景段支持非 MP4 格式的复杂转场（如推拉、擦除）
- DaVinci/Premiere 原生工程文件导出（`.drp`/`.prproj`）— 仅支持 JSON EDL
- 删除旧 LLM 库文件
- 生产者-消费者队列架构升级

## Further Notes

- Phase 2 是 Phase 1 的继续。Phase 1 已经让品牌名和产品名可配置，Phase 2 让生产流程和素材分类可配置。
- `AppConfigManager` 已经支持深度合并和嵌套键，新的 `scene` 和 `asset_library.categories` 配置直接使用现有机制。
- 并行调度（Scene + TTS）在控制面侧实现，Worker 协议保持不变。这避免了 Worker 端的复杂状态管理。
- AI 分类建议是"一键操作"——运营人员触发后在后台运行，完成后前端展示建议列表，审核确认后写入配置。不替代手动配置，作为辅助工具存在。
- Category 从枚举迁移到配置后，旧枚举保留但标记 deprecated，`vision_client.py` 和 `retrieval_embedding.py` 等模块的 prompt 从配置读取而非常量。
