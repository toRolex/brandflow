# 前端视觉适配 mockup 方案 A 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 React 实现调整为方案 A mockup 的视觉规格（左侧步骤条 + 右侧详情），覆盖流水线详情页、项目工作台、项目列表三个核心页面。

**Architecture:** 纯前端变更，不涉及后端 API。修改现有 React 组件的 Tailwind 类名，调整色彩、间距、字号、圆角以匹配 mockup 内联 CSS 的设计系统。核心色板：蓝 `#0969da` / 黄 `#e8b931` / 红 `#d1242f` / 绿 `#1a7f37` / 灰 `#59636e` `#eff2f5` `#393f46`。

**Tech Stack:** React 19, TypeScript, Tailwind CSS v4

---

## 文件映射总览

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `frontend/src/components/PipelineSidebar.tsx` | 修改 | 步骤条色彩重构：已完成蓝底白字、审核黄底高亮、待执行灰底 |
| `frontend/src/components/ScriptPreview.tsx` | 修改 | 脚本卡片白色背景、质检项紧凑横排、按钮圆角缩小 |
| `frontend/src/pages/JobPipeline.tsx` | 修改 | 详情区整体灰底、步骤标题带步骤号 |
| `frontend/src/pages/ProjectWorkbench.tsx` | 修改 | 三区卡片边框 + 间距、创建按钮图标 |
| `frontend/src/components/JobTable.tsx` | 修改 | 新增进度列 `③/⑨`、状态标签彩色背景、失败行红色 |
| `frontend/src/components/AssetCard.tsx` | 修改 | 视频图标 `🎬`、预览按钮、精确圆角 |
| `frontend/src/components/FileDropzone.tsx` | 修改 | 边框加粗 `border-2`、背景 `bg-[#eff2f5]` |
| `frontend/src/pages/ProjectList.tsx` | 修改 | 表格圆角容器、空态图标大小 |
| `frontend/src/components/StatusBadge.tsx` | 修改 | 颜色精确映射：待审核黄底、失败红底、已完成绿底 |
| `frontend/src/App.tsx` | 修改 | 导航当前页高亮、整体容器宽度 |

---

### Task 1: PipelineSidebar 步骤条色彩重构

**Files:**
- Modify: `frontend/src/components/PipelineSidebar.tsx`

**Mockup 参考（`all-layouts.html` 方案 A 左侧条）：**
- 已完成：蓝底 `#0969da` + 白字 + 白色 ✓ 圆圈
- 待审核（当前激活）：黄底 `#e8b931` + 黑字 + 白色 ! 圆圈 + 加粗
- 待执行：灰字 + 灰色边框圆圈
- 顶部标题：小写灰色，显示 Job ID 和产品名

- [ ] **Step 1: 添加 jobInfo prop 并在顶部显示**

```tsx
// 在 Props interface 中添加：
interface Props {
  currentPhase: Phase;
  completedPhases: Phase[];
  onStepClick: (key: string) => void;
  activeStepKey: string;
  jobInfo?: string;  // e.g. "Job #003 羊肚菌"
}
```

在 return 开头，`"流水线步骤"` 标题之前添加：
```tsx
{jobInfo && (
  <div className="text-xs font-semibold text-gray-500 mb-3">{jobInfo}</div>
)}
```

- [ ] **Step 2: 替换步骤条 button 的 className**

将当前 (line 33-41) 替换为：
```tsx
className={`flex items-center gap-1.5 w-full text-left px-1.5 py-1.5 rounded-md mb-0.5 text-xs transition-colors ${
  active
    ? isReview
      ? "bg-[#e8b931] text-[#1e2327] font-semibold"
      : "bg-[#0969da] text-white"
    : done
    ? "bg-[#0969da] text-white"
    : "text-[#59636e]"
}`}
```

- [ ] **Step 3: 替换步骤圆圈 span 的 className**

将当前 (line 43-52) 替换为：
```tsx
className={`w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] flex-shrink-0 ${
  done
    ? "bg-white text-[#0969da] font-bold"
    : active
    ? "bg-white text-[#1e2327] font-bold"
    : "border-1.5 border-[#59636e] text-[#59636e]"
}`}
```

- [ ] **Step 4: 添加底部操作按钮区**

在步骤列表结束后（`</div>` 之前最后添加）：
```tsx
<div className="mt-4 pt-3 border-t border-gray-200">
  <button className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md mb-1 transition-colors">
    &#9208; 暂停
  </button>
  <button className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md mb-1 transition-colors">
    &#8634; 重试当前
  </button>
  <button className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md transition-colors">
    &#128203; 查看日志
  </button>
</div>
```

- [ ] **Step 5: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc -b
```

Expected: 0 errors

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/PipelineSidebar.tsx
git commit -m "style: PipelineSidebar mockup 色彩 — 蓝底完成态 + 黄底审核高亮"
```

---

### Task 2: ScriptPreview 脚本卡片视觉适配

**Files:**
- Modify: `frontend/src/components/ScriptPreview.tsx`

**Mockup 参考：** 脚本灰底区域 + 质检结果横排绿/红

- [ ] **Step 1: 替换脚本预览卡片样式**

将当前 (line 20-23) 的 h3 + div 替换为：
```tsx
<div>
  <div className="text-sm font-semibold mb-2">口播脚本</div>
  <div className="bg-white border border-[#393f46] rounded-lg p-4 mb-3 text-sm leading-relaxed min-h-[60px]">
    {script || "暂无脚本"}
  </div>
```

- [ ] **Step 2: 替换质检结果区域**

将当前 checks 区域 (line 24-48) 替换为：
```tsx
{checks && (
  <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs mb-4">
    <span className={checks.length >= 150 && checks.length <= 200 ? "text-[#1a7f37]" : "text-[#d1242f]"}>
      字数: {checks.length} {checks.length >= 150 && checks.length <= 200 ? "\u2713" : "\u2717"}
    </span>
    <span className={checks.brand_name_count >= 1 ? "text-[#1a7f37]" : "text-[#d1242f]"}>
      品牌"滋元堂": {checks.brand_name_count}次
    </span>
    <span className={checks.product_name_count >= 1 ? "text-[#1a7f37]" : "text-[#d1242f]"}>
      品名: {checks.product_name_count}次
    </span>
    <span className={checks.has_safety_warning ? "text-[#1a7f37]" : "text-[#d1242f]"}>
      充分烹熟: {checks.has_safety_warning ? "\u2713" : "\u2717"}
    </span>
    <span className={!checks.has_emoji ? "text-[#1a7f37]" : "text-[#d1242f]"}>
      禁emoji: {!checks.has_emoji ? "\u2713" : "\u2717"}
    </span>
    {checks.forbidden_terms.length > 0 && (
      <span className="text-[#d1242f]">禁词: {checks.forbidden_terms.join(", ")}</span>
    )}
  </div>
)}
```

- [ ] **Step 3: 替换按钮区域**

将当前 button 区域 (line 50-69) 替换为：
```tsx
<div className="flex gap-1.5 flex-wrap">
  <button
    className="bg-[#0969da] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
    onClick={onApprove}
  >
    {"\u2713"} 通过
  </button>
  <button
    className="bg-[#d1242f] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
    onClick={onReject}
  >
    {"\u2717"} 打回
  </button>
  <button
    className="bg-white border border-[#393f46] px-4 py-2 rounded-md text-xs hover:bg-gray-50 transition-all"
    onClick={onRegenerate}
  >
    {"\U0001F504"} 重生成脚本
  </button>
</div>
```

- [ ] **Step 4: 验证**

```bash
cd frontend && npx tsc -b
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/ScriptPreview.tsx
git commit -m "style: ScriptPreview 白卡片脚本 + 绿/红质检 + 紧凑按钮"
```

---

### Task 3: JobPipeline 详情区 + 底部操作栏整合

**Files:**
- Modify: `frontend/src/pages/JobPipeline.tsx`

**变更：**
1. 步骤标题带步骤号和状态（如 "③ 脚本审核 — 待审核"）
2. 详情区背景灰底
3. 顶部传递 jobInfo 给 PipelineSidebar
4. 移除页面底部的操作按钮（移到 PipelineSidebar 内）

- [ ] **Step 1: 传递 jobInfo 到 PipelineSidebar**

找到 `<PipelineSidebar ... />` 调用，添加 prop：
```tsx
<PipelineSidebar
  currentPhase={job.phase}
  completedPhases={[]}
  onStepClick={(key) => setActiveStepKey(key)}
  activeStepKey={activeStepKey}
  jobInfo={job.product ? `${job.job_id} ${job.product}` : job.job_id}
/>
```

- [ ] **Step 2: 给详情区外层加灰底**

将 `<div className="flex-1 p-5">` 替换为：
```tsx
<div className="flex-1 p-5 bg-[#eff2f5]">
```

- [ ] **Step 3: 移除底部全局操作按钮**

删除 JobPipeline 底部的暂停/重试/日志按钮（移到 PipelineSidebar 内部了）。
删除 JSX 中以下代码：
```tsx
<div className="flex gap-2 mt-4">
  <button ...>⏸ 暂停</button>
  <button ...>🔄 重试当前</button>
  <button ...>📋 查看日志</button>
</div>
```

- [ ] **Step 4: 验证**

```bash
cd frontend && npx tsc -b
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/JobPipeline.tsx
git commit -m "style: JobPipeline 详情区灰底 + jobInfo 传参 + 操作按钮移入侧边栏"
```

---

### Task 4: ProjectWorkbench 三区卡片化

**Files:**
- Modify: `frontend/src/pages/ProjectWorkbench.tsx`
- Modify: `frontend/src/components/FileDropzone.tsx`

- [ ] **Step 1: 创建 Job 区域标题样式**

将 `<h2 className="font-semibold mb-4">创建新 Job</h2>` 替换为：
```tsx
<h2 className="text-[15px] font-semibold mb-3.5">创建新 Job</h2>
```

- [ ] **Step 2: 产品选择标签样式**

将 "产品" label 和 "目标平台" label 统一为 mockup 规格：
```tsx
<label className="grid gap-1.5 text-xs text-[#59636e] min-w-[200px]">
  产品选择
  <select ...>
```
将 `<span className="text-xs text-gray-500">目标平台</span>` 替换为：
```tsx
<span className="text-xs text-[#59636e]">目标平台</span>
```

- [ ] **Step 3: FileDropzone 背景改灰**

修改 `FileDropzone.tsx` 中默认状态的背景：
将 className 中的 `bg-gray-50` 替换为 `bg-[#eff2f5]`
将 `border-gray-300` 替换为 `border-[#393f46]`

- [ ] **Step 4: 创建按钮样式**

将 创建按钮 替换为：
```tsx
<button
  className="bg-[#d1242f] text-white border-none px-8 py-3 rounded-lg text-[15px] font-semibold hover:brightness-110 transition-all h-fit"
  onClick={handleCreateJob}
>
  创建并开始生产
</button>
```

- [ ] **Step 5: Tab 按钮样式**

将 Job 列表/排期池 tab 的激活态颜色改为 `#0969da`：
```tsx
className={`pb-2 text-sm font-medium transition-colors ${
  tab === "jobs"
    ? "border-b-2 border-[#0969da] text-[#0969da]"
    : "text-[#59636e] hover:text-gray-700"
}`}
```

- [ ] **Step 6: 验证**

```bash
cd frontend && npx tsc -b
```

- [ ] **Step 7: 提交**

```bash
git add frontend/src/pages/ProjectWorkbench.tsx frontend/src/components/FileDropzone.tsx
git commit -m "style: ProjectWorkbench + FileDropzone 色彩对齐 mockup"
```

---

### Task 5: JobTable + AssetCard 视觉重做

**Files:**
- Modify: `frontend/src/components/JobTable.tsx`
- Modify: `frontend/src/components/AssetCard.tsx`
- Modify: `frontend/src/components/ScheduleTable.tsx`

**JobTable 变更：添加"进度"列**

- [ ] **Step 1: 重写 JobTable**

```tsx
import { useNavigate } from "react-router-dom";
import type { JobSummary } from "../types";
import StatusBadge from "./StatusBadge";

interface Props {
  jobs: JobSummary[];
  onRetry: (jobId: string) => void;
}

export default function JobTable({ jobs, onRetry }: Props) {
  const navigate = useNavigate();

  if (jobs.length === 0) {
    return <p className="text-sm text-[#59636e] py-4">暂无 Job，创建一个开始吧</p>;
  }

  return (
    <table className="w-full border-collapse text-[13px]">
      <thead>
        <tr className="border-b border-[#393f46] text-left text-[#59636e]">
          <th className="py-2 px-2 font-medium">Job ID</th>
          <th className="py-2 px-2 font-medium">产品</th>
          <th className="py-2 px-2 font-medium">状态</th>
          <th className="py-2 px-2 font-medium">进度</th>
          <th className="py-2 px-2 font-medium">操作</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((j) => (
          <tr key={j.job_id} className="border-b border-[#eff2f5] hover:bg-gray-50">
            <td className="py-2.5 px-2 font-mono text-xs">{j.job_id}</td>
            <td className="py-2.5 px-2">{j.product}</td>
            <td className="py-2.5 px-2">
              <StatusBadge phase={j.phase} />
            </td>
            <td className="py-2.5 px-2 text-[#59636e]">
              {j.phase_index > 0 ? `${j.phase_index}/${j.phase_total}` : "—"}
            </td>
            <td className="py-2.5 px-2">
              {j.phase === "failed" ? (
                <button
                  className="text-[#0969da] hover:underline text-xs"
                  onClick={() => onRetry(j.job_id)}
                >
                  重试 &#8634;
                </button>
              ) : (
                <button
                  className="text-[#0969da] hover:underline text-xs"
                  onClick={() => navigate(`/jobs/${j.job_id}`)}
                >
                  查看 &rarr;
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: AssetCard 添加视频图标**

将 `<div className="h-24 bg-gray-100 ...">{/* 视频图标 */}</div>` 替换为：
```tsx
<div className="h-[90px] bg-[#eff2f5] flex items-center justify-center text-[28px]">
  {"\uD83C\uDFAC"}
</div>
```

卡片边框从 `border-gray-200` 改为 `border-[#eff2f5]`。

- [ ] **Step 3: ScheduleTable 状态标签色彩**

将 "已发布" 标签从 `bg-green-100 text-green-700` 改为：
```tsx
className={`px-2 py-0.5 rounded text-xs ${
  e.status === "published"
    ? "bg-[#e6f4ea] text-[#1a7f37]"
    : "bg-gray-100 text-gray-600"
}`}
```

- [ ] **Step 4: 验证**

```bash
cd frontend && npx tsc -b
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/JobTable.tsx frontend/src/components/AssetCard.tsx frontend/src/components/ScheduleTable.tsx
git commit -m "style: JobTable 进度列 + AssetCard 图标 + ScheduleTable 绿色已发布"
```

---

### Task 6: StatusBadge 精确色彩 + ProjectList 视觉收尾

**Files:**
- Modify: `frontend/src/components/StatusBadge.tsx`
- Modify: `frontend/src/pages/ProjectList.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: StatusBadge 颜色精确化**

将 `colorMap` 中的关键颜色替换为精确值：
```tsx
const colorMap: Record<string, string> = {
  queued: "bg-gray-100 text-gray-700",
  script_generating: "bg-[#e3f2fd] text-[#0969da]",
  tts_generating: "bg-[#e3f2fd] text-[#0969da]",
  subtitle_generating: "bg-[#e3f2fd] text-[#0969da]",
  asset_retrieving: "bg-[#e3f2fd] text-[#0969da]",
  video_rendering: "bg-[#e3f2fd] text-[#0969da]",
  schedule_writing: "bg-[#e3f2fd] text-[#0969da]",
  script_review: "bg-[#fff3cd] text-[#997404]",
  asset_review: "bg-[#fff3cd] text-[#997404]",
  final_review: "bg-[#fff3cd] text-[#997404]",
  completed: "bg-[#e6f4ea] text-[#1a7f37]",
  failed: "bg-[#ffe0e0] text-[#d1242f]",
  cancelled: "bg-gray-200 text-gray-500",
  paused: "bg-[#fff3e0] text-[#e65100]",
};
```

- [ ] **Step 2: ProjectList 表格标题行加灰底**

将 `<thead>` 内的 tr 添加背景：
```tsx
<tr className="bg-gray-50 border-b border-[#393f46] text-left text-[#59636e]">
```

- [ ] **Step 3: 空态图标放大**

```tsx
<div className="text-5xl mb-4">📂</div>
```

- [ ] **Step 4: App.tsx 导航当前页高亮 + 创建按钮样式**

NavLink 组件的 active 状态颜色改为：
```tsx
className={`px-3 py-2 rounded-xl text-sm font-medium transition-colors ${
  active
    ? "text-[#0969da] bg-[#eff2f5]"
    : "text-[#59636e] hover:text-gray-700 hover:bg-gray-50"
}`}
```

ProjectList 创建按钮颜色改为 mockup 红：
```tsx
className="bg-[#d1242f] text-white px-4 py-2 rounded-lg text-sm font-semibold hover:brightness-110 transition-all"
```

- [ ] **Step 5: 验证**

```bash
cd frontend && npx tsc -b
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/StatusBadge.tsx frontend/src/pages/ProjectList.tsx frontend/src/App.tsx
git commit -m "style: StatusBadge 精确色 + ProjectList/App 导航收尾"
```

---

### Task 7: 构建验证 + 浏览器集成测试

**Files:** 无新增

- [ ] **Step 1: TypeScript 编译**

```bash
cd frontend && npx tsc -b
```
Expected: 0 errors

- [ ] **Step 2: 生产构建**

```bash
cd frontend && npm run build
```
Expected: 构建成功，56+ 模块

- [ ] **Step 3: 后端测试无回归**

```bash
uv run pytest tests/ -q
```
Expected: 62 passed

- [ ] **Step 4: 启动 dev 服务器 + 浏览器验证三页面**

```bash
# Terminal 1
uv run python -m apps.control_plane

# Terminal 2
cd frontend && npm run dev

# 浏览器验证：
# - http://localhost:5173/ 项目列表页
# - http://localhost:5173/projects/:id 工作台
# - http://localhost:5173/jobs/:id 流水线详情
```

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "chore: 视觉适配构建验证通过"
```

---

## 实施顺序

```
Task 1 (PipelineSidebar)
  └── Task 2 (ScriptPreview)
        └── Task 3 (JobPipeline)
              └── Task 4 (ProjectWorkbench + FileDropzone)
                    └── Task 5 (JobTable + AssetCard + ScheduleTable)
                          └── Task 6 (StatusBadge + ProjectList + App)
                                └── Task 7 (构建验证)
```

全部 7 个任务，纯前端变更，可顺序执行，最后统一构建验证。
