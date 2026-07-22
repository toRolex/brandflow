import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
	base: "./",
	plugins: [react(), tailwindcss()],
	server: {
		host: true,
		port: 5173,
		proxy: {
			"/api": "http://127.0.0.1:17890",
			"/workers": "http://127.0.0.1:17890",
			"/workspace": "http://127.0.0.1:17890",
		},
	},
	build: {
		outDir: "dist",
	},
});
