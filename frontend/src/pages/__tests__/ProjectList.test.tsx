import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { api } from "../../api/client";
import ProjectList from "../ProjectList";

vi.mock("../../api/client", () => ({
  api: {
    listProjects: vi.fn(),
    createProject: vi.fn(),
    deleteProject: vi.fn(),
  },
}));

const MOCK_PROJECTS = [
  { id: "p1", name: "项目A", status: "active", job_count: 3 },
  { id: "p2", name: "项目B", status: "active", job_count: 1 },
];

function renderPage() {
  return render(
    <BrowserRouter>
      <ProjectList />
    </BrowserRouter>,
  );
}

describe("ProjectList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("loading state", () => {
    it("shows loading indicator on initial mount, not empty state", () => {
      // Don't resolve the listProjects promise yet
      vi.mocked(api.listProjects).mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText("加载中...")).toBeInTheDocument();
      // Empty state text should NOT be present
      expect(
        screen.queryByText("开始你的第一个项目"),
      ).not.toBeInTheDocument();
    });

    it("shows empty state after loading when no projects", async () => {
      vi.mocked(api.listProjects).mockResolvedValue([]);
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByText("开始你的第一个项目"),
        ).toBeInTheDocument();
      });
    });

    it("shows project list after loading with data", async () => {
      vi.mocked(api.listProjects).mockResolvedValue(MOCK_PROJECTS);
      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });
      expect(screen.getByText("项目B")).toBeInTheDocument();
    });
  });

  describe("header create button", () => {
    it("renders persistent 新建项目 button in header", async () => {
      vi.mocked(api.listProjects).mockResolvedValue(MOCK_PROJECTS);
      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });
      // Header button (first "新建项目" in the document)
      const buttons = screen.getAllByText("新建项目");
      expect(buttons.length).toBe(1); // Only header button when list is shown
    });

    it("opens create modal when header button is clicked", async () => {
      vi.mocked(api.listProjects).mockResolvedValue(MOCK_PROJECTS);
      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });
      // Header is inside the flex header div
      const header = screen.getByText("项目列表").parentElement!;
      fireEvent.click(within(header).getByText("新建项目"));
      expect(
        screen.getByPlaceholderText("请输入项目名称"),
      ).toBeInTheDocument();
      expect(screen.getByText("创建")).toBeInTheDocument(); // modal has create button
    });
  });

  describe("empty state create button", () => {
    it("shows 新建项目 button in empty state and it opens modal", async () => {
      vi.mocked(api.listProjects).mockResolvedValue([]);
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByText("开始你的第一个项目"),
        ).toBeInTheDocument();
      });
      // Empty-state button lives in the empty-state section
      const emptyState = screen.getByText("开始你的第一个项目").parentElement!;
      fireEvent.click(within(emptyState).getByText("新建项目"));
      expect(
        screen.getByPlaceholderText("请输入项目名称"),
      ).toBeInTheDocument();
    });
  });

  describe("create validation", () => {
    it("shows error for empty name", async () => {
      vi.mocked(api.listProjects).mockResolvedValue([]);
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByText("开始你的第一个项目"),
        ).toBeInTheDocument();
      });
      // Open modal via empty state button
      const emptyState = screen.getByText("开始你的第一个项目").parentElement!;
      fireEvent.click(within(emptyState).getByText("新建项目"));
      expect(
        screen.getByPlaceholderText("请输入项目名称"),
      ).toBeInTheDocument();
      // Click create without entering name
      fireEvent.click(screen.getByText("创建"));
      expect(screen.getByText("项目名称不能为空")).toBeInTheDocument();
    });

    it("shows error for duplicate name", async () => {
      vi.mocked(api.listProjects).mockResolvedValue(MOCK_PROJECTS);
      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });
      const header = screen.getByText("项目列表").parentElement!;
      fireEvent.click(
        within(header).getByText("新建项目"),
      );
      const input = screen.getByPlaceholderText("请输入项目名称");
      fireEvent.change(input, { target: { value: "项目A" } });
      fireEvent.click(screen.getByText("创建"));
      expect(
        screen.getByText("项目名称已存在，请使用其他名称"),
      ).toBeInTheDocument();
      // Modal should still be open
      expect(
        screen.getByPlaceholderText("请输入项目名称"),
      ).toBeInTheDocument();
    });
  });

  describe("create success", () => {
    it("stays on list, shows banner, and highlights new row", async () => {
      const newProject = {
        id: "p3",
        name: "项目C",
        status: "active",
        job_count: 0,
      };
      vi.mocked(api.listProjects).mockResolvedValueOnce(MOCK_PROJECTS);
      vi.mocked(api.createProject).mockResolvedValueOnce(newProject);
      vi.mocked(api.listProjects).mockResolvedValueOnce([
        ...MOCK_PROJECTS,
        newProject,
      ]);

      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });
      const header = screen.getByText("项目列表").parentElement!;
      fireEvent.click(
        within(header).getByText("新建项目"),
      );
      const input = screen.getByPlaceholderText("请输入项目名称");
      fireEvent.change(input, { target: { value: "项目C" } });
      fireEvent.click(screen.getByText("创建"));

      // Should stay on list (not navigate away)
      await waitFor(() => {
        expect(screen.getByText("项目C")).toBeInTheDocument();
      });
      // Success banner should appear
      expect(
        screen.getByText('项目「项目C」创建成功'),
      ).toBeInTheDocument();
    });
  });

  describe("create failure", () => {
    it("shows error banner when create fails", async () => {
      vi.mocked(api.listProjects).mockResolvedValueOnce(MOCK_PROJECTS);
      vi.mocked(api.createProject).mockRejectedValueOnce(
        new Error("创建失败：服务错误"),
      );

      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });
      const header = screen.getByText("项目列表").parentElement!;
      fireEvent.click(
        within(header).getByText("新建项目"),
      );
      fireEvent.change(
        screen.getByPlaceholderText("请输入项目名称"),
        { target: { value: "新项目" } },
      );
      fireEvent.click(screen.getByText("创建"));

      await waitFor(() => {
        expect(
          screen.getByText("创建失败：服务错误"),
        ).toBeInTheDocument();
      });
    });
  });

  describe("bulk selection", () => {
    it("shows checkboxes and selects a single row", async () => {
      vi.mocked(api.listProjects).mockResolvedValue(MOCK_PROJECTS);
      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });

      const rowCheckboxes = screen.getAllByRole("checkbox", {
        name: /选择项目/,
      });
      expect(rowCheckboxes.length).toBe(2);

      fireEvent.click(rowCheckboxes[0]);
      expect(screen.getByText("已选 1 项")).toBeInTheDocument();
    });

    it("selects all rows via header checkbox", async () => {
      vi.mocked(api.listProjects).mockResolvedValue(MOCK_PROJECTS);
      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });

      const headerCheckbox = screen.getByRole("checkbox", { name: "全选" });
      fireEvent.click(headerCheckbox);
      expect(screen.getByText("已选 2 项")).toBeInTheDocument();

      fireEvent.click(headerCheckbox);
      expect(screen.queryByText("已选 2 项")).not.toBeInTheDocument();
    });

    it("shows bulk action bar only when items are selected", async () => {
      vi.mocked(api.listProjects).mockResolvedValue(MOCK_PROJECTS);
      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });

      expect(screen.queryByText("已选 1 项")).not.toBeInTheDocument();
      const rowCheckboxes = screen.getAllByRole("checkbox", {
        name: /选择项目/,
      });
      fireEvent.click(rowCheckboxes[0]);
      expect(screen.getByText("已选 1 项")).toBeInTheDocument();
    });
  });

  describe("bulk delete", () => {
    it("deletes selected projects and refreshes the list", async () => {
      vi.mocked(api.listProjects).mockResolvedValueOnce(MOCK_PROJECTS);
      vi.mocked(api.deleteProject).mockResolvedValue({ ok: true });
      vi.mocked(api.listProjects).mockResolvedValueOnce([MOCK_PROJECTS[1]]);

      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });

      const rowCheckboxes = screen.getAllByRole("checkbox", {
        name: /选择项目/,
      });
      fireEvent.click(rowCheckboxes[0]);

      fireEvent.click(screen.getByRole("button", { name: "批量删除" }));
      fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

      await waitFor(() => {
        expect(screen.getByText("已删除 1 个项目")).toBeInTheDocument();
      });
      expect(screen.queryByText("项目A")).not.toBeInTheDocument();
      expect(screen.getByText("项目B")).toBeInTheDocument();
    });

    it("shows partial failure summary and refreshes the list", async () => {
      vi.mocked(api.listProjects).mockResolvedValueOnce(MOCK_PROJECTS);
      vi.mocked(api.deleteProject).mockImplementation((id: string) => {
        if (id === "p1") return Promise.resolve({ ok: true });
        return Promise.reject(new Error("删除失败：权限不足"));
      });
      vi.mocked(api.listProjects).mockResolvedValueOnce([MOCK_PROJECTS[1]]);

      renderPage();
      await waitFor(() => {
        expect(screen.getByText("项目A")).toBeInTheDocument();
      });

      const headerCheckbox = screen.getByRole("checkbox", { name: "全选" });
      fireEvent.click(headerCheckbox);

      fireEvent.click(screen.getByRole("button", { name: "批量删除" }));
      fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

      await waitFor(() => {
        expect(screen.getByText("1 成功，1 失败")).toBeInTheDocument();
      });
      expect(screen.queryByText("项目A")).not.toBeInTheDocument();
      expect(screen.getByText("项目B")).toBeInTheDocument();
    });
  });
});
