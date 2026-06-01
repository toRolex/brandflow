import { useState } from "react";

const CATEGORIES = [
  "产地溯源",
  "筛选分拣",
  "清洗泡发",
  "切配处理",
  "下锅入锅",
  "烹饪翻炒",
  "出锅装盘",
  "成品展示",
  "试吃品尝",
  "产品特写",
];

interface Props {
  count: number;
  onEnable: () => void;
  onDisable: () => void;
  onClear: () => void;
  onBatchEdit?: (fields: { product?: string; category?: string }) => void;
}

export default function BatchActionBar({ count, onEnable, onDisable, onClear, onBatchEdit }: Props) {
  const [showEdit, setShowEdit] = useState(false);
  const [editProduct, setEditProduct] = useState("");
  const [editCategory, setEditCategory] = useState("");

  const handleSave = () => {
    if (!onBatchEdit) return;
    const fields: { product?: string; category?: string } = {};
    if (editProduct.trim()) fields.product = editProduct.trim();
    if (editCategory) fields.category = editCategory;
    if (Object.keys(fields).length > 0) {
      onBatchEdit(fields);
    }
    setShowEdit(false);
    setEditProduct("");
    setEditCategory("");
  };

  return (
    <div className="bg-blue-50 border border-blue-500 rounded-lg px-4 py-2 mb-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-blue-700">已选择 {count} 张卡片</span>
        <div className="flex gap-2">
          {onBatchEdit && (
            <button
              className="px-3 py-1 text-xs rounded-md bg-green-600 text-white hover:bg-green-700"
              onClick={() => setShowEdit(!showEdit)}
            >
              批量编辑
            </button>
          )}
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

      {showEdit && (
        <div className="mt-3 pt-3 border-t border-blue-200 flex gap-4 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">产品名称（留空则不修改）</label>
            <input
              type="text"
              className="border rounded px-2 py-1 text-sm w-40"
              value={editProduct}
              onChange={(e) => setEditProduct(e.target.value)}
              placeholder="如：荔枝菌"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">分类（留空则不修改）</label>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={editCategory}
              onChange={(e) => setEditCategory(e.target.value)}
            >
              <option value="">不修改</option>
              {CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>
          <button
            className="px-3 py-1 text-xs rounded-md bg-green-600 text-white hover:bg-green-700"
            onClick={handleSave}
          >
            应用
          </button>
          <button
            className="px-3 py-1 text-xs rounded-md text-gray-500 hover:text-gray-700"
            onClick={() => setShowEdit(false)}
          >
            取消
          </button>
        </div>
      )}
    </div>
  );
}
