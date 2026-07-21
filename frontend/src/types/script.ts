export interface ScriptCheckResult {
	length: number;
	brand_name_count: number;
	product_name_count: number;
	has_safety_warning: boolean;
	has_emoji: boolean;
	forbidden_terms: string[];
	passed: boolean;
}
