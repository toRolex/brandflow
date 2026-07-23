import type { PhasePresentation } from "../phasePresentation";

export default function PhaseStatusNotice({
	presentation,
}: {
	presentation: PhasePresentation;
}) {
	const isError = ["integrity_error", "recoverable_error", "failed"].includes(
		presentation.kind,
	);
	const isRetrying = presentation.kind === "retrying";

	return (
		<div
			className="mb-4 rounded-lg border p-3"
			style={{
				borderColor: isError
					? "var(--alert-red)"
					: isRetrying
						? "var(--color-caution-amber)"
						: "var(--border-default)",
				background: isError ? "var(--alert-red-muted)" : "var(--bg-table-head)",
			}}
		>
			<p
				className="text-sm font-medium"
				style={{ color: isError ? "var(--alert-red)" : undefined }}
			>
				{presentation.title}
			</p>
			<p className="mt-1 text-xs text-[var(--text-secondary)]">
				{presentation.detail}
			</p>
		</div>
	);
}
