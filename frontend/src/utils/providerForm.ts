import type { ProviderField } from "../types";

/** Sentinel value used to mask already-configured secrets. */
export const SECRET_MASK = "***";

/** Render a provider field value into a form-input-ready string. */
export function displayFieldValue(
	value: unknown,
	field: ProviderField,
): string {
	if (field.secret && value === SECRET_MASK) {
		return "";
	}
	if (field.kind === "json" && typeof value !== "string") {
		return JSON.stringify(value ?? {}, null, 2);
	}
	if (typeof value === "string") {
		return value;
	}
	if (typeof value === "number") {
		return String(value);
	}
	return "";
}
