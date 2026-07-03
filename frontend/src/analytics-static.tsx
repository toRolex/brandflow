import AnalyticsStaticPage from "./pages/AnalyticsStaticPage";
import { createRoot } from "react-dom/client";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<AnalyticsStaticPage />);
}
