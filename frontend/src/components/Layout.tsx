import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";
import ProductSelector from "./ProductSelector";

/* ------------------------------------------------------------------ */
/*  SVG Icons — 18x18, currentColor, stroke-width 1.5, round caps     */
/* ------------------------------------------------------------------ */

const IconGrid = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="1.5" y="1.5" width="6" height="6" rx="1" />
    <rect x="10.5" y="1.5" width="6" height="6" rx="1" />
    <rect x="1.5" y="10.5" width="6" height="6" rx="1" />
    <rect x="10.5" y="10.5" width="6" height="6" rx="1" />
  </svg>
);

const IconImage = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="1.5" y="2.5" width="15" height="13" rx="2" />
    <circle cx="5.5" cy="6.5" r="1.5" />
    <path d="M1.5 13.5l4-4 3 3 3-3 5 5" />
  </svg>
);

const IconGear = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="9" cy="9" r="2.5" />
    <path d="M9 1.5v1.5M9 15v1.5M3.7 3.7l1.06 1.06M13.24 13.24l1.06 1.06M1.5 9h1.5M15 9h1.5M3.7 14.3l1.06-1.06M13.24 4.76l1.06-1.06" />
  </svg>
);

const IconChart = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M3.5 14.5V9" />
    <path d="M9 14.5V3.5" />
    <path d="M14.5 14.5V7" />
  </svg>
);

const IconSun = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="9" cy="9" r="3.5" />
    <path d="M9 1v1.5M9 15.5V17M3.34 3.34l1.06 1.06M15.6 15.6l1.06 1.06M1 9h1.5M15.5 9H17M3.34 16.66l1.06-1.06M15.6 2.4l1.06-1.06" />
  </svg>
);

const IconMoon = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M15.5 10.5a6.5 6.5 0 0 1-8-8 6.5 6.5 0 1 0 8 8z" />
  </svg>
);

const IconExpand = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M7 1.5H1.5V7M11 16.5h5.5V11" />
  </svg>
);

const IconCollapse = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 18 18"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M1.5 7V1.5H7M16.5 11v5.5H11" />
  </svg>
);

/* ------------------------------------------------------------------ */
/*  Icon mapping – key -> ReactNode                                   */
/* ------------------------------------------------------------------ */

const ICON_MAP: Record<string, ReactNode> = {
  grid: <IconGrid />,
  image: <IconImage />,
  gear: <IconGear />,
  chart: <IconChart />,
};

const NAV_ITEMS = [
  { path: "/", label: "项目列表", icon: "grid" },
  { path: "/assets", label: "素材库", icon: "image" },
  { path: "/config", label: "系统配置", icon: "gear" },
  { path: "/analytics", label: "数据追踪", icon: "chart" },
];

const CONFIG_ITEMS = [
  { path: "/config", label: "Provider 配置" },
  { path: "/system/config/product", label: "产品配置" },
  { path: "/system/config/templates", label: "脚本模板" },
  { path: "/system/config/quality", label: "质检规则" },
  { path: "/system/config/knowledge", label: "知识库" },
  { path: "/tts-config", label: "TTS 配置" },
  { path: "/tts-monitor", label: "TTS 监控" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { theme, layout, toggleTheme, toggleLayout } = useTheme();
  const active = location.pathname;

  const inSystemConfig =
    active.startsWith("/system/config/") ||
    active === "/config" ||
    active === "/tts-config" ||
    active === "/tts-monitor";

  return (
    <div
      className="flex h-screen"
      style={{ background: "var(--bg-page)", color: "var(--text-primary)" }}
    >
      {/* Left sidebar */}
      <nav
        className="flex flex-col w-12 border-r py-2 items-center gap-1 shrink-0"
        style={{
          background: "var(--bg-nav)",
          borderColor: "var(--border-default)",
        }}
      >
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.path === "/" ? active === "/" : active.startsWith(item.path);
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`w-9 h-9 flex items-center justify-center rounded-md text-sm transition-colors ${
                isActive ? "" : "hover:bg-[var(--color-steel)]"
              }`}
              title={item.label}
              style={{
                background: isActive
                  ? "var(--color-electric-blue-muted)"
                  : undefined,
                color: isActive
                  ? "var(--color-electric-blue)"
                  : "var(--text-secondary)",
              }}
            >
              {ICON_MAP[item.icon]}
            </Link>
          );
        })}
        {/* Bottom controls */}
        <div className="mt-auto flex flex-col items-center gap-1">
          <button
            onClick={toggleLayout}
            className="w-9 h-9 flex items-center justify-center rounded-md transition-colors hover:bg-[var(--color-steel)]"
            style={{ color: "var(--text-secondary)" }}
            title={layout === "normal" ? "紧凑模式" : "正常模式"}
          >
            {layout === "normal" ? <IconCollapse /> : <IconExpand />}
          </button>
          <button
            onClick={toggleTheme}
            className="w-9 h-9 flex items-center justify-center rounded-md transition-colors hover:bg-[var(--color-steel)]"
            style={{ color: "var(--text-secondary)" }}
            title={theme === "light" ? "暗色模式" : "亮色模式"}
          >
            {theme === "light" ? <IconMoon /> : <IconSun />}
          </button>
        </div>
      </nav>

      {/* Right content area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top header */}
        <header
          className="flex items-center justify-between px-4 py-2 border-b shrink-0"
          style={{
            background: "var(--bg-header)",
            borderColor: "var(--border-default)",
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="text-sm font-semibold"
              style={{ color: "var(--text-primary)" }}
            >
              Brandflow
            </span>
            {inSystemConfig && (
              <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                / 系统配置
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <ProductSelector />
          </div>
        </header>

        {/* Content area with optional sub-nav */}
        <div className="flex-1 flex overflow-hidden">
          {inSystemConfig && <SystemConfigSidebar />}
          <main
            className="flex-1 overflow-auto"
            style={{ padding: "var(--spacing-lg)" }}
          >
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}

function SystemConfigSidebar() {
  const location = useLocation();
  const active = location.pathname;
  return (
    <nav
      className="w-44 border-r shrink-0 overflow-y-auto py-2"
      style={{
        background: "var(--bg-nav)",
        borderColor: "var(--border-default)",
      }}
    >
      {CONFIG_ITEMS.map((item) => {
        const isActive =
          item.path === "/config"
            ? active === "/config"
            : active.startsWith(item.path);
        return (
          <Link
            key={item.path}
            to={item.path}
            className="block px-3 py-1.5 text-sm rounded-md mx-1 transition-colors"
            style={{
              background: isActive ? "var(--bg-nav-active)" : "transparent",
              color: isActive
                ? "var(--text-nav-active)"
                : "var(--text-secondary)",
            }}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
