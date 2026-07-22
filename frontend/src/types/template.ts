export type SlotType =
	| "hook"
	| "selling_point"
	| "usage_scene"
	| "call_to_action";

export type VariableSource = "manual" | "product_config" | "knowledge_base";

export interface TemplateSlot {
	type: SlotType;
	label: string;
	required: boolean;
	max_length: number;
	hint: string;
}

export interface TemplateVariable {
	name: string;
	label: string;
	source: VariableSource;
}

export interface ScriptTemplate {
	id: string;
	name: string;
	description: string;
	slots: TemplateSlot[];
	variables: TemplateVariable[];
	default_config_override: Record<string, unknown>;
}

export interface PreviewResponse {
	rendered_script: string;
}
