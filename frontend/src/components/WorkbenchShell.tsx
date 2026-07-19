import type { ReactNode } from "react";

interface WorkbenchShellProps {
	projectName: string;
	projectId: string;
	error: string;
	onDismissError: () => void;
	onBack: () => void;
	children: ReactNode;
}

export default function WorkbenchShell({
	projectName,
	projectId,
	error,
	onDismissError,
	onBack,
	children,
}: WorkbenchShellProps) {
	return (
		<div>
			{/* breadcrumb */}
			<div className="flex items-center gap-2 mb-6">
				<button
					className="text-sm"
					style={{ color: "var(--text-secondary)" }}
					onClick={onBack}
				>
					&#8592; 项目列表
				</button>
				<span style={{ color: "var(--text-secondary)" }}>|</span>
				<h1
					className="text-lg font-bold"
					style={{ color: "var(--text-primary)" }}
				>
					{projectName || projectId}
				</h1>
			</div>

			{/* error banner */}
			{error && (
				<div
					className="mb-4 px-4 py-3 rounded-lg text-sm flex items-center justify-between"
					style={{
						background: "var(--alert-red-muted)",
						border: "1px solid var(--danger)",
						color: "var(--danger)",
					}}
				>
					<span>{error}</span>
					<button
						onClick={onDismissError}
						className="text-lg leading-none"
						style={{ color: "var(--danger)", opacity: 0.7 }}
					>
						&times;
					</button>
				</div>
			)}

			{children}
		</div>
	);
}
