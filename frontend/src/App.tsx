import { Routes, Route, Link } from "react-router-dom";
import ProjectList from "./pages/ProjectList";
import ProjectWorkbench from "./pages/ProjectWorkbench";
import ConfigPage from "./pages/ConfigPage";

export default function App() {
  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <nav className="flex items-center gap-3 pb-4 border-b mb-6">
        <Link to="/" className="text-blue-600 hover:text-blue-800 font-medium">
          项目列表
        </Link>
        <Link to="/config" className="text-blue-600 hover:text-blue-800 font-medium">
          系统配置
        </Link>
      </nav>
      <Routes>
        <Route path="/" element={<ProjectList />} />
        <Route path="/projects/:id" element={<ProjectWorkbench />} />
        <Route path="/jobs/:id" element={<div className="text-gray-500">流水线详情（施工中）</div>} />
        <Route path="/config" element={<ConfigPage />} />
      </Routes>
    </div>
  );
}
