import { useRef } from "react";
import { splitScriptText } from "../utils/batchScriptSplit";

interface Props {
  onScripts: (scripts: string[]) => void;
}

export default function BatchScriptUploader({ onScripts }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = String(event.target?.result ?? "");
      const scripts = splitScriptText(text);
      onScripts(scripts);
    };
    reader.readAsText(file);

    // 允许重复上传同一文件
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  return (
    <label className="inline-flex items-center gap-2 px-3 py-1.5 text-sm border-2 border-dashed border-gray-300 rounded-lg text-gray-600 hover:border-gray-400 cursor-pointer transition-colors">
      <input
        ref={inputRef}
        type="file"
        accept=".txt"
        className="hidden"
        onChange={handleChange}
        aria-label="上传文案文件"
      />
      上传文案文件
    </label>
  );
}
