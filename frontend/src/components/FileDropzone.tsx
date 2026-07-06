import { useCallback, useState, type DragEvent } from "react";

interface Props {
  onFile: (file: File) => void;
  accept?: string;
}

export default function FileDropzone({ onFile, accept = "video/*" }: Props) {
  const [over, setOver] = useState(false);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setOver(false);
      const file = e.dataTransfer.files[0];
      if (file) onFile(file);
    },
    [onFile]
  );

  const handleClick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) onFile(file);
    };
    input.click();
  };

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
        over
          ? "border-blue-500 bg-blue-50"
          : "border-[var(--border-default)] bg-[var(--bg-page)] hover:border-gray-400"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={handleDrop}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") handleClick();
      }}
      aria-label="点击或拖拽上传视频文件"
    >
      <div className="text-2xl mb-1">📁</div>
      <div className="text-sm">
        拖拽视频文件到此处，或{" "}
        <span className="text-blue-600 underline">点击选择文件</span>
      </div>
      <div className="text-xs text-gray-500 mt-1">支持 .mp4 / .mov / .avi</div>
    </div>
  );
}
