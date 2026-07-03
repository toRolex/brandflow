import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ScriptTemplateEditor from "../ScriptTemplateEditor";
import { api } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: {
    getTemplate: vi.fn(),
    createTemplate: vi.fn(),
    updateTemplate: vi.fn(),
    previewTemplate: vi.fn(),
  },
}));

const EXISTING_TEMPLATE = {
  id: "tmpl_001",
  name: "通用带货脚本",
  description: "适用于食品类短视频带货",
  slots: [
    { type: "hook" as const, label: "开头钩子", required: true, max_length: 60, hint: "吸引眼球的开头" },
  ],
  variables: [
    { name: "product_name", label: "产品名", source: "product_config" as const },
  ],
  default_config_override: {},
};

function renderNewTemplate() {
  return render(
    <MemoryRouter initialEntries={["/system/config/templates/new"]}>
      <Routes>
        <Route path="/system/config/templates/new" element={<ScriptTemplateEditor />} />
      </Routes>
    </MemoryRouter>
  );
}

function renderExistingTemplate(id: string = "tmpl_001") {
  return render(
    <MemoryRouter initialEntries={[`/system/config/templates/${id}`]}>
      <Routes>
        <Route path="/system/config/templates/:id" element={<ScriptTemplateEditor />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ScriptTemplateEditor - New Template", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("新建模式下显示标题和保存按钮", () => {
    renderNewTemplate();
    expect(screen.getByText("新建脚本模板")).toBeInTheDocument();
    expect(screen.getByText("保存模板")).toBeInTheDocument();
  });

  it("新建模式不加载 API", () => {
    renderNewTemplate();
    expect(api.getTemplate).not.toHaveBeenCalled();
  });

  it("输入模板名称和描述", async () => {
    renderNewTemplate();
    const nameInput = screen.getByPlaceholderText("输入模板名称");
    fireEvent.change(nameInput, { target: { value: "新模板" } });
    await waitFor(() => {
      expect(screen.getByDisplayValue("新模板")).toBeInTheDocument();
    });
  });
});

describe("ScriptTemplateEditor - Existing Template", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getTemplate).mockResolvedValue(EXISTING_TEMPLATE);
  });

  it("加载时调用 getTemplate API", () => {
    renderExistingTemplate();
    expect(api.getTemplate).toHaveBeenCalledWith("tmpl_001");
  });

  it("回显已有模板数据", async () => {
    renderExistingTemplate();
    await waitFor(() => {
      expect(screen.getByDisplayValue("通用带货脚本")).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue("适用于食品类短视频带货")).toBeInTheDocument();
  });

  it("显示 slot 信息", async () => {
    renderExistingTemplate();
    const matches = await screen.findAllByDisplayValue("开头钩子");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("显示变量信息", async () => {
    renderExistingTemplate();
    await waitFor(() => {
      expect(screen.getByDisplayValue("product_name")).toBeInTheDocument();
    });
  });

  it("保存按钮调用 updateTemplate API", async () => {
    vi.mocked(api.updateTemplate).mockResolvedValue(EXISTING_TEMPLATE);
    renderExistingTemplate();

    await waitFor(() => {
      expect(screen.getByDisplayValue("通用带货脚本")).toBeInTheDocument();
    });

    const saveBtn = screen.getByText("保存模板");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.updateTemplate).toHaveBeenCalledWith("tmpl_001", expect.any(Object));
    });
  });

  it("保存成功后显示提示", async () => {
    vi.mocked(api.updateTemplate).mockResolvedValue(EXISTING_TEMPLATE);
    renderExistingTemplate();

    await waitFor(() => {
      expect(screen.getByDisplayValue("通用带货脚本")).toBeInTheDocument();
    });

    const saveBtn = screen.getByText("保存模板");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("模板已保存")).toBeInTheDocument();
    });
  });
});
