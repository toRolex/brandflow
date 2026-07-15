import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useCategorySuggestions, generateCategoryId } from "../useCategorySuggestions";
import { api } from "../../api/client";
import type { CategoryConfig, SuggestCategory } from "../../types";

vi.mock("../../api/client", () => ({
  api: {
    suggestCategories: vi.fn(),
  },
}));

const MOCK_SUGGESTIONS: SuggestCategory[] = [
  { label: "产品细节", description: "产品特写展示", vision_prompt: "product detail close-up" },
  { label: "调味过程", description: "加入调料的过程", vision_prompt: "seasoning process" },
];

=======
>>>>>>> origin/main
describe("generateCategoryId", () => {
  it("英文名生成有效 id", () => {
    expect(generateCategoryId("Test Category")).toBe("test_category");
  });

  it("中文名生成 fallback id", () => {
    const id = generateCategoryId("产品展示");
    expect(id).toMatch(/^cat_/);
    expect(id.length).toBeGreaterThan(0);
  });

  it("中英混合生成有效 id", () => {
    expect(generateCategoryId("产品ABC展示")).toContain("abc");
  });

  it("纯特殊字符生成 fallback id", () => {
    const id = generateCategoryId("!!!");
    expect(id).toMatch(/^cat_/);
    expect(id.length).toBeGreaterThan(0);
  });
});

describe("useCategorySuggestions", () => {
  const onConfirm = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: MOCK_SUGGESTIONS,
      errors: [],
    });
  });

  // ── 初始状态 ──

  it("初始状态为默认值", () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    expect(result.current.suggestions).toBeNull();
    expect(result.current.suggestLoading).toBe(false);
    expect(result.current.suggestError).toBeNull();
    expect(result.current.pendingSuggestionNames.size).toBe(0);
  });

  // ── S1: handleSuggest ──

  it("S1: handleSuggest 成功加载建议", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    expect(api.suggestCategories).toHaveBeenCalledTimes(1);
    expect(result.current.suggestions).toEqual(MOCK_SUGGESTIONS);
    expect(result.current.suggestLoading).toBe(false);
    expect(result.current.suggestError).toBeNull();
  });

  it("S1: handleSuggest 设置 loading 状态", () => {
    vi.mocked(api.suggestCategories).mockImplementation(
      () => new Promise(() => {}) // never resolves
    );

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    act(() => {
      result.current.handleSuggest();
    });

    expect(result.current.suggestLoading).toBe(true);
  });

  it("S2: handleSuggest 网络失败设置错误", async () => {
    vi.mocked(api.suggestCategories).mockRejectedValue(new Error("Network Error"));

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    expect(result.current.suggestError).toBe("获取 AI 建议失败");
    expect(result.current.suggestLoading).toBe(false);
    expect(result.current.suggestions).toBeNull();
  });

  it("S3: handleSuggest API 返回 errors 时设置错误", async () => {
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [],
      errors: ["未找到可用素材", "Vision API 调用失败"],
    });

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    expect(result.current.suggestError).toBe("未找到可用素材；Vision API 调用失败");
    expect(result.current.suggestLoading).toBe(false);
  });

  // ── S4/S5: toggleSuggestion ──

  it("S4: toggleSuggestion 添加 label 到待选集", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    // After load, all items are selected by default; uncheck both first
    act(() => {
      result.current.toggleSuggestion("产品细节");
    });
    act(() => {
      result.current.toggleSuggestion("调味过程");
    });
    expect(result.current.pendingSuggestionNames.size).toBe(0);

    // Now toggle back one
    act(() => {
      result.current.toggleSuggestion("产品细节");
    });

    expect(result.current.pendingSuggestionNames.has("产品细节")).toBe(true);
    expect(result.current.pendingSuggestionNames.size).toBe(1);
  });

  it("S5: toggleSuggestion 移除已选 label", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    // All suggestions are selected by default after load
    expect(result.current.pendingSuggestionNames.has("产品细节")).toBe(true);

    // Toggle off
    act(() => {
      result.current.toggleSuggestion("产品细节");
    });

    expect(result.current.pendingSuggestionNames.has("产品细节")).toBe(false);
    expect(result.current.pendingSuggestionNames.size).toBe(1);
  });

  // ── S6: cancelSuggestions ──

  it("S6: cancelSuggestions 重置所有状态", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    act(() => {
      result.current.cancelSuggestions();
    });

    expect(result.current.suggestions).toBeNull();
    expect(result.current.suggestError).toBeNull();
    expect(result.current.pendingSuggestionNames.size).toBe(0);
  });

  // ── S7-S11: confirmSuggestions ──

  it("S7: confirmSuggestions 合并选中建议并调用 onConfirm", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));
    onConfirm.mockResolvedValue(undefined);

    await act(async () => {
      await result.current.handleSuggest();
    });

    await act(async () => {
      await result.current.confirmSuggestions();
    });

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const merged = onConfirm.mock.calls[0][0] as CategoryConfig[];
    expect(merged).toHaveLength(2);
    expect(merged[0].name).toBe("产品细节");
    expect(merged[1].name).toBe("调味过程");
  });

  it("S8: confirmSuggestions 只包含已勾选的建议", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));
    onConfirm.mockResolvedValue(undefined);

    await act(async () => {
      await result.current.handleSuggest();
    });

    // Uncheck one
    act(() => {
      result.current.toggleSuggestion("调味过程");
    });

    await act(async () => {
      await result.current.confirmSuggestions();
    });

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const merged = onConfirm.mock.calls[0][0] as CategoryConfig[];
    expect(merged).toHaveLength(1);
    expect(merged[0].name).toBe("产品细节");
  });

  it("S9: confirmSuggestions 按 id 和 name 去重", async () => {
    const existingCategories: CategoryConfig[] = [
      { id: "chanpinxijie", name: "产品细节", description: "已有", vision_prompt: "existing" },
    ];
    const { result } = renderHook(() => useCategorySuggestions(existingCategories, onConfirm));
    onConfirm.mockResolvedValue(undefined);

    await act(async () => {
      await result.current.handleSuggest();
    });

    await act(async () => {
      await result.current.confirmSuggestions();
    });

    const merged = onConfirm.mock.calls[0][0] as CategoryConfig[];
    // "产品细节" is already in existingCategories by name, should be deduplicated
    // Result: 1 existing ("产品细节") + 1 new non-dup ("调味过程") = 2
    expect(merged).toHaveLength(2);
    expect(merged[0].name).toBe("产品细节");
    expect(merged[1].name).toBe("调味过程");
    // Verify "产品细节" in merged is the existing one (not a new id)
    expect(merged[0].id).toBe("chanpinxijie");
  });

  it("S10: confirmSuggestions 成功后重置 suggestions", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));
    onConfirm.mockResolvedValue(undefined);

    await act(async () => {
      await result.current.handleSuggest();
    });
    expect(result.current.suggestions).not.toBeNull();

    await act(async () => {
      await result.current.confirmSuggestions();
    });

    expect(result.current.suggestions).toBeNull();
    expect(result.current.pendingSuggestionNames.size).toBe(0);
  });

  it("S11: confirmSuggestions 保存失败不清除 suggestions", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));
    onConfirm.mockRejectedValue(new Error("Save failed"));

    await act(async () => {
      await result.current.handleSuggest();
    });

    await act(async () => {
      await result.current.confirmSuggestions();
    });

    // suggestions stay visible so user can retry
    expect(result.current.suggestions).not.toBeNull();
    expect(result.current.pendingSuggestionNames.size).toBe(2);
  });

  it("suggestions 为空时 confirmSuggestions 不调用 onConfirm", async () => {
    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.confirmSuggestions();
    });

    expect(onConfirm).not.toHaveBeenCalled();
  });

  // ── S12: backendErrors ──

  it("S12: backendErrors 保存后端返回的 errors 数组", async () => {
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [],
      errors: ["错误1", "错误2"],
    });

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    expect(result.current.backendErrors).toEqual(["错误1", "错误2"]);
    expect(result.current.suggestError).toBe("错误1；错误2");
    expect(result.current.suggestLoading).toBe(false);
  });

  it("S13: 网络失败时 backendErrors 保持空数组", async () => {
    vi.mocked(api.suggestCategories).mockRejectedValue(new Error("Network Error"));

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });

    expect(result.current.backendErrors).toEqual([]);
    expect(result.current.suggestError).toBe("获取 AI 建议失败");
    expect(result.current.suggestLoading).toBe(false);
  });

  it("S14: 先有后端错误时网络失败不覆盖 suggestError", async () => {
    // First call: backend returns errors
    vi.mocked(api.suggestCategories).mockResolvedValueOnce({
      suggestions: [],
      errors: ["Vision API 调用失败"],
    });

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });
    expect(result.current.backendErrors).toEqual(["Vision API 调用失败"]);
    expect(result.current.suggestError).toBe("Vision API 调用失败");

    // Second call: network fails
    vi.mocked(api.suggestCategories).mockRejectedValueOnce(new Error("Network Error"));

    await act(async () => {
      await result.current.handleSuggest();
    });

    // suggestError should still show backend error, not "获取 AI 建议失败"
    expect(result.current.suggestError).toBe("Vision API 调用失败");
    expect(result.current.backendErrors).toEqual(["Vision API 调用失败"]);
  });

  // ── S15/S16: dismissSuggestError ──

  it("S15: dismissSuggestError 清除 suggestError", async () => {
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [],
      errors: ["错误提示"],
    });

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });
    expect(result.current.suggestError).toBe("错误提示");

    act(() => {
      result.current.dismissSuggestError();
    });

    expect(result.current.suggestError).toBeNull();
  });

  it("S16: dismissSuggestError 不清除 backendErrors", async () => {
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [],
      errors: ["错误提示"],
    });

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });
    expect(result.current.backendErrors).toEqual(["错误提示"]);

    act(() => {
      result.current.dismissSuggestError();
    });

    // backendErrors preserved for retry context
    expect(result.current.backendErrors).toEqual(["错误提示"]);
    expect(result.current.suggestions).not.toBeNull();
  });

  // ── S17: auto-dismiss ──

  it("S17: suggestError 3 秒后自动消失", async () => {
    vi.useFakeTimers();
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [],
      errors: ["自动消失测试"],
    });

    const { result } = renderHook(() => useCategorySuggestions([], onConfirm));

    await act(async () => {
      await result.current.handleSuggest();
    });
    expect(result.current.suggestError).toBe("自动消失测试");

    // Advance past 3 seconds
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(result.current.suggestError).toBeNull();

    vi.useRealTimers();
  });
});
