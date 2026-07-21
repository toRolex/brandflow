interface InlineBannerProps {
	type: "success" | "error";
	message: string;
	onClose?: () => void;
}

export default function InlineBanner({
	type,
	message,
	onClose,
}: InlineBannerProps) {
	const isError = type === "error";
	return (
		<div
			role="status"
			className="rounded-lg px-4 py-3 mb-4 border flex items-start justify-between gap-3"
			style={{
				background: isError ? "var(--error-bg)" : "var(--success-bg)",
				borderColor: isError ? "var(--error-border)" : "var(--success-border)",
				color: isError ? "var(--error-text)" : "var(--success-text)",
			}}
		>
			<span className="text-sm font-medium">{message}</span>
			{onClose && (
				<button
					type="button"
					onClick={onClose}
					className="text-sm leading-none"
					style={{
						color: isError ? "var(--error-text)" : "var(--success-text)",
						opacity: 0.7,
					}}
					aria-label="关闭"
					onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
					onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.7")}
				>
					✕
				</button>
			)}
		</div>
	);
}
