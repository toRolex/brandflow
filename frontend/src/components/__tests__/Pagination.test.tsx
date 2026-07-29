import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Pagination from "../Pagination";

describe("Pagination", () => {
	it("always renders (no longer hidden for single-page data)", () => {
		const { container } = render(
			<Pagination
				page={1}
				pageSize={50}
				total={10}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(container.firstChild).not.toBeNull();
		expect(
			screen.getByText(/第\s*1-10\s*条，共\s*10\s*条/),
		).toBeInTheDocument();
		expect(screen.getByText("1")).toBeInTheDocument();
	});

	it("shows slot range info", () => {
		render(
			<Pagination
				page={2}
				pageSize={50}
				total={200}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(
			screen.getByText(/第\s*51-100\s*条，共\s*200\s*条/),
		).toBeInTheDocument();
	});

	it("renders page buttons", () => {
		render(
			<Pagination
				page={1}
				pageSize={50}
				total={100}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		const select = screen.getByRole("combobox") as HTMLSelectElement;
		expect(select.value).toBe("50");
	});

	it("calls onPageChange when a page number is clicked", async () => {
		const onPageChange = vi.fn();
		render(
			<Pagination
				page={1}
				pageSize={10}
				total={100}
				onPageChange={onPageChange}
				onPageSizeChange={vi.fn()}
			/>,
		);
		await userEvent.click(screen.getByText("3"));
		expect(onPageChange).toHaveBeenCalledWith(3);
	});

	it("calls onPageSizeChange when page-size selector changes", async () => {
		const onPageSizeChange = vi.fn();
		render(
			<Pagination
				page={1}
				pageSize={25}
				total={200}
				onPageChange={vi.fn()}
				onPageSizeChange={onPageSizeChange}
			/>,
		);
		await userEvent.selectOptions(screen.getByRole("combobox"), "50");
		expect(onPageSizeChange).toHaveBeenCalledWith(50);
	});

	it("disables prev and first buttons on the first page", () => {
		render(
			<Pagination
				page={1}
				pageSize={10}
				total={100}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(screen.getByText("上一页")).toBeDisabled();
		expect(screen.getByText("首页")).toBeDisabled();
	});

	it("disables next and last buttons on the last page", () => {
		render(
			<Pagination
				page={10}
				pageSize={10}
				total={100}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(screen.getByText("下一页")).toBeDisabled();
		expect(screen.getByText("末页")).toBeDisabled();
	});

	it("shows ellipsis for large page counts", () => {
		render(
			<Pagination
				page={10}
				pageSize={5}
				total={500}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(screen.getAllByText("…").length).toBeGreaterThanOrEqual(2);
	});

	it("jumps to page via input", async () => {
		const onPageChange = vi.fn();
		render(
			<Pagination
				page={1}
				pageSize={10}
				total={200}
				onPageChange={onPageChange}
				onPageSizeChange={vi.fn()}
			/>,
		);
		const input = screen.getByPlaceholderText("1") as HTMLInputElement;
		await userEvent.type(input, "5");
		await userEvent.keyboard("{Enter}");
		expect(onPageChange).toHaveBeenCalledWith(5);
	});

	it("clamps jump input to valid page range", async () => {
		const onPageChange = vi.fn();
		render(
			<Pagination
				page={1}
				pageSize={10}
				total={100}
				onPageChange={onPageChange}
				onPageSizeChange={vi.fn()}
			/>,
		);
		const input = screen.getByPlaceholderText("1") as HTMLInputElement;
		await userEvent.type(input, "99");
		await userEvent.keyboard("{Enter}");
		expect(onPageChange).toHaveBeenCalledWith(10);
	});

	it("navigates to first page via first button", async () => {
		const onPageChange = vi.fn();
		render(
			<Pagination
				page={5}
				pageSize={10}
				total={100}
				onPageChange={onPageChange}
				onPageSizeChange={vi.fn()}
			/>,
		);
		await userEvent.click(screen.getByText("首页"));
		expect(onPageChange).toHaveBeenCalledWith(1);
	});

	it("navigates to last page via last button", async () => {
		const onPageChange = vi.fn();
		render(
			<Pagination
				page={5}
				pageSize={10}
				total={100}
				onPageChange={onPageChange}
				onPageSizeChange={vi.fn()}
			/>,
		);
		await userEvent.click(screen.getByText("末页"));
		expect(onPageChange).toHaveBeenCalledWith(10);
	});

	it("handles zero total gracefully", () => {
		render(
			<Pagination
				page={1}
				pageSize={10}
				total={0}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(screen.getByText(/第\s*0-0\s*条，共\s*0\s*条/)).toBeInTheDocument();
	});

	it("uses the last valid page when the supplied page is out of range", () => {
		render(
			<Pagination
				page={3}
				pageSize={10}
				total={15}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(
			screen.getByText(/第\s*11-15\s*条，共\s*15\s*条/),
		).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "2" })).toHaveStyle({
			background: "var(--btn-primary-bg)",
		});
	});
});
