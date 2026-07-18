import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { CategoryConfig, SuggestCategory } from "../types";

/** Generate a stable machine-readable id from a category name.
 *  Lowercase, replace spaces with underscores, strip non-alphanumeric chars.
 *  Falls back to a timestamp-based id for pure-Chinese names. */
export function generateCategoryId(name: string): string {
	const cleaned = name
		.toLowerCase()
		.replace(/\s+/g, "_")
		.replace(/[^a-z0-9_]/g, "");
	if (!cleaned.replace(/_/g, "")) {
		return `cat_${Date.now().toString(36)}`;
	}
	return cleaned;
}

export interface UseCategorySuggestionsReturn {
	suggestions: SuggestCategory[] | null;
	suggestLoading: boolean;
	suggestError: string | null;
	backendErrors: string[];
	pendingSuggestionNames: Set<string>;
	dismissSuggestError: () => void;
	handleSuggest: () => Promise<void>;
	toggleSuggestion: (label: string) => void;
	confirmSuggestions: () => Promise<void>;
	cancelSuggestions: () => void;
}

/**
 * Shared hook encapsulating AI category suggestion state and operations.
 *
 * @param categories - Current category list (used for deduplication when confirming)
 * @param onConfirm  - Callback receiving the merged category list after user confirms.
 *                     Throw to signal failure; the hook will set suggestError.
 */
export function useCategorySuggestions(
	categories: CategoryConfig[],
	onConfirm: (mergedCategories: CategoryConfig[]) => Promise<void>,
): UseCategorySuggestionsReturn {
	const [suggestions, setSuggestions] = useState<SuggestCategory[] | null>(
		null,
	);
	const [pendingSuggestionNames, setPendingSuggestionNames] = useState<
		Set<string>
	>(new Set());
	const [suggestLoading, setSuggestLoading] = useState(false);
	const [suggestError, setSuggestError] = useState<string | null>(null);
	const [backendErrors, setBackendErrors] = useState<string[]>([]);
	const backendErrorsRef = useRef<string[]>([]);

	// Auto-dismiss suggestError after 3 seconds
	useEffect(() => {
		if (suggestError) {
			const timer = setTimeout(() => setSuggestError(null), 3000);
			return () => clearTimeout(timer);
		}
	}, [suggestError]);

	const handleSuggest = useCallback(async () => {
		setSuggestLoading(true);
		setSuggestions(null);
		try {
			const result = await api.suggestCategories();
			setSuggestions(result.suggestions);
			setPendingSuggestionNames(
				new Set(result.suggestions.map((s) => s.label)),
			);
			if (result.errors && result.errors.length > 0) {
				backendErrorsRef.current = result.errors;
				setBackendErrors(result.errors);
				setSuggestError(result.errors.join("；"));
			} else {
				backendErrorsRef.current = [];
				setBackendErrors([]);
				setSuggestError(null);
			}
		} catch {
			// Network failure: don't overwrite informative backend errors
			if (backendErrorsRef.current.length > 0) {
				setSuggestError(backendErrorsRef.current.join("；"));
			} else {
				setSuggestError("获取 AI 建议失败");
			}
		}
		setSuggestLoading(false);
	}, []);

	const dismissSuggestError = useCallback(() => {
		setSuggestError(null);
	}, []);

	const toggleSuggestion = useCallback((label: string) => {
		setPendingSuggestionNames((prev) => {
			const next = new Set(prev);
			if (next.has(label)) {
				next.delete(label);
			} else {
				next.add(label);
			}
			return next;
		});
	}, []);

	const confirmSuggestions = useCallback(async () => {
		if (!suggestions) return;

		setSuggestError(null);

		const checked = suggestions.filter((s) =>
			pendingSuggestionNames.has(s.label),
		);
		const newCategories: CategoryConfig[] = checked.map((s) => ({
			id: generateCategoryId(s.label),
			name: s.label,
			description: s.description,
			vision_prompt: s.vision_prompt,
		}));

		// Merge with existing categories, avoid duplicates by id then by name
		const existingIds = new Set(categories.map((c) => c.id));
		const existingNames = new Set(categories.map((c) => c.name));
		const merged = [
			...categories,
			...newCategories.filter(
				(c) => !existingIds.has(c.id) && !existingNames.has(c.name),
			),
		];

		try {
			await onConfirm(merged);
			// Clear suggestions only on success
			setSuggestions(null);
			setPendingSuggestionNames(new Set());
		} catch {
			// Component handles save error display via onConfirm callback
		}
	}, [suggestions, pendingSuggestionNames, categories, onConfirm]);

	const cancelSuggestions = useCallback(() => {
		setSuggestions(null);
		setSuggestError(null);
		setBackendErrors([]);
		backendErrorsRef.current = [];
		setPendingSuggestionNames(new Set());
	}, []);

	return {
		suggestions,
		suggestLoading,
		suggestError,
		backendErrors,
		pendingSuggestionNames,
		dismissSuggestError,
		handleSuggest,
		toggleSuggestion,
		confirmSuggestions,
		cancelSuggestions,
	};
}
