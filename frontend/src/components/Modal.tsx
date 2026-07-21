import { useEffect } from "react";

interface ModalProps {
  isOpen: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

export default function Modal({ isOpen, title, onClose, children }: ModalProps) {
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
      className="fixed inset-0 flex items-center justify-center"
      style={{ zIndex: "var(--z-modal)" }}
    >
      <div
        className="absolute inset-0"
        style={{ background: "var(--shadow-modal-backdrop)" }}
        onClick={onClose}
      />
      <div
        className="relative rounded-xl p-6 min-w-[400px] max-w-[520px]"
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-default)",
          boxShadow: "var(--shadow-modal)",
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3
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
        {children}
      </div>
    </div>
  );
}
