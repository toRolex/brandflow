import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Pagination from "../Pagination";

describe("Pagination", () => {
	it("renders nothing when totalPages is 1", () => {
		const { container } = render(
			<Pagination
				page={1}
				pageSize={50}
				total={10}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(container.firstChild).toBeNull();
	});

	it("renders page buttons and total count", () => {
		render(
			<Pagination
				page={1}
				pageSize={50}
				total={100}
				onPageChange={vi.fn()}
				onPageSizeChange={vi.fn()}
			/>,
		);
		expect(screen.getByText("共 100 条")).toBeInTheDocument();
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

	it("disables prev button on the first page", () => {
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
	});

	it("disables next button on the last page", () => {
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
});
