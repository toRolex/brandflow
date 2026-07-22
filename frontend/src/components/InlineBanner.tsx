import { useEffect, useState } from "react";

interface InlineBannerProps {
	type: "success" | "error";
	message: string;
	onClose: () => void;
	/** Auto-hide duration in ms. Default: 3000 for success, 0 (no auto-hide) for error */
	autoHideMs?: number;
}

export default function InlineBanner({
	type,
	message,
	onClose,
	autoHideMs,
}: InlineBannerProps) {
	const [visible, setVisible] = useState(true);

	useEffect(() => {
		// Reset visibility when message changes (new banner)
		setVisible(true);
	}, [message, type]);

	useEffect(() => {
		const duration = autoHideMs ?? (type === "success" ? 3000 : 0);
		if (duration <= 0) return;
		const timer = setTimeout(() => {
			setVisible(false);
			onClose();
		}, duration);
		return () => clearTimeout(timer);
	}, [type, message, autoHideMs, onClose]);

	if (!visible) return null;

	const isError = type === "error";
	return (
		<div
			className={`mb-4 px-4 py-3 rounded-lg text-sm flex items-center justify-between ${
				isError
					? "bg-[var(--danger-bg)] border border-[var(--danger-border)] text-[var(--danger)]"
					: "bg-[var(--success-bg)] border border-[var(--success-border)] text-[var(--success)]"
			}`}
			role="alert"
		>
			<span>{message}</span>
			<button
				className="ml-4 text-sm font-medium hover:opacity-70 flex-shrink-0"
				onClick={() => {
					setVisible(false);
					onClose();
				}}
				aria-label="关闭"
				type="button"
			>
				✕
			</button>
		</div>
	);
}
