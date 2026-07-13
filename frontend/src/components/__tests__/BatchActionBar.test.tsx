import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import BatchActionBar from "../BatchActionBar";

describe("BatchActionBar", () => {
  const defaultProps = {
    count: 3,
    onEnable: vi.fn(),
    onDisable: vi.fn(),
    onDelete: vi.fn(),
    onClear: vi.fn(),
  };

  it("renders custom categories in the batch edit dropdown", async () => {
    const onBatchEdit = vi.fn();
    const customCategories = ["促销活动", "开箱展示", "产品评测"];

    const { container } = render(
      <BatchActionBar
        {...defaultProps}
        onBatchEdit={onBatchEdit}
        categories={customCategories}
      />
    );

    // Click batch edit button
    fireEvent.click(screen.getByText("批量编辑"));

    // Dropdown should show "不修改" as default + custom categories
    expect(screen.getByText("不修改")).toBeInTheDocument();

    const selects = container.querySelectorAll("select");
    // The category select is the only select in the batch edit panel
    const categorySelect = selects[0] as HTMLSelectElement;
    const optionTexts = Array.from(categorySelect.options).map((o) => o.text);
    expect(optionTexts).toContain("不修改");
    for (const cat of customCategories) {
      expect(optionTexts).toContain(cat);
    }
  });

  it("submits custom category in batch edit", async () => {
    const onBatchEdit = vi.fn();
    const customCategories = ["促销活动", "开箱展示"];

    const { container } = render(
      <BatchActionBar
        {...defaultProps}
        onBatchEdit={onBatchEdit}
        categories={customCategories}
      />
    );

    fireEvent.click(screen.getByText("批量编辑"));

    // Find the category select (it's the select in the form)
    const selects = container.querySelectorAll("select");
    const categorySelect = selects[0] as HTMLSelectElement;
    fireEvent.change(categorySelect, { target: { value: "促销活动" } });

    // Click apply
    fireEvent.click(screen.getByText("应用"));

    await waitFor(() => {
      expect(onBatchEdit).toHaveBeenCalledWith({ category: "促销活动" });
    });
  });

  it("renders old food categories in batch edit", async () => {
    const onBatchEdit = vi.fn();
    const foodCategories = ["产地溯源", "烹饪翻炒", "产品特写"];

    const { container } = render(
      <BatchActionBar
        {...defaultProps}
        onBatchEdit={onBatchEdit}
        categories={foodCategories}
      />
    );

    fireEvent.click(screen.getByText("批量编辑"));

    const selects = container.querySelectorAll("select");
    const categorySelect = selects[0] as HTMLSelectElement;
    const optionTexts = Array.from(categorySelect.options).map((o) => o.text);
    for (const cat of foodCategories) {
      expect(optionTexts).toContain(cat);
    }
  });
});
