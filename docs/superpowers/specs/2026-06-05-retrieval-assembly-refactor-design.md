# 检索装配重构 + Job 命名 + 审核修复 设计文档

## 概述

本次改动涉及 6 个需求点，统一在一个 feature 分支实现：

1. Job 创建时指定名称、创建后支持重命名
2. 素材审核打回重检索后前端刷新 + 支持多次打回
3. 降级匹配显示原始匹配意图
4. 移除 TTS 语音拉伸（时长归一化）
5. 视频时长自由化（跟随 TTS 音频）
6. 素材按句裁剪 + 检索改为 LLM 分类 + 随机选取

---

## 架构变更

### 删除项

| 删除项 | 文件 | 原因 |
|--------|------|------|
| `keyword_map.json` | `packages/pipeline_services/asset_library/` | 关键词匹配被 LLM 分类替代 |
| `_parse_sentence()` | `retriever.py` | 替换为 LLM 分类 |
| `load_keyword_map()` | `models.py` | 不再需要 |
| `_ensure_slice_folders()` | `main_controller.py` | 不再需要 5s 固定切片预处理 |
| `_select_clips_for_job()` | `main_controller.py` | 替换为按句检索 |
| `_write_concat_file()` | `main_controller.py` | 裁剪后的临时片段直接 concat |
| `_fit_audio_duration_for_delivery()` | `main_controller.py` | 不再拉伸 TTS |
| `_validate_final_video_duration()` | `main_controller.py` | 不再硬约束时长 |
| 常量 `SLICE_GROUP_COUNT`, `CLIPS_PER_GROUP`, `CLIP_DURATION_SECONDS`, `TARGET_FINAL_VIDEO_MIN_SECONDS`, `TARGET_FINAL_VIDEO_MAX_SECONDS`, `MIN_REQUIRED_SOURCE_SECONDS`, `MAX_CLIP_REUSE`, `CLIPS_PER_GROUP` | `main_controller.py` | 废弃 |

### 修改文件清单

| 文件 | 改动 |
|------|------|
| `packages/pipeline_services/asset_library/retriever.py` | LLM 分类 + 分类内随机选取 |
| `main_controller.py` | worker_a 删 TTS 拉伸; worker_b 按句时长装配视频 |
| `packages/domain_core/models.py` | JobRecord 加 `name` 字段 |
| `apps/control_plane/routes/api_jobs.py` | 创建时接受 name; 新增 PUT rename 路由 |
| `apps/control_plane/routes/reviews.py` | 打回时回退到 asset_retrieving 并重新检索 |
| `packages/domain_core/state.py` | 允许 asset_review → asset_retrieving 回退 |
| `frontend/src/pages/ProjectWorkbench.tsx` | 创建表单加 name 输入 |
| `frontend/src/pages/JobPipeline.tsx` | asset_review 重新拉取 + 多次打回 |
| `frontend/src/components/ClipReviewCard.tsx` | 降级匹配显示原始意图 |
| `frontend/src/components/JobTable.tsx` | 行内重命名 |
| `frontend/src/api/client.ts` | 新增 renameJob API |
| `frontend/src/types/index.ts` | 类型更新 |

---

## 详细设计

### 1. LLM 检索改造

**`retriever.py` —— `_classify_sentence()` 替换 `_parse_sentence()`：**

- 输入：单个句子字符串
- LLM（复用现有 DeepSeek provider，纯文本，无视觉输入）

```
你是一个视频素材分类助手。根据文案句子的语义，从以下分类中选择最匹配的一个：
产地溯源, 筛选分拣, 清洗泡发, 切配处理, 下锅入锅, 烹饪翻炒, 出锅装盘, 成品展示, 试吃品尝, 产品特写

文案：{sentence}

只返回JSON：{"category": "分类名"}
```

- 验证返回分类在 `Category` 枚举中
- 验证失败 → `_fallback()` 兜底

**`_fallback()` 行为不变：** 所有可用素材中选 `usage_count` 最低的。

**检索主流程 `retrieve()` 改动：**

```
旧: _split_sentences() → 每句 _parse_sentence(keyword_map) → query_by_category / fallback
新: _split_sentences() → 每句 _classify_sentence(LLM) → query_by_category → random.choice()
```

`method` 字段：
- `"llm_match"` — LLM 分类成功
- `"fallback"` — 分类失败兜底

### 2. 视频装配改造

**`_build_base_video()` 改动：**

```
旧流程:
  _select_clips_for_job() → 9个固定切片 → concat → -t audio_duration 截断

新流程:
  asset_bundle["selected_clips"] → 每段素材:
    ss = random.uniform(0, 1)  # 随机起始偏移
    t = <该句TTS时长>          # 裁剪时长
    最大取到素材原长（不超）
    ffmpeg -ss {ss} -t {t} -i {素材} → temp_{idx}.mp4
  concat 所有 temp → 底包（自然等于音频总长，不截断）
```

**`_burn_final_video()` 改动：**
- `-shortest` 参数保留（以音频流为准）
- 移除 `-t` 参数

### 3. TTS 拉伸移除

`worker_a` / `asset_worker_loop` 中删除三处 `_fit_audio_duration_for_delivery()` 调用（行 1569, 2847, 2913）。

`_validate_final_video_duration()` 调用（行 1710）改为只记录日志，不抛异常。

### 4. Job 命名

**数据模型：**
```python
class JobRecord(BaseModel):
    name: str = Field(default="")  # 空字符串表示未命名，前端 fallback 到 product
```

**后端 API：**
- `POST /api/projects/{project_id}/jobs` — `CreateJobRequest` 加 `name: str | None`
- `PUT /api/jobs/{job_id}/rename` — `{"name": "新名称"}`

**前端：**
- `ProjectWorkbench.tsx`：创建表单加 name 输入框（可选，placeholder 显示 product 名）
- `JobTable.tsx`：名称列双击进入编辑模式，回车调用 rename API
- `JobPipeline.tsx`：顶部标题显示 `name || product`

### 5. 素材审核打回重检索

**`reviews.py` —— `reject` 路由改动：**

```python
# 旧: job.phase = "queued"; dispatcher.enqueue_demo_job()
# 新:
job.phase = "asset_retrieving"
# 重新运行 AssetRetriever.retrieve(script_text, product)
selected_clips = retriever.retrieve(script_text, product)
# 写回 job 的 selected_clips
# 推进到 asset_review
job.phase = "asset_review"
```

**`state.py` 改动：**
- `next_phase("asset_review")` 允许回退到 `asset_retrieving`（打回场景）

**前端 `JobPipeline.tsx` 改动：**
- `asset_review` 阶段每次渲染时重新 fetch selected_clips
- "全部打回重新检索" 调用 reject API 后自动轮询 `GET /api/jobs/{job_id}` 等待 phase 回到 `asset_review`，展示新素材

**`ClipReviewCard.tsx` 改动：**
- 移除打回次数限制（目前打回一次后按钮 disabled）

### 6. 降级匹配显示原始意图

**数据结构改动：**
`selected_clips` 中每个 clip 增加字段：
```json
{
  "requested_category": "试吃品尝",  // LLM 原始匹配的分类
  "actual_category": "产品特写",     // 实际返回的分类（fallback 时与 requested 不同）
  "method": "llm_match"             // llm_match / fallback
}
```

**前端 `ClipReviewCard.tsx` 改动：**
- 当 `method === "fallback"` 时显示："想匹配：{requested_category} → 降级为：{actual_category}"
- 当 `method === "llm_match"` 时只显示："{actual_category}"

---

## 测试要点

1. **Job 命名**：创建带/不带 name、rename 正常/空字符串/超长
2. **LLM 分类**：正常分类、无效分类回退、LLM 超时回退
3. **随机裁剪**：重复生成不应产生完全相同的视频（ss 随机）
4. **视频时长**：生成视频总长应等于 TTS 音频总长（误差 < 0.5s）
5. **审核打回**：打回→重检索→新素材展示→再次打回 完整链路
6. **降级显示**：fallback 材料确认显示 requested_category

---

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 分类增加延迟 | 每句一次 LLM 调用，7-8 句可能增加 5-10s | 可后续改为批量一次调用 |
| 随机裁剪可能截到不完整画面 | 视觉效果偶尔不佳 | 已用 vision_client 分类的素材通常画面稳定 |
| 删除旧切片逻辑后旧项目不兼容 | 旧项目数据有 `切片_01-09` 目录 | 不影响，旧数据仅不被新流程引用 |
