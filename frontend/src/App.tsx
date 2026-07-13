import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import { ProductProvider } from "./ProductContext";
import ProjectList from "./pages/ProjectList";
import ProjectWorkbench from "./pages/ProjectWorkbench";
import JobPipeline from "./pages/JobPipeline";
import SmartAssetLibrary from "./pages/SmartAssetLibrary";
import ConfigPage from "./pages/ConfigPage";
import ProductConfigForm from "./pages/ProductConfigForm";
import ScriptTemplateList from "./pages/ScriptTemplateList";
import ScriptTemplateEditor from "./pages/ScriptTemplateEditor";
import QualityRulesForm from "./pages/QualityRulesForm";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";
import TTSConfig from "./pages/TTSConfig";
import TTSMonitor from "./pages/TTSMonitor";
import AnalyticsPage from "./pages/AnalyticsPage";

export default function App() {
  return (
    <ErrorBoundary>
      <ProductProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<ProjectList />} />
            <Route path="/projects/:id" element={<ProjectWorkbench />} />
            <Route path="/jobs/:id" element={<JobPipeline />} />
            <Route path="/assets" element={<SmartAssetLibrary />} />
            <Route path="/config" element={<ConfigPage />} />
            <Route path="/system/config/product" element={<ProductConfigForm />} />
            <Route path="/system/config/templates" element={<ScriptTemplateList />} />
            <Route path="/system/config/templates/:id" element={<ScriptTemplateEditor />} />
            <Route path="/system/config/quality" element={<QualityRulesForm />} />
            <Route path="/system/config/knowledge" element={<KnowledgeBasePage />} />
            <Route path="/tts-config" element={<TTSConfig />} />
            <Route path="/tts-monitor" element={<TTSMonitor />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
          </Routes>
        </Layout>
      </ProductProvider>
    </ErrorBoundary>
  );
}
