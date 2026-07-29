export interface ProviderSection {
	selected: string;
	providers: Record<string, Record<string, unknown>>;
}

export interface ProviderConfig {
	providers: Record<string, ProviderSection>;
	settings?: Record<string, Record<string, unknown>>;
}

export interface ProviderField {
	name: string;
	label: string;
	kind: string;
	secret?: boolean;
	options?: string[];
	hint?: string;
	min?: number;
	max?: number;
	step?: number;
	env_var?: string;
	integer?: boolean;
	json_type?: "array" | "object";
	item_type?: "object";
	required_item_keys?: string[];
}

export interface ProviderOption {
	label: string;
	fields: ProviderField[];
}

export interface ProviderOptions {
	field_hints?: Record<string, string>;
	settings?: Record<
		string,
		{
			label: string;
			description?: string;
			fields: ProviderField[];
		}
	>;
	providers: Record<
		string,
		{
			label?: string;
			providers: Record<string, ProviderOption>;
		}
	>;
}
