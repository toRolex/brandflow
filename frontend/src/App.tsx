import { Route, Routes } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import { ProductProvider } from "./ProductContext";
import AnalyticsPage from "./pages/AnalyticsPage";
import ConfigPage from "./pages/ConfigPage";
import JobPipeline from "./pages/JobPipeline";
import KnowledgeBasePage from "./pages/KnowledgeBasePage";
import ProductConfigForm from "./pages/ProductConfigForm";
import ProjectList from "./pages/ProjectList";
import ProjectWorkbench from "./pages/ProjectWorkbench";
import QualityRulesForm from "./pages/QualityRulesForm";
import ScriptTemplateEditor from "./pages/ScriptTemplateEditor";
import ScriptTemplateList from "./pages/ScriptTemplateList";
import SmartAssetLibrary from "./pages/SmartAssetLibrary";
import TtsConfig from "./pages/TTSConfig";

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
						<Route
							path="/system/config/product"
							element={<ProductConfigForm />}
						/>
						<Route
							path="/system/config/templates"
							element={<ScriptTemplateList />}
						/>
						<Route
							path="/system/config/templates/:id"
							element={<ScriptTemplateEditor />}
						/>
						<Route
							path="/system/config/quality"
							element={<QualityRulesForm />}
						/>
						<Route
							path="/system/config/knowledge"
							element={<KnowledgeBasePage />}
						/>
						<Route path="/tts-config" element={<TtsConfig />} />
						<Route path="/analytics" element={<AnalyticsPage />} />
					</Routes>
				</Layout>
			</ProductProvider>
		</ErrorBoundary>
	);
}
