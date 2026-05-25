import type { ScriptCheckResult } from "../types";

interface Props {
  script: string;
  checks: ScriptCheckResult | null;
  onApprove: () => void;
  onReject: () => void;
  onRegenerate: () => void;
}

export default function ScriptPreview({
  script,
  checks,
  onApprove,
  onReject,
  onRegenerate,
}: Props) {
  return (
    <div>
      <div className="text-sm font-semibold mb-2">口播脚本</div>
      <div className="bg-white border border-[#393f46] rounded-lg p-4 mb-3 text-sm leading-relaxed min-h-[60px]">
        {script || "暂无脚本"}
      </div>
      {checks && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs mb-4">
          <span className={checks.length >= 150 && checks.length <= 200 ? "text-[#1a7f37]" : "text-[#d1242f]"}>
            字数: {checks.length} {checks.length >= 150 && checks.length <= 200 ? "\u2713" : "\u2717"}
          </span>
          <span
            className={checks.brand_name_count >= 1 ? "text-[#1a7f37]" : "text-[#d1242f]"}
          >
            品牌"滋元堂": {checks.brand_name_count}次
          </span>
          <span
            className={checks.product_name_count >= 1 ? "text-[#1a7f37]" : "text-[#d1242f]"}
          >
            品名: {checks.product_name_count}次
          </span>
          <span className={checks.has_safety_warning ? "text-[#1a7f37]" : "text-[#d1242f]"}>
            充分烹熟: {checks.has_safety_warning ? "\u2713" : "\u2717"}
          </span>
          <span className={!checks.has_emoji ? "text-[#1a7f37]" : "text-[#d1242f]"}>
            禁emoji: {!checks.has_emoji ? "\u2713" : "\u2717"}
          </span>
          {checks.forbidden_terms.length > 0 && (
            <span className="text-[#d1242f]">禁词: {checks.forbidden_terms.join(", ")}</span>
          )}
        </div>
      )}
      <div className="flex gap-1.5 flex-wrap">
        <button
          className="bg-[#0969da] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
          onClick={onApprove}
        >
          {"\u2713"} 通过
        </button>
        <button
          className="bg-[#d1242f] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
          onClick={onReject}
        >
          {"\u2717"} 打回
        </button>
        <button
          className="bg-white border border-[#393f46] px-4 py-2 rounded-md text-xs hover:bg-gray-50 transition-all"
          onClick={onRegenerate}
        >
          {"\U0001F504"} 重生成脚本
        </button>
      </div>
    </div>
  );
}
