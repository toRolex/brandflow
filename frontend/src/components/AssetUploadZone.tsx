import { useMemo, useRef, useState } from "react";

interface Props {
	accept?: string;
	disabled?: boolean;
	onConfirm: (files: File[]) => Promise<void> | void;
}

export default function AssetUploadZone({
	accept = "video/*",
	disabled = false,
	onConfirm,
}: Props) {
	const inputRef = useRef<HTMLInputElement | null>(null);
	const [pendingFiles, setPendingFiles] = useState<File[]>([]);
	const [isConfirming, setIsConfirming] = useState(false);

	const totalSize = useMemo(
		() => pendingFiles.reduce((sum, file) => sum + file.size, 0),
		[pendingFiles],
	);

	const enqueueFiles = (fileList: FileList | null) => {
		if (!fileList || fileList.length === 0) return;
		const incoming = Array.from(fileList);
		setPendingFiles((prev) => {
			const map = new Map<string, File>();
			for (const file of prev) {
				map.set(`${file.name}:${file.size}:${file.lastModified}`, file);
			}
			for (const file of incoming) {
				map.set(`${file.name}:${file.size}:${file.lastModified}`, file);
			}
			return Array.from(map.values());
		});
	};

	const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		enqueueFiles(e.target.files);
		e.target.value = "";
	};

	const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		if (disabled || isConfirming) return;
		enqueueFiles(e.dataTransfer.files);
	};

	const handleConfirm = async () => {
		if (pendingFiles.length === 0 || disabled || isConfirming) return;
		setIsConfirming(true);
		try {
			await onConfirm(pendingFiles);
			setPendingFiles([]);
		} finally {
			setIsConfirming(false);
		}
	};

	const removePendingFile = (key: string) => {
		setPendingFiles((prev) =>
			prev.filter(
				(file) => `${file.name}:${file.size}:${file.lastModified}` !== key,
			),
		);
	};

	const formatSize = (bytes: number) => {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	};

	return (
		<section
			className="border rounded-xl p-4"
			style={{ background: "var(--bg-card)" }}
		>
			<div className="flex items-center justify-between mb-3">
				<h3 className="text-sm font-semibold">素材批量上传</h3>
				<button
					type="button"
					className="text-sm hover:underline disabled:text-[var(--text-tertiary)] disabled:no-underline"
					style={{ color: "var(--accent)" }}
					onClick={() => inputRef.current?.click()}
					disabled={disabled || isConfirming}
				>
					选择文件
				</button>
			</div>

			<div
				className="border-2 border-dashed rounded-lg p-6 text-center text-sm"
				style={{
					borderColor: "var(--border-default)",
					color: "var(--text-secondary)",
					background: "var(--bg-page)",
				}}
				onDragOver={(e) => e.preventDefault()}
				onDrop={handleDrop}
			>
				拖拽文件到此处，或点击“选择文件”批量添加
			</div>

			<input
				ref={inputRef}
				type="file"
				accept={accept}
				multiple={true}
				className="hidden"
				onChange={handleFileChange}
			/>

			<div className="mt-4">
				<div
					className="flex items-center justify-between text-xs mb-2"
					style={{ color: "var(--text-secondary)" }}
				>
					<span>待入库列表（{pendingFiles.length}）</span>
					<span>总大小：{formatSize(totalSize)}</span>
				</div>

				{pendingFiles.length === 0 ? (
					<div
						className="text-xs border rounded-lg px-3 py-2"
						style={{ color: "var(--text-tertiary)" }}
					>
						暂无待入库素材
					</div>
				) : (
					<ul className="border rounded-lg divide-y max-h-48 overflow-auto">
						{pendingFiles.map((file) => {
							const key = `${file.name}:${file.size}:${file.lastModified}`;
							return (
								<li
									key={key}
									className="px-3 py-2 flex items-center justify-between text-sm"
								>
									<div className="min-w-0">
										<p className="truncate" title={file.name}>
											{file.name}
										</p>
										<p
											className="text-xs"
											style={{ color: "var(--text-secondary)" }}
										>
											{formatSize(file.size)}
										</p>
									</div>
									<button
										type="button"
										className="text-xs hover:underline ml-3"
										style={{ color: "var(--danger)" }}
										onClick={() => removePendingFile(key)}
										disabled={disabled || isConfirming}
									>
										移除
									</button>
								</li>
							);
						})}
					</ul>
				)}
			</div>

			<div className="mt-4 flex justify-end">
				<button
					type="button"
					className="text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
					style={{ background: "var(--btn-primary-bg)" }}
					onClick={handleConfirm}
					disabled={disabled || isConfirming || pendingFiles.length === 0}
				>
					{isConfirming ? "入库中..." : "确认入库"}
				</button>
			</div>
		</section>
	);
}
