import type { ReactNode } from "react";
import type {
	PhasePresentation,
	PresentationSeverity,
} from "../../../policies/phasePresentation";

interface PhaseStatePresenterProps {
	presentation: PhasePresentation;
	onRetry?: () => void;
	onApprove?: () => void;
	onReject?: () => void;
	onReload?: () => void;
	onDiagnose?: () => void;
	children?: ReactNode;
}

const SEVERITY_BORDER: Record<PresentationSeverity, string> = {
	info: "var(--border-default)",
	success: "var(--color-signal-green)",
	warning: "var(--color-caution-amber)",
	error: "var(--alert-red)",
};

const SEVERITY_BG: Record<PresentationSeverity, string> = {
	info: "var(--bg-table-head)",
	success: "var(--color-signal-green-bg, rgba(34,197,94,0.1))",
	warning: "var(--color-caution-amber-bg, rgba(245,158,11,0.1))",
	error: "var(--alert-red-bg, rgba(239,68,68,0.1))",
};

const SEVERITY_TEXT: Record<PresentationSeverity, string> = {
	info: "var(--text-secondary)",
	success: "var(--color-signal-green)",
	warning: "var(--color-caution-amber)",
	error: "var(--alert-red)",
};

function isSuccessLike(type: PhasePresentation["type"]): boolean {
	return (
		type === "succeeded" ||
		type === "review_ready" ||
		type === "review_completed" ||
		type === "completed"
	);
}

export default function PhaseStatePresenter({
	presentation,
	onRetry,
	onApprove,
	onReject,
	onReload,
	onDiagnose,
	children,
}: PhaseStatePresenterProps) {
	if (isSuccessLike(presentation.type)) {
		return children;
	}

	const { title, message, severity, actions } = presentation;
	const showAttempt =
		presentation.retryAttempt !== undefined &&
		presentation.maxRetryAttempts !== undefined;

	return (
		<div
			className="rounded-lg border p-3 mb-3"
			style={{
				borderColor: SEVERITY_BORDER[severity],
				background: SEVERITY_BG[severity],
			}}
		>
			<p
				className="text-sm font-medium mb-1"
				style={{ color: SEVERITY_TEXT[severity] }}
			>
				{title}
			</p>
			<p className="text-xs" style={{ color: "var(--text-secondary)" }}>
				{message}
			</p>
			{showAttempt && (
				<p className="text-xs mt-1" style={{ color: "var(--text-tertiary)" }}>
					第 {presentation.retryAttempt} / {presentation.maxRetryAttempts}{" "}
					次尝试
				</p>
			)}
			{actions.length > 0 && (
				<div className="flex flex-wrap gap-2 mt-3">
					{actions.map((action) => {
						const key = action.key;
						const common =
							"px-3 py-1.5 rounded-md text-xs font-medium transition-all";
						const primary =
							"bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] hover:brightness-110";
						const secondary =
							"border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]";
						const isPrimary =
							key === "retry" || key === "approve" || key === "review";

						let onClick: (() => void) | undefined;
						if (key === "retry") onClick = onRetry;
						else if (key === "approve") onClick = onApprove;
						else if (key === "reject") onClick = onReject;
						else if (key === "reload") onClick = onReload;
						else if (key === "diagnose") onClick = onDiagnose;

						return (
							<button
								key={key}
								type="button"
								className={`${common} ${isPrimary ? primary : secondary}`}
								onClick={onClick}
								disabled={!onClick}
							>
								{action.label}
							</button>
						);
					})}
				</div>
			)}
		</div>
	);
}
