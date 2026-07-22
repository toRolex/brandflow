import type { ProviderConfig, ProviderOptions } from "../types/config";
import { request } from "./core";

export const getConfig = () => request<ProviderConfig>("/api/config");

export const getConfigOptions = () =>
	request<ProviderOptions>("/api/config/options");

export const saveConfig = (payload: ProviderConfig) =>
	request<ProviderConfig>("/api/config", {
		method: "PUT",
		body: JSON.stringify(payload),
	});
