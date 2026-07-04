import { type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";
import ProductSelector from "./ProductSelector";

const NAV_ITEMS = [
  { path: "/", label: "项目列表", icon: "📋" },
  { path: "/assets", label: "素材库", icon: "🖼" },
  { path: "/config", label: "系统配置", icon: "⚙" },
  { path: "/analytics", label: "数据追踪", icon: "📊" },
];

const CONFIG_ITEMS = [
  { path: "/config", label: "Provider 配置" },
  { path: "/system/config/product", label: "产品配置" },
  { path: "/system/config/templates", label: "脚本模板" },
  { path: "/system/config/categories", label: "素材分类" },
  { path: "/system/config/quality", label: "质检规则" },
  { path: "/system/config/knowledge", label: "知识库" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { theme, layout, toggleTheme, toggleLayout } = useTheme();
  const active = location.pathname;

  const inSystemConfig =
    active.startsWith("/system/config/") || active === "/config";

  return (
    <div
      className="flex h-screen"
      style={{ background: "var(--bg-page)", color: "var(--text-primary)" }}
    >
      {/* Left sidebar */}
      <nav
        className="flex flex-col w-13 border-r py-2 items-center gap-1 shrink-0"
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
              className="w-9 h-9 flex items-center justify-center rounded-md text-sm transition-colors"
              title={item.label}
              style={{
                background: isActive ? "var(--bg-nav-active)" : "transparent",
                color: isActive
                  ? "var(--text-nav-active)"
                  : "var(--text-secondary)",
              }}
            >
              {item.icon}
            </Link>
          );
        })}
        {/* Bottom controls */}
        <div className="mt-auto flex flex-col items-center gap-1">
          <button
            onClick={toggleLayout}
            className="w-9 h-9 flex items-center justify-center rounded-md text-xs"
            style={{ color: "var(--text-tertiary)" }}
            title={layout === "normal" ? "紧凑模式" : "正常模式"}
          >
            {layout === "normal" ? "⊟" : "⊞"}
          </button>
          <button
            onClick={toggleTheme}
            className="w-9 h-9 flex items-center justify-center rounded-md text-sm"
            style={{ color: "var(--text-tertiary)" }}
            title={theme === "light" ? "暗色模式" : "亮色模式"}
          >
            {theme === "light" ? "🌙" : "☀️"}
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
