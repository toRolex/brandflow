import { useEffect, useRef, useState } from "react";
import { useProducts } from "../ProductContext";

export default function ProductSelector() {
	const { products, activeProductId, activeProductName, switchProduct } =
		useProducts();
	const [open, setOpen] = useState(false);
	const ref = useRef<HTMLDivElement>(null);

	useEffect(() => {
		function handleClickOutside(e: MouseEvent) {
			if (ref.current && !ref.current.contains(e.target as Node)) {
				setOpen(false);
			}
		}
		document.addEventListener("mousedown", handleClickOutside);
		return () => document.removeEventListener("mousedown", handleClickOutside);
	}, []);

	const displayName = activeProductName || "选择产品";

	if (products.length === 0) {
		return (
			<div
				className="text-xs px-2 py-1 italic"
				style={{ color: "var(--text-secondary)" }}
			>
				暂未配置产品
			</div>
		);
	}

	return (
		<div className="relative" ref={ref}>
			<button
				className="flex items-center gap-1.5 px-2.5 py-1.5 text-sm font-medium rounded-lg border hover:bg-gray-50 transition-colors min-w-[100px]"
				style={{
					borderColor: "var(--border-default)",
					background: "var(--bg-card)",
				}}
				onClick={() => setOpen(!open)}
			>
				<span className="truncate max-w-[120px]">{displayName}</span>
				<svg
					className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : ""}`}
					style={{ color: "var(--text-secondary)" }}
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						strokeLinecap="round"
						strokeLinejoin="round"
						strokeWidth={2}
						d="M19 9l-7 7-7-7"
					/>
				</svg>
			</button>

			{open && (
				<div
					className="absolute top-full left-0 mt-1 w-48 border rounded-lg shadow-lg z-50 py-1"
					style={{
						background: "var(--bg-card)",
						borderColor: "var(--border-default)",
					}}
				>
					{products.map((p) => (
						<button
							key={p.id}
							className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors ${
								p.id === activeProductId ? "font-medium" : ""
							}`}
							style={
								p.id === activeProductId
									? {
											color: "var(--accent)",
											background: "var(--bg-nav-active)",
										}
									: { color: "var(--text-primary)" }
							}
							onClick={async () => {
								await switchProduct(p.id);
								setOpen(false);
								window.location.reload();
							}}
						>
							{p.name || p.id}
						</button>
					))}
				</div>
			)}
		</div>
	);
}
