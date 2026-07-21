import { request } from "./core";
import type { ProductConfig } from "../types/product";

export const getProductConfig = () =>
	request<ProductConfig>("/api/config/product");

export const saveProductConfig = (payload: ProductConfig) =>
	request<ProductConfig>("/api/config/product", {
		method: "PUT",
		body: JSON.stringify(payload),
	});

export const resetProductConfig = () =>
	request<{ status: string }>("/api/config/product", {
		method: "DELETE",
	});
