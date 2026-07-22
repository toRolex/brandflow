import { useState } from "react";

interface Props {
	count: number;
	label?: string | ((count: number) => string);
	onEnable?: () => void;
	onDisable?: () => void;
	onDelete: () => void;
	onClear: () => void;
	onBatchEdit?: (fields: { product?: string; category?: string }) => void;
	onReclassify?: (category: string) => void;
	categories?: string[];
	hasUnmappedReclassifyTargets?: boolean;
}

export default function BatchActionBar({
	count,
	label,
	onEnable,
	onDisable,
	onDelete,
	onClear,
	onBatchEdit,
	onReclassify,
	categories = [],
	hasUnmappedReclassifyTargets = false,
}: Props) {
	const labelText =
		typeof label === "function"
			? label(count)
			: (label ?? `已选择 ${count} 张卡片`);
	const [showEdit, setShowEdit] = useState(false);
	const [editProduct, setEditProduct] = useState("");
	const [editCategory, setEditCategory] = useState("");

	const [showReclassify, setShowReclassify] = useState(false);
	const [reclassifyCategory, setReclassifyCategory] = useState("");

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

	const handleReclassify = () => {
		if (!onReclassify || !reclassifyCategory) return;
		onReclassify(reclassifyCategory);
		setShowReclassify(false);
		setReclassifyCategory("");
	};

	return (
		<div className="bg-blue-50 border border-blue-500 rounded-lg px-4 py-2 mb-3">
			<div className="flex items-center justify-between">
				<span className="text-sm font-semibold text-blue-700">{labelText}</span>
				<div className="flex gap-2">
					{onReclassify && hasUnmappedReclassifyTargets && (
						<button
							className="px-3 py-1 text-xs rounded-md bg-purple-600 text-white hover:bg-purple-700"
							onClick={() => setShowReclassify(!showReclassify)}
						>
							归类到...
						</button>
					)}
					{onBatchEdit && (
						<button
							className="px-3 py-1 text-xs rounded-md bg-green-600 text-white hover:bg-green-700"
							onClick={() => setShowEdit(!showEdit)}
						>
							批量编辑
						</button>
					)}
					{onDisable && (
						<button
							className="px-3 py-1 text-xs rounded-md bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] hover:bg-[var(--btn-danger-hover)]"
							onClick={onDisable}
						>
							批量禁用
						</button>
					)}
					{onEnable && (
						<button
							className="px-3 py-1 text-xs rounded-md bg-blue-600 text-white hover:bg-blue-700"
							onClick={onEnable}
						>
							批量启用
						</button>
					)}
					<button
						className="px-3 py-1 text-xs rounded-md bg-red-800 text-white hover:bg-red-900"
						onClick={onDelete}
					>
						批量删除
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
						<label className="block text-xs text-gray-500 mb-1">
							产品名称（留空则不修改）
						</label>
						<input
							type="text"
							className="border rounded px-2 py-1 text-sm w-40"
							value={editProduct}
							onChange={(e) => setEditProduct(e.target.value)}
							placeholder="如：龙井茶"
						/>
					</div>
					<div>
						<label className="block text-xs text-gray-500 mb-1">
							分类（留空则不修改）
						</label>
						<select
							className="border rounded px-2 py-1 text-sm"
							value={editCategory}
							onChange={(e) => setEditCategory(e.target.value)}
						>
							<option value="">不修改</option>
							{categories.map((cat) => (
								<option key={cat} value={cat}>
									{cat}
								</option>
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

			{showReclassify && (
				<div className="mt-3 pt-3 border-t border-blue-200 flex gap-4 items-end">
					<div>
						<label className="block text-xs text-gray-500 mb-1">目标分类</label>
						<select
							className="border rounded px-2 py-1 text-sm"
							value={reclassifyCategory}
							onChange={(e) => setReclassifyCategory(e.target.value)}
						>
							<option value="">请选择分类</option>
							{categories.map((cat) => (
								<option key={cat} value={cat}>
									{cat}
								</option>
							))}
						</select>
					</div>
					<button
						className="px-3 py-1 text-xs rounded-md bg-purple-600 text-white hover:bg-purple-700"
						onClick={handleReclassify}
					>
						确认归类
					</button>
					<button
						className="px-3 py-1 text-xs rounded-md text-gray-500 hover:text-gray-700"
						onClick={() => setShowReclassify(false)}
					>
						取消
					</button>
				</div>
			)}
		</div>
	);
}
