export interface ProviderSection {
	selected: string;
	providers: Record<string, Record<string, unknown>>;
}

export interface ProviderConfig {
	providers: Record<string, ProviderSection>;
}

export interface ProviderField {
	name: string;
	label: string;
	kind: string;
	secret?: boolean;
	options?: string[];
}

export interface ProviderOption {
	label: string;
	fields: ProviderField[];
}

export interface ProviderOptions {
	field_hints?: Record<string, string>;
	providers: Record<
		string,
		{
			providers: Record<string, ProviderOption>;
		}
	>;
}
