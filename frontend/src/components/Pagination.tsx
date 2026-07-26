interface PaginationProps {
	page: number;
	pageSize: number;
	total: number;
	onPageChange: (page: number) => void;
	onPageSizeChange: (size: number) => void;
}

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];
const MAX_VISIBLE_PAGES = 7;

export default function Pagination({
	page,
	pageSize,
	total,
	onPageChange,
	onPageSizeChange,
}: PaginationProps) {
	const totalPages = Math.max(1, Math.ceil(total / pageSize));

	// Hidden when there's only one page
	if (totalPages <= 1) return null;

	const pages = buildPageNumbers(page, totalPages, MAX_VISIBLE_PAGES);

	return (
		<div className="flex items-center justify-between mt-4 text-sm">
			{/* Page-size selector */}
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
			</div>

			{/* Page navigation */}
			<div className="flex items-center gap-1">
				{/* Prev */}
				<button
					className="px-3 py-1.5 rounded text-sm font-medium transition-colors"
					style={{
						background: "var(--btn-ghost-bg)",
						color: page <= 1 ? "var(--text-tertiary)" : "var(--btn-ghost-text)",
						border: "1px solid var(--border-default)",
						cursor: page <= 1 ? "not-allowed" : "pointer",
						opacity: page <= 1 ? 0.5 : 1,
					}}
					disabled={page <= 1}
					onClick={() => onPageChange(page - 1)}
				>
					上一页
				</button>

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
									p === page ? "var(--btn-primary-bg)" : "var(--btn-ghost-bg)",
								color:
									p === page
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
				<button
					className="px-3 py-1.5 rounded text-sm font-medium transition-colors"
					style={{
						background: "var(--btn-ghost-bg)",
						color:
							page >= totalPages
								? "var(--text-tertiary)"
								: "var(--btn-ghost-text)",
						border: "1px solid var(--border-default)",
						cursor: page >= totalPages ? "not-allowed" : "pointer",
						opacity: page >= totalPages ? 0.5 : 1,
					}}
					disabled={page >= totalPages}
					onClick={() => onPageChange(page + 1)}
				>
					下一页
				</button>

				{/* Total info */}
				<span className="ml-3" style={{ color: "var(--text-tertiary)" }}>
					共 {total} 条
				</span>
			</div>
		</div>
	);
}

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

	const half = Math.floor((maxVisible - 2) / 2); // pages on each side of current
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
