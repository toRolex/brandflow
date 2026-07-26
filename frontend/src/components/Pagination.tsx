import { useRef, useState } from "react";

interface PaginationProps {
	page: number;
	pageSize: number;
	total: number;
	onPageChange: (page: number) => void;
	onPageSizeChange: (size: number) => void;
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100, 200];
const MAX_VISIBLE_PAGES = 7;

export default function Pagination({
	page,
	pageSize,
	total,
	onPageChange,
	onPageSizeChange,
}: PaginationProps) {
	const totalPages = Math.max(1, Math.ceil(total / pageSize));
	const currentPage = Math.max(1, Math.min(page, totalPages));
	const [jumpInput, setJumpInput] = useState("");
	const jumpRef = useRef<HTMLInputElement>(null);

	const pages = buildPageNumbers(currentPage, totalPages, MAX_VISIBLE_PAGES);

	/* ── slot range ── */
	const startItem = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
	const endItem = Math.min(currentPage * pageSize, total);

	const handleJump = () => {
		const target = parseInt(jumpInput, 10);
		if (isNaN(target)) return;
		const clamped = Math.max(1, Math.min(target, totalPages));
		setJumpInput("");
		if (clamped !== currentPage) onPageChange(clamped);
	};

	return (
		<div
			className="flex items-center justify-between mt-4 text-sm border-t rounded-b-lg px-3 py-2.5"
			style={{
				background: "var(--bg-table-head)",
				borderColor: "var(--border-default)",
			}}
		>
			{/* ── Left: page-size selector + slot range ── */}
			<div className="flex items-center gap-2">
				<span style={{ color: "var(--text-secondary)" }}>每页</span>
				<select
					className="rounded border px-2 py-1 text-sm"
					style={{
						background: "var(--input-bg)",
						color: "var(--input-text)",
						borderColor: "var(--input-border)",
					}}
					value={pageSize}
					onChange={(e) => onPageSizeChange(Number(e.target.value))}
				>
					{PAGE_SIZE_OPTIONS.map((size) => (
						<option key={size} value={size}>
							{size}
						</option>
					))}
				</select>
				<span style={{ color: "var(--text-secondary)" }}>条</span>

				{/* slot range */}
				<span
					className="ml-3"
					style={{ color: "var(--text-tertiary)" }}
				>
					第 {startItem}-{endItem} 条，共 {total} 条
				</span>
			</div>

			{/* ── Right: page navigation ── */}
			<div className="flex items-center gap-1">
				{/* First */}
				<PageNavButton
					label="首页"
					disabled={currentPage <= 1}
					onClick={() => onPageChange(1)}
				/>

				{/* Prev */}
				<PageNavButton
					label="上一页"
					disabled={currentPage <= 1}
					onClick={() => onPageChange(currentPage - 1)}
				/>

				{/* Page numbers */}
				{pages.map((p, i) =>
					p === null ? (
						<span
							key={`ellipsis-${i}`}
							className="px-2 py-1.5"
							style={{ color: "var(--text-tertiary)" }}
						>
							…
						</span>
					) : (
						<button
							key={p}
							className="px-3 py-1.5 rounded text-sm font-medium transition-colors"
							style={{
								background:
									p === currentPage
										? "var(--btn-primary-bg)"
										: "var(--btn-ghost-bg)",
								color:
									p === currentPage
										? "var(--btn-primary-text)"
										: "var(--btn-ghost-text)",
								border: p === page ? "none" : "1px solid var(--border-default)",
							}}
							onClick={() => onPageChange(p)}
						>
							{p}
						</button>
					),
				)}

				{/* Next */}
				<PageNavButton
					label="下一页"
					disabled={currentPage >= totalPages}
					onClick={() => onPageChange(currentPage + 1)}
				/>

				{/* Last */}
				<PageNavButton
					label="末页"
					disabled={currentPage >= totalPages}
					onClick={() => onPageChange(totalPages)}
				/>

				{/* Jump-to input */}
				<span
					className="ml-3"
					style={{ color: "var(--text-secondary)" }}
				>
					跳至
				</span>
				<input
					ref={jumpRef}
					type="number"
					min={1}
					max={totalPages}
					className="w-12 rounded border px-2 py-1 text-sm text-center"
					style={{
						background: "var(--input-bg)",
						color: "var(--input-text)",
						borderColor: "var(--input-border)",
					}}
					value={jumpInput}
					placeholder={`${currentPage}`}
					onChange={(e) => setJumpInput(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === "Enter") handleJump();
					}}
					onBlur={handleJump}
				/>
				<span style={{ color: "var(--text-secondary)" }}>页</span>
			</div>
		</div>
	);
}

/* ── small helper ── */

function PageNavButton({
	label,
	disabled,
	onClick,
}: {
	label: string;
	disabled: boolean;
	onClick: () => void;
}) {
	return (
		<button
			className="px-2.5 py-1.5 rounded text-sm font-medium transition-colors"
			style={{
				background: "var(--btn-ghost-bg)",
				color: disabled
					? "var(--text-tertiary)"
					: "var(--btn-ghost-text)",
				border: "1px solid var(--border-default)",
				cursor: disabled ? "not-allowed" : "pointer",
				opacity: disabled ? 0.5 : 1,
			}}
			disabled={disabled}
			onClick={onClick}
		>
			{label}
		</button>
	);
}

/* ── page-number builder ── */

/**
 * Build an array of page numbers (and null placeholders for ellipsis)
 * for a pagination window.
 *
 * Examples for totalPages=20, maxVisible=7:
 *   page=1  → [1, 2, 3, 4, 5, 6, 7, null, 20]
 *   page=10 → [1, null, 8, 9, 10, 11, 12, null, 20]
 *   page=20 → [1, null, 14, 15, 16, 17, 18, 19, 20]
 */
function buildPageNumbers(
	page: number,
	totalPages: number,
	maxVisible: number,
): (number | null)[] {
	if (totalPages <= maxVisible) {
		return Array.from({ length: totalPages }, (_, i) => i + 1);
	}

	const half = Math.floor((maxVisible - 2) / 2);
	let start = page - half;
	let end = page + half;

	if (start < 2) {
		start = 2;
		end = Math.min(maxVisible - 1, totalPages - 1);
	} else if (end > totalPages - 1) {
		end = totalPages - 1;
		start = Math.max(2, totalPages - maxVisible + 2);
	}

	const pages: (number | null)[] = [1];

	if (start > 2) {
		pages.push(null);
	}

	for (let i = start; i <= end; i++) {
		pages.push(i);
	}

	if (end < totalPages - 1) {
		pages.push(null);
	}

	pages.push(totalPages);
	return pages;
}
