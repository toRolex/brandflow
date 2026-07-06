import { useEffect, useRef } from "react";

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = "确认",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isOpen) confirmRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center"
      style={{ zIndex: "var(--z-modal)" }}
    >
      {/* backdrop */}
      <div
        className="absolute inset-0"
        style={{ background: "var(--shadow-modal-backdrop)" }}
        onClick={onCancel}
      />
      {/* dialog */}
      <div
        className="relative rounded-xl p-6 min-w-[360px] max-w-[480px]"
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-default)",
          boxShadow: "var(--shadow-modal)",
        }}
      >
        <h3
          className="text-[15px] font-semibold mb-2"
          style={{ color: "var(--text-primary)" }}
        >
          {title}
        </h3>
        <p
          className="text-sm mb-6"
          style={{ color: "var(--text-secondary)" }}
        >
          {message}
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            className="px-4 py-2 text-sm rounded-lg transition-colors"
            style={{
              background: "var(--btn-ghost-bg)",
              color: "var(--btn-ghost-text)",
              border: "1px solid var(--border-default)",
            }}
            onClick={onCancel}
          >
            取消
          </button>
          <button
            ref={confirmRef}
            type="button"
            className="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
            style={{
              background: danger ? "var(--btn-danger-bg)" : "var(--btn-primary-bg)",
              color: danger ? "var(--btn-danger-text)" : "var(--btn-primary-text)",
            }}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
