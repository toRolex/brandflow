---
name: Brandflow
description: 短视频自动化生产控制面 — 精密仪器式的运营工作台
colors:
  electric-blue: "oklch(62% 0.19 252)"
  electric-blue-hover: "oklch(68% 0.19 252)"
  electric-blue-muted: "oklch(62% 0.19 252 / 0.12)"
  signal-green: "oklch(58% 0.17 145)"
  signal-green-muted: "oklch(58% 0.17 145 / 0.12)"
  alert-red: "oklch(55% 0.21 20)"
  alert-red-muted: "oklch(55% 0.21 20 / 0.10)"
  caution-amber: "oklch(65% 0.14 75)"
  caution-amber-muted: "oklch(65% 0.14 75 / 0.12)"
  void: "oklch(14% 0.006 258)"
  obsidian: "oklch(18% 0.006 258)"
  obsidian-raised: "oklch(22% 0.006 258)"
  steel: "oklch(28% 0.006 258)"
  steel-strong: "oklch(35% 0.006 258)"
  chalk: "oklch(97% 0.003 258)"
  frost: "oklch(100% 0 0)"
  mist: "oklch(88% 0.004 258)"
  graphite: "oklch(18% 0.004 258)"
  slate: "oklch(40% 0.006 258)"
  fog: "oklch(55% 0.006 258)"
  white-smoke: "oklch(92% 0 0)"
typography:
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.01em"
  label:
    fontFamily: "'SF Mono', 'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Noto Sans SC', monospace"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.02em"
rounded:
  sm: "4px"
  md: "6px"
  lg: "10px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  "2xl": "32px"
components:
  button-primary:
    backgroundColor: "{colors.electric-blue}"
    textColor: "{colors.white-smoke}"
    rounded: "{rounded.md}"
    padding: "8px 20px"
  button-primary-hover:
    backgroundColor: "{colors.electric-blue-hover}"
  button-danger:
    backgroundColor: "{colors.alert-red}"
    textColor: "{colors.white-smoke}"
    rounded: "{rounded.md}"
    padding: "8px 20px"
  button-ghost:
    backgroundColor: transparent
    textColor: "{colors.slate}"
    rounded: "{rounded.md}"
    padding: "6px 14px"
  badge-default:
    backgroundColor: "{colors.electric-blue-muted}"
    textColor: "{colors.electric-blue}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  badge-success:
    backgroundColor: "{colors.signal-green-muted}"
    textColor: "{colors.signal-green}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  badge-warning:
    backgroundColor: "{colors.caution-amber-muted}"
    textColor: "{colors.caution-amber}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  badge-danger:
    backgroundColor: "{colors.alert-red-muted}"
    textColor: "{colors.alert-red}"
    rounded: "{rounded.sm}"
    padding: "2px 8px"
  input-field:
    backgroundColor: "{colors.frost}"
    textColor: "{colors.graphite}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  card:
    backgroundColor: "{colors.frost}"
    rounded: "{rounded.lg}"
    padding: "20px"
---

# Design System: Brandflow

## 1. Overview

**Creative North Star: "The Precision Instrument"**

Brandflow 的设计系统像一个精密仪器——每个像素都经过计算，每个交互都经过校准。它不是装饰性的，而是功能性的：颜色传递状态，间距传递关系，动效传递因果。暗色模式是一等公民，因为运营人员每天盯着屏幕数小时；亮色模式同样精心打磨，用于日间混合光环境。

这个系统的美学来源于 Vercel 的几何精确性和 Linear 的静默精致感。它拒绝 AI 生成设计的全部套路：没有奶油色暖调背景，没有玻璃态默认风格，没有渐变文字，没有侧边彩条装饰。冷调中性色底盘承载一个高饱和蓝色 accent，绿色和红色分别承担成功和危险的信号角色——不多不少，刚好够用。

**Key Characteristics:**
- 暗色优先：深色近黑底盘（`void` / `obsidian`），减轻长时间盯屏疲劳
- 单 accent 原则：一个电光蓝（`electric-blue`）覆盖 ≤10% 的屏幕面积
- 系统字体栈：原生渲染速度，零布局偏移，操作系统的熟悉感
- 精密间距刻度：4px 基准网格，6 级间距（`xs` 到 `2xl`）
- 信号色彩：绿/红/琥珀仅用于状态传递，不用于装饰
- 克制动效：状态转换 150ms、hover 微反馈、入场编排，全部尊重 reduced-motion

## 2. Colors

冷调中性底盘 + 一个电光蓝 accent + 三个信号色。暗色模式是色彩系统的设计原点。

### Primary
- **Electric Blue** (`oklch(62% 0.19 252)`): 唯一的品牌 accent。用于主按钮、链接、选中态、聚焦环。在任一屏幕上占比不超过 10%——稀有性就是它的力量。
- **Electric Blue Hover** (`oklch(68% 0.19 252)`): hover/按下态的提亮变体。
- **Electric Blue Muted** (`oklch(62% 0.19 252 / 0.12)`): accent 的低透明度底版，用于选中背景、tag 底色。

### Neutral (Dark)
- **Void** (`oklch(14% 0.006 258)`): 暗色页面底色。近黑冷调，微微偏向蓝轴，避免纯黑的生硬感。
- **Obsidian** (`oklch(18% 0.006 258)`): 暗色卡片、导航、表头的表面色。比 `void` 亮 4%，刚好可感知的层次分离。
- **Obsidian Raised** (`oklch(22% 0.006 258)`): hover 抬升态、下拉面板、弹出层。
- **Steel** (`oklch(28% 0.006 258)`): 暗色默认边框。可见但不喧宾夺主。
- **Steel Strong** (`oklch(35% 0.006 258)`): 暗色强调边框（输入框聚焦、分割线）。

### Neutral (Light)
- **Chalk** (`oklch(97% 0.003 258)`): 亮色页面底色。冷调近白，chroma 极低，避免暖调奶油感。
- **Frost** (`oklch(100% 0 0)`): 亮色卡片、导航、输入框。纯白，最大对比度。
- **Mist** (`oklch(88% 0.004 258)`): 亮色默认边框。
- **Graphite** (`oklch(18% 0.004 258)`): 亮色主文本。接近黑色但不刺眼。
- **Slate** (`oklch(40% 0.006 258)`): 亮色次要文本。与背景对比度 ≥ 4.5:1。
- **Fog** (`oklch(55% 0.006 258)`): 亮色三级文本/占位符。与背景对比度 ≥ 4.5:1。
- **White Smoke** (`oklch(92% 0 0)`): 暗色主文本。近白，柔和不刺眼。

### Semantic
- **Signal Green** (`oklch(58% 0.17 145)`): 成功/完成。清晰、干净、不像荧光绿的绿色。
- **Alert Red** (`oklch(55% 0.21 20)`): 危险/错误/删除。高可见性，但不刺眼。
- **Caution Amber** (`oklch(65% 0.14 75)`): 警告/审核中/待处理。温暖的注意信号。

### Named Rules
**The One Accent Rule.** `electric-blue` 在任一屏幕上覆盖不超过 10% 的面积。它不是装饰色，而是功能信号——链接、选中、主操作。滥用 accent 会稀释它的信号价值。

**The Cold Neutral Rule.** 所有中性色（`void`、`obsidian`、`chalk`、`steel`）的色相统一偏蓝轴（255-258°），chroma ≤ 0.008。禁止暖调中性色（色相 40-100°），那是 AI 生成设计的默认选择。

**The Signal-Only Rule.** `signal-green`、`alert-red`、`caution-amber` 仅用于状态传递。禁止将它们用作装饰色、图表配色或 brand accent。绿色按钮表示"安全/完成"，不是"购买"。

## 3. Typography

**Body Font:** System sans stack — `-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif`
**Label/Mono Font:** System mono stack — `'SF Mono', 'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Noto Sans SC', monospace`

**Character:** 不引入自定义字体。系统字体栈提供原生渲染速度、零 FOUT、以及操作系统级的熟悉感。精密感来自间距刻度、字重对比和信息层级，不来自字体本身。中文字体回退链确保简繁体均有合适回退。

### Hierarchy
- **Title** (600, 1.125rem / 18px, 1.35): 页面标题、卡片标题。使用 `-apple-system` 的 Display 变体以获得更紧致的间距。
- **Body** (400, 0.875rem / 14px, 1.5): 正文、表格内容、表单标签。行高 1.5 保证中文舒适阅读。行长上限 75ch。
- **Label** (500, 0.75rem / 12px, 1.3, letter-spacing: 0.02em): Badge、tag、状态标签、表头。等宽字体提供数据对齐的精确感。
- **Small** (400, 0.8125rem / 13px, 1.45): 辅助说明、时间戳、次要元数据。

### Named Rules
**The System Font Rule.** 始终使用系统字体栈。不引入 Web 字体——它们的网络开销和布局偏移与"精密仪器"的理念相悖。自定义字体的缺失本身就是一种风格选择。

**The Mono Label Rule.** 所有状态标签、badge、数据指标使用等宽字体。固定宽度让同类元素在扫描时对齐，强化"精密仪器"的视觉节奏。

## 4. Elevation

精密仪器使用轻阴影作为深度线索，但默认是平的。表面靠背景色差（`void` → `obsidian` → `obsidian-raised`）而非投影来区分层级。阴影只在需要引起注意的浮层上出现——下拉面板、弹出框、模态框。

### Shadow Vocabulary
- **Ambient Low** (`0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)`): 卡片默认阴影。几乎不可见，仅提供微弱的物理感。
- **Elevated** (`0 4px 16px rgba(0,0,0,0.12), 0 2px 4px rgba(0,0,0,0.06)`): 下拉面板、弹出层。清晰但克制的抬升感。
- **Modal** (`0 12px 32px rgba(0,0,0,0.18), 0 4px 8px rgba(0,0,0,0.08)`): 模态框、抽屉。最重的阴影，标记最高的 z-index 层级。

暗色模式下阴影仍为黑色——半透明黑色在暗色背景上叠加形成深度，效果微妙但有效。

### Z-Index Scale
`dropdown (100) → sticky (200) → modal-backdrop (300) → modal (400) → toast (500) → tooltip (600)`

### Named Rules
**The Flat-By-Default Rule.** 表面在静止状态下是平的。阴影只在浮层（dropdown、modal、tooltip）上出现。卡片、导航、输入框靠背景色差和 1px 边框区分层级。

**The Calculated Z-Index Rule.** 禁止使用任意 z-index 值（如 999、9999）。所有层级从语义刻度中选取，且必须在 0-600 范围内。

## 5. Components

### Buttons
精密仪器的按钮是清晰、果断的交互点。三个变体，没有多余的。
- **Shape:** 6px 圆角（`--radius-md`），直角过冷，大圆角过软。
- **Primary:** `electric-blue` 实心底 + 白色文本。padding: 8px 20px。150ms 过渡到 `electric-blue-hover`。
- **Danger:** `alert-red` 实心底 + 白色文本。结构与 Primary 一致，颜色承载语义。
- **Ghost:** 透明底 + `slate` 文本。hover 时底色变为 `electric-blue-muted`。
- **Focus:** 所有按钮使用 `electric-blue` 的 2px 聚焦环，offset 2px。

### Status Badges
标签是数据扫描的锚点。等宽字体 + 紧凑 padding 让同类元素对齐。
- **Shape:** 4px 圆角（`--radius-sm`），padding: 2px 8px。
- **Default:** `electric-blue-muted` 底 + `electric-blue` 文本。
- **Success:** `signal-green-muted` 底 + `signal-green` 文本。
- **Warning:** `caution-amber-muted` 底 + `caution-amber` 文本。
- **Danger:** `alert-red-muted` 底 + `alert-red` 文本。

### Cards / Containers
- **Shape:** 10px 圆角（`--radius-lg`），1px `mist` 边框。
- **Background:** `frost`（亮色）/ `obsidian`（暗色）。
- **Shadow:** `Ambient Low` 阴影。
- **Padding:** 20px（`--spacing-lg` 的 1.25×）。

### Inputs / Fields
- **Style:** 1px `mist` 边框，`frost` 底色，6px 圆角。padding: 8px 12px。
- **Focus:** 边框变为 `electric-blue`，外圈 2px `electric-blue-muted` 光晕。150ms 过渡。
- **Placeholder:** `fog`，确保与背景对比度 ≥ 4.5:1。

### Navigation
双层侧边栏结构：左侧图标导航（48px 宽）+ 二级文本导航（176px 宽）。
- **Icon Nav:** `obsidian` 底色。选中态：`electric-blue-muted` 底 + `electric-blue` 图标色。hover 态：`steel` 底色。
- **Text Nav:** `obsidian` 底色，1px `steel` 右边框。选中态：`electric-blue-muted` 底 + `electric-blue` 文本。字体：body stack，600 字重。

### Tables
- **Header:** `obsidian` 底色，`label` 字体（等宽，12px，500 字重），文本色 `slate`。
- **Row:** 1px `steel` 下边框。hover 态底色切换为 `obsidian-raised`。
- **Cell Padding:** 12px 16px（垂直 水平）。

## 6. Do's and Don'ts

### Do:
- **Do** 使用 `electric-blue` 作为唯一的品牌 accent，覆盖面积 ≤10%
- **Do** 暗色模式作为设计的默认参照，亮色模式同等质量
- **Do** 使用系统字体栈——不引入 Web 字体
- **Do** 所有动效响应 `prefers-reduced-motion: reduce`
- **Do** 使用语义色（绿/红/琥珀）仅传递状态，不用于装饰
- **Do** 使用 OKLCH 书写所有颜色值，保持色彩一致性
- **Do** 1px 边框 + 背景色差作为默认层级区分方式

### Don't:
- **Don't** 使用暖调中性色背景（奶油色/沙色/米色/纸张色），那是 AI 生成设计的默认选择
- **Don't** 使用 `border-left` 或 `border-right` 大于 1px 的彩色侧边条装饰
- **Don't** 使用 `background-clip: text` 渐变文字
- **Don't** 使用玻璃态/毛玻璃效果作为默认风格
- **Don't** 使用 tiny uppercase eyebrow 文字（"ABOUT" / "PROCESS"）在每个 section 上方
- **Don't** 使用 01/02/03 数字编号作为 section 的默认脚手架
- **Don't** 使用千篇一律的等大卡片网格（icon + heading + text）
- **Don't** 使用任意 z-index 值（999、9999）——从语义刻度选取
- **Don't** 使用 `signal-green` 或 `alert-red` 作为装饰色或图表配色
