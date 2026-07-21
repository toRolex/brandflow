import { request } from "./core";

export const listProducts = () =>
	request<Array<{ id: string; name: string }>>("/api/products");

export const createProduct = (name: string) =>
	request<{ id: string; name: string }>("/api/products", {
		method: "POST",
		body: JSON.stringify({ name }),
	});

export const renameProduct = (productId: string, name: string) =>
	request<{ id: string; name: string }>(`/api/products/${productId}`, {
		method: "PATCH",
		body: JSON.stringify({ name }),
	});

export const deleteProduct = (productId: string) =>
	request<{ status: string; active_product_id: string }>(
		`/api/products/${productId}`,
		{
			method: "DELETE",
		},
	);

export const switchProduct = (productId: string) =>
	request<{ active_product_id: string }>(
		`/api/products/${productId}/switch`,
		{
			method: "POST",
		},
	);

export const getProductConfigById = (productId: string) =>
	request<import("../types/product").ProductConfig>(
		`/api/products/${productId}/config`,
	);

export const saveProductConfigById = (
	productId: string,
	payload: import("../types/product").ProductConfig,
) =>
	request<import("../types/product").ProductConfig>(
		`/api/products/${productId}/config`,
		{
			method: "PUT",
			body: JSON.stringify(payload),
		},
	);
