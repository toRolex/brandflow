import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StatusBadge from "../StatusBadge";

describe("StatusBadge (#262)", () => {
	it("renders '终审·合成' for final_rendering phase", () => {
		render(<StatusBadge phase="final_rendering" />);
		expect(screen.getByText("终审·合成")).toBeInTheDocument();
	});
});
