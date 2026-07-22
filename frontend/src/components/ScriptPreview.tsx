import { useState } from "react";
import type { ProductionMode, ScriptCheckResult } from "../types";

interface Props {
	script: string;
	checks: ScriptCheckResult | null;
	brand?: string;
	safetyWarningText?: string;
	mode?: ProductionMode;
	reviewEnabled?: boolean;
	onApprove: () => void;
	onReject: () => void;
	onRegenerate: () => void;
	onEdit: (newScript: string) => void;
	onRegenerateWithPrompt: (prompt: string) => void;
}

export default function ScriptPreview({
	script,
	checks,
	brand,
	safetyWarningText,
	mode,
	reviewEnabled = true,
	onApprove,
	onReject,
	onRegenerate,
	onEdit,
	onRegenerateWithPrompt,
}: Props) {
	const [isEditing, setIsEditing] = useState(false);
	const [editText, setEditText] = useState(script);
	const [showPromptInput, setShowPromptInput] = useState(false);
	const [customPrompt, setCustomPrompt] = useState("");

	const handleSaveEdit = () => {
		onEdit(editText);
		setIsEditing(false);
	};

	const handleCancelEdit = () => {
		setEditText(script);
		setIsEditing(false);
	};

	const handleRegenerateWithPrompt = () => {
		if (customPrompt.trim()) {
			onRegenerateWithPrompt(customPrompt.trim());
			setCustomPrompt("");
			setShowPromptInput(false);
		}
	};

	return (
		<div>
			<div className="text-sm font-semibold mb-2">口播脚本</div>

			{isEditing ? (
				<div className="mb-3">
					<textarea
						className="w-full bg-white border border-[var(--border-default)] rounded-lg p-4 text-sm leading-relaxed min-h-[120px] focus:outline-none focus:border-[var(--color-electric-blue)] resize-y"
						value={editText}
						onChange={(e) => setEditText(e.target.value)}
					/>
					<div className="flex gap-1.5 mt-2">
						<button
							className="bg-[var(--btn-primary-bg)] text-white border-none px-3 py-1.5 rounded-md text-xs hover:brightness-110 transition-all"
							onClick={handleSaveEdit}
						>
							保存
						</button>
						<button
							className="bg-white border border-[var(--border-default)] px-3 py-1.5 rounded-md text-xs hover:bg-gray-50 transition-all"
							onClick={handleCancelEdit}
						>
							取消
						</button>
					</div>
				</div>
			) : (
				<div className="bg-white border border-[var(--border-default)] rounded-lg p-4 mb-3 text-sm leading-relaxed min-h-[60px]">
					{script || "暂无脚本"}
				</div>
			)}

			{checks && (
				<div className="flex flex-wrap gap-x-6 gap-y-1 text-xs mb-4">
					<span
						className={
							checks.length >= 150 && checks.length <= 200
								? "text-[var(--color-signal-green)]"
								: "text-[var(--color-alert-red)]"
						}
					>
						字数: {checks.length}{" "}
						{checks.length >= 150 && checks.length <= 200 ? "✓" : "✗"}
					</span>
					{brand && (
						<span
							className={
								checks.brand_name_count >= 1
									? "text-[var(--color-signal-green)]"
									: "text-[var(--color-alert-red)]"
							}
						>
							品牌"{brand}": {checks.brand_name_count}次
						</span>
					)}
					<span
						className={
							checks.product_name_count >= 1
								? "text-[var(--color-signal-green)]"
								: "text-[var(--color-alert-red)]"
						}
					>
						品名: {checks.product_name_count}次
					</span>
					<span
						className={
							checks.has_safety_warning
								? "text-[var(--color-signal-green)]"
								: "text-[var(--color-alert-red)]"
						}
					>
						{safetyWarningText || "安全提示"}:{" "}
						{checks.has_safety_warning ? "✓" : "✗"}
					</span>
					<span
						className={
							checks.has_emoji
								? "text-[var(--color-alert-red)]"
								: "text-[var(--color-signal-green)]"
						}
					>
						禁emoji: {checks.has_emoji ? "✗" : "✓"}
					</span>
					{checks.forbidden_terms.length > 0 && (
						<span className="text-[var(--color-alert-red)]">
							禁词: {checks.forbidden_terms.join(", ")}
						</span>
					)}
				</div>
			)}

			{showPromptInput && (
				<div className="mb-3 p-3 bg-gray-50 border border-[var(--border-default)] rounded-lg">
					<div className="text-xs text-gray-500 mb-2">
						输入提示词，指导 LLM 重新生成脚本：
					</div>
					<textarea
						className="w-full bg-white border border-[var(--border-default)] rounded p-2 text-sm min-h-[60px] focus:outline-none focus:border-[var(--color-electric-blue)] resize-y"
						placeholder="例如：语气更活泼一些，加入更多互动感..."
						value={customPrompt}
						onChange={(e) => setCustomPrompt(e.target.value)}
					/>
					<div className="flex gap-1.5 mt-2">
						<button
							className="bg-[var(--btn-primary-bg)] text-white border-none px-3 py-1.5 rounded-md text-xs hover:brightness-110 transition-all"
							onClick={handleRegenerateWithPrompt}
						>
							生成
						</button>
						<button
							className="bg-white border border-[var(--border-default)] px-3 py-1.5 rounded-md text-xs hover:bg-gray-50 transition-all"
							onClick={() => setShowPromptInput(false)}
						>
							取消
						</button>
					</div>
				</div>
			)}

			{mode === "import" ? (
				<div className="text-xs text-gray-500 mb-2">
					此 Job 为手动导入模式，脚本仅供查看
				</div>
			) : (
				<div className="flex gap-1.5 flex-wrap">
					{!reviewEnabled && (
						<div
							className="w-full text-xs mb-1"
							style={{ color: "var(--color-caution-amber)" }}
						>
							当前不在该审核阶段，无法操作
						</div>
					)}
					<button
						className="bg-[var(--btn-primary-bg)] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
						onClick={onApprove}
						disabled={!reviewEnabled}
						aria-disabled={!reviewEnabled}
					>
						{"✓"} 通过
					</button>
					<button
						className="bg-[var(--btn-danger-bg)] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
						onClick={onReject}
						disabled={!reviewEnabled}
						aria-disabled={!reviewEnabled}
					>
						{"✗"} 打回
					</button>
					<button
						className="bg-white border border-[var(--border-default)] px-4 py-2 rounded-md text-xs hover:bg-gray-50 transition-all"
						onClick={onRegenerate}
					>
						{"🔄"} 重生成脚本
					</button>
					<button
						className="bg-white border border-[var(--border-default)] px-4 py-2 rounded-md text-xs hover:bg-gray-50 transition-all"
						onClick={() => {
							setIsEditing(true);
							setEditText(script);
						}}
					>
						{"✏️"} 手动编辑
					</button>
					<button
						className="bg-white border border-[var(--border-default)] px-4 py-2 rounded-md text-xs hover:bg-gray-50 transition-all"
						onClick={() => setShowPromptInput(!showPromptInput)}
					>
						{"📝"} 提示词重生成
					</button>
				</div>
			)}
		</div>
	);
}
