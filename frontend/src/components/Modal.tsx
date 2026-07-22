import { useEffect, useId } from "react";

interface ModalProps {
	isOpen: boolean;
	title: string;
	onClose: () => void;
	children: React.ReactNode;
	size?: "default" | "wide";
}

export default function Modal({
	isOpen,
	title,
	onClose,
	children,
	size = "default",
}: ModalProps) {
	const titleId = useId();

	useEffect(() => {
		if (!isOpen) return;
		const handleKey = (e: KeyboardEvent) => {
			if (e.key === "Escape") onClose();
		};
		window.addEventListener("keydown", handleKey);
		return () => window.removeEventListener("keydown", handleKey);
	}, [isOpen, onClose]);

	if (!isOpen) return null;

	return (
		<div
			className="fixed inset-0 flex items-center justify-center overflow-y-auto p-3 sm:p-6"
			style={{ zIndex: "var(--z-modal)" }}
			role="dialog"
			aria-modal="true"
			aria-labelledby={titleId}
		>
			<div
				className="absolute inset-0"
				style={{ background: "var(--shadow-modal-backdrop)" }}
				onClick={onClose}
			/>
			<div
				className={`relative my-auto flex max-h-full w-full flex-col rounded-xl p-4 sm:p-6 ${
					size === "wide" ? "max-w-5xl" : "max-w-[520px]"
				}`}
				style={{
					background: "var(--bg-card)",
					border: "1px solid var(--border-default)",
					boxShadow: "var(--shadow-modal)",
				}}
			>
				<div className="mb-4 flex shrink-0 items-center justify-between">
					<h3
						id={titleId}
						className="text-[15px] font-semibold"
						style={{ color: "var(--text-primary)" }}
					>
						{title}
					</h3>
					<button
						className="text-sm hover:opacity-70"
						style={{ color: "var(--text-tertiary)" }}
						onClick={onClose}
						aria-label="关闭"
						type="button"
					>
						✕
					</button>
				</div>
				<div className="min-h-0 overflow-y-auto overscroll-contain pr-1">
					{children}
				</div>
			</div>
		</div>
	);
}
