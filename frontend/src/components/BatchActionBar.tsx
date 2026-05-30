interface Props {
  count: number;
  onEnable: () => void;
  onDisable: () => void;
  onClear: () => void;
}

export default function BatchActionBar({ count, onEnable, onDisable, onClear }: Props) {
  return (
    <div className="flex items-center justify-between bg-blue-50 border border-blue-500 rounded-lg px-4 py-2 mb-3">
      <span className="text-sm font-semibold text-blue-700">已选择 {count} 张卡片</span>
      <div className="flex gap-2">
        <button
          className="px-3 py-1 text-xs rounded-md bg-red-600 text-white hover:bg-red-700"
          onClick={onDisable}
        >
          批量禁用
        </button>
        <button
          className="px-3 py-1 text-xs rounded-md bg-blue-600 text-white hover:bg-blue-700"
          onClick={onEnable}
        >
          批量启用
        </button>
        <button
          className="px-3 py-1 text-xs rounded-md text-gray-500 hover:text-gray-700"
          onClick={onClear}
        >
          取消选择
        </button>
      </div>
    </div>
  );
}
