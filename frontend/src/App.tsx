import { Routes, Route, Link, useLocation } from "react-router-dom";
import ProjectList from "./pages/ProjectList";
import ProjectWorkbench from "./pages/ProjectWorkbench";
import JobPipeline from "./pages/JobPipeline";
import ConfigPage from "./pages/ConfigPage";
import TTSConfig from "./pages/TTSConfig";
import TTSMonitor from "./pages/TTSMonitor";
import ProductConfigForm from "./pages/ProductConfigForm";
import ScriptTemplateList from "./pages/ScriptTemplateList";
import ScriptTemplateEditor from "./pages/ScriptTemplateEditor";
import AnalyticsPage from "./pages/AnalyticsPage";
import ErrorBoundary from "./components/ErrorBoundary";

function NavLink({ to, label }: { to: string; label: string }) {
  const location = useLocation();
  const active = location.pathname === to;
  return (
    <Link
      to={to}
      className={`px-3 py-2 rounded-xl text-sm font-medium transition-colors ${
        active
          ? "text-[#0969da] bg-[#eff2f5]"
          : "text-[#59636e] hover:text-gray-700 hover:bg-gray-50"
      }`}
    >
      {label}
    </Link>
  );
}

export default function App() {
  return (
    <div className="max-w-6xl mx-auto px-4 py-4">
      <nav className="flex items-center gap-2 pb-3 border-b border-gray-200 mb-6">
        <NavLink to="/" label="项目列表" />
        <NavLink to="/config" label="系统配置" />
        <NavLink to="/system/config/product" label="产品配置" />
        <NavLink to="/system/config/templates" label="脚本模板" />
        <NavLink to="/tts-config" label="TTS 配置" />
        <NavLink to="/tts-monitor" label="TTS 监控" />
        <NavLink to="/analytics" label="数据追踪" />
      </nav>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<ProjectList />} />
          <Route path="/projects/:id" element={<ProjectWorkbench />} />
          <Route path="/jobs/:id" element={<JobPipeline />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/system/config/product" element={<ProductConfigForm />} />
          <Route path="/system/config/templates" element={<ScriptTemplateList />} />
          <Route path="/system/config/templates/:id" element={<ScriptTemplateEditor />} />
          <Route path="/tts-config" element={<TTSConfig />} />
          <Route path="/tts-monitor" element={<TTSMonitor />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Routes>
      </ErrorBoundary>
    </div>
  );
}
