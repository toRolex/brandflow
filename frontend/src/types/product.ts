export interface ProductConfig {
	default_name: string;
	default_brand: string;
	script: {
		scene: string;
		material: string;
		system_prompt: string;
		word_count_min?: number;
		word_count_max?: number;
		forbidden_words?: string[];
		emoji_forbidden?: boolean;
		product_name_count?: number;
		brand_name_count?: number;
		[key: string]: unknown;
	};
	categories?: CategoryConfig[];
	[key: string]: unknown;
}

export interface CategoryConfig {
	id: string;
	name: string;
	description: string;
	vision_prompt: string;
}
