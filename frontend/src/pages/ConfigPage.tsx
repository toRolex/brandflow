import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProviderConfig, ProviderField, ProviderOptions } from "../types";

interface SectionDef {
	key: string;
	label: string;
	color: string;
	icon: (color: string) => React.ReactNode;
	cssVar: string;
}

const SECTIONS: SectionDef[] = [
	{
		key: "llm",
		label: "LLM",
		color: "#3b82f6",
		cssVar: "--section-llm-color",
		icon: (color: string) => (
			<svg
				aria-hidden="true"
				viewBox="0 0 24 24"
				width="18"
				height="18"
				fill="none"
				stroke={color}
				strokeWidth="2"
				strokeLinecap="round"
				strokeLinejoin="round"
			>
				<path d="M12 2L2 7l10 5 10-5-10-5z" />
				<path d="M2 17l10 5 10-5" />
				<path d="M2 12l10 5 10-5" />
			</svg>
		),
	},
	{
		key: "tts",
		label: "TTS",
		color: "#22c55e",
		cssVar: "--section-tts-color",
		icon: (color: string) => (
			<svg
				aria-hidden="true"
				viewBox="0 0 24 24"
				width="18"
				height="18"
				fill="none"
				stroke={color}
				strokeWidth="2"
				strokeLinecap="round"
				strokeLinejoin="round"
			>
				<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
				<path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
				<path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
			</svg>
		),
	},
	{
		key: "vision",
		label: "Vision",
		color: "#7c3aed",
		cssVar: "--section-vision-color",
		icon: (color: string) => (
			<svg
				aria-hidden="true"
				viewBox="0 0 24 24"
				width="18"
				height="18"
				fill="none"
				stroke={color}
				strokeWidth="2"
				strokeLinecap="round"
				strokeLinejoin="round"
			>
				<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
				<circle cx="12" cy="12" r="3" />
			</svg>
		),
	},
	{
		key: "text_to_image",
		label: "文生图",
		color: "#f59e0b",
		cssVar: "--section-text_to_image-color",
		icon: (color: string) => (
			<svg
				aria-hidden="true"
				viewBox="0 0 24 24"
				width="18"
				height="18"
				fill="none"
				stroke={color}
				strokeWidth="2"
				strokeLinecap="round"
				strokeLinejoin="round"
			>
				<rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
				<circle cx="9" cy="9" r="2" />
				<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
			</svg>
		),
	},
	{
		key: "image_to_video",
		label: "图生视频",
		color: "#0891b2",
		cssVar: "--section-image_to_video-color",
		icon: (color: string) => (
			<svg
				aria-hidden="true"
				viewBox="0 0 24 24"
				width="18"
				height="18"
				fill="none"
				stroke={color}
				strokeWidth="2"
				strokeLinecap="round"
				strokeLinejoin="round"
			>
				<rect x="2" y="6" width="20" height="12" rx="2" ry="2" />
				<path d="m10 10 4 2-4 2z" />
			</svg>
		),
	},
];

const inputStyle: React.CSSProperties = {
	backgroundColor: "var(--bg-input)",
	borderColor: "var(--input-border)",
	color: "var(--input-text)",
};

const SECRET_MASK = "***";

const FIELD_HINTS: Record<string, string> = {
	api_key: "仅保存在 .env；更新后需重启后端生效",
	endpoint: "非敏感运行配置，保存后立即生效",
	model: "当前 provider 实际调用的模型",
	thinking: "控制模型是否启用深度思考",
	extra_headers: "JSON 对象，将随 provider 请求发送",
};

function selectFirstProviders(
	c: ProviderConfig,
	o: ProviderOptions,
): ProviderConfig {
	const next = structuredClone(c);
	for (const { key } of SECTIONS) {
		const section = next.providers[key];
		const opts = o.providers[key];
		if (!section || !opts) continue;
		if (!section.selected && opts) {
			const first = Object.keys(opts.providers)[0];
			if (first) {
				section.selected = first;
			}
		}
	}
	return next;
}

function displayFieldValue(value: unknown, field: ProviderField): string {
	if (field.secret && value === SECRET_MASK) return "";
	if (field.kind === "json" && value && typeof value !== "string") {
		return JSON.stringify(value, null, 2);
	}
	return typeof value === "string" ? value : "";
}

export default function ConfigPage() {
	const [config, setConfig] = useState<ProviderConfig | null>(null);
	const [savedConfig, setSavedConfig] = useState<ProviderConfig | null>(null);
	const [options, setOptions] = useState<ProviderOptions | null>(null);
	const [activeTab, setActiveTab] = useState<string>("llm");
	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [dirty, setDirty] = useState(false);
	const [secretChanged, setSecretChanged] = useState(false);
	const [saving, setSaving] = useState(false);
	const [saveMsg, setSaveMsg] = useState<string | null>(null);

	const load = useCallback(async () => {
		setLoading(true);
		setLoadError(null);
		try {
			const [c, o] = await Promise.all([
				api.getConfig(),
				api.getConfigOptions(),
			]);
			const initialized = selectFirstProviders(c, o);
			setConfig(initialized);
			setSavedConfig(structuredClone(initialized));
			setOptions(o);
			setDirty(false);
			setSecretChanged(false);
			setSaveMsg(null);
		} catch (e) {
			setLoadError(
				`加载配置失败：${e instanceof Error ? e.message : "请检查后端服务"}`,
			);
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		load();
	}, [load]);

	const updateField = (
		section: string,
		provider: string,
		field: string,
		value: unknown,
	) => {
		if (!config) return;
		const next = structuredClone(config);
		const sectionData = next.providers[section];
		if (!sectionData.providers[provider]) {
			sectionData.providers[provider] = {};
		}
		sectionData.providers[provider] = {
			...sectionData.providers[provider],
			[field]: value,
		} as Record<string, unknown>;
		setConfig(next);
		setDirty(true);
		if (field === "api_key") setSecretChanged(true);
		setSaveMsg(null);
	};

	const handleSave = async () => {
		if (!config) return;
		setSaving(true);
		setSaveMsg(null);
		try {
			const saved = await api.saveConfig(config);
			const normalized = options ? selectFirstProviders(saved, options) : saved;
			setConfig(normalized);
			setSavedConfig(structuredClone(normalized));
			setDirty(false);
			setSaveMsg(
				secretChanged
					? "业务配置已生效；API Key 更新需重启后端后生效"
					: "配置已保存并立即生效",
			);
			setSecretChanged(false);
		} catch (e) {
			setSaveMsg(`保存失败：${e instanceof Error ? e.message : "未知错误"}`);
		}
		setSaving(false);
	};

	if (loading) {
		return (
			<div
				className="text-center py-12"
				style={{ color: "var(--text-secondary)" }}
			>
				加载配置中...
			</div>
		);
	}

	if (loadError || !config || !options) {
		return (
			<div
				role="alert"
				className="mx-auto max-w-lg rounded-xl border p-6 text-center"
				style={{
					background: "var(--bg-card)",
					borderColor: "var(--danger)",
					color: "var(--text-primary)",
				}}
			>
				<div className="mb-2 font-semibold">无法加载系统配置</div>
				<p className="mb-4 text-sm" style={{ color: "var(--text-secondary)" }}>
					{loadError || "配置响应不完整"}
				</p>
				<button
					type="button"
					className="rounded-lg px-4 py-2 text-sm font-medium"
					style={{ background: "var(--accent)", color: "var(--text-inverse)" }}
					onClick={load}
				>
					重新加载
				</button>
			</div>
		);
	}

	const availableSections = SECTIONS.filter(
		(section) =>
			Object.keys(options.providers[section.key]?.providers || {}).length > 0,
	);
	const activeSection =
		availableSections.find((s) => s.key === activeTab) ?? availableSections[0];
	if (!activeSection) {
		return (
			<div
				className="py-12 text-center"
				style={{ color: "var(--text-secondary)" }}
			>
				暂无可配置的 Provider
			</div>
		);
	}
	const key = activeSection.key;
	const sectionData = config.providers[key];
	const sectionOpts = options.providers[key];
	const selected = sectionData?.selected || "";
	const selectedProfile = sectionData?.providers[selected] || {};
	const selectedFields =
		sectionOpts?.providers[selected]?.fields || ([] as ProviderField[]);
	const secretConfigured = selectedFields.some(
		(field) =>
			field.secret &&
			typeof selectedProfile[field.name] === "string" &&
			selectedProfile[field.name] !== "",
	);
	const selectedModel =
		typeof selectedProfile.model === "string" ? selectedProfile.model : "";

	return (
		<div>
			<div className="mb-6 flex flex-wrap items-start justify-between gap-4">
				<div>
					<div className="flex items-center gap-3">
						<h1
							className="text-xl font-bold"
							style={{ color: "var(--text-primary)" }}
						>
							系统配置
						</h1>
						{dirty && (
							<span
								className="rounded-full px-2 py-1 text-xs font-medium"
								style={{
									background: "var(--alert-yellow-muted)",
									color: "var(--warning)",
								}}
							>
								有未保存的更改
							</span>
						)}
					</div>
					<p
						className="mt-1 text-sm"
						style={{ color: "var(--text-secondary)" }}
					>
						统一管理各项 AI 能力的运行 Provider、模型与凭据
					</p>
				</div>
				<div className="flex items-center gap-2">
					{dirty && savedConfig && (
						<button
							type="button"
							className="rounded-lg border px-3 py-2 text-xs font-medium"
							style={{
								borderColor: "var(--border-default)",
								color: "var(--text-secondary)",
							}}
							onClick={() => {
								setConfig(structuredClone(savedConfig));
								setDirty(false);
								setSecretChanged(false);
								setSaveMsg(null);
							}}
						>
							放弃更改
						</button>
					)}
					<button
						className="rounded-lg px-4 py-2 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
						style={
							saving || !dirty
								? {
										background: "var(--text-tertiary)",
										color: "var(--text-inverse)",
									}
								: {
										background: "var(--accent)",
										color: "var(--text-inverse)",
									}
						}
						disabled={saving || !dirty}
						title={dirty ? "保存所有配置更改" : "没有未保存的更改"}
						onClick={handleSave}
					>
						{saving ? "保存中..." : "保存配置"}
					</button>
				</div>
			</div>

			{saveMsg && (
				<div
					role={saveMsg.includes("失败") ? "alert" : "status"}
					aria-live="polite"
					className="mb-4 px-4 py-3 rounded-lg text-sm border"
					style={
						saveMsg.includes("失败")
							? {
									background: "var(--alert-red-muted)",
									borderColor: "var(--danger)",
									color: "var(--danger)",
								}
							: {
									background: "var(--bg-tag-green)",
									borderColor: "var(--success)",
									color: "var(--success)",
								}
					}
				>
					{saveMsg}
				</div>
			)}

			<div className="mb-6 grid gap-3 md:grid-cols-3">
				{[
					{
						title: "运行配置",
						value: "app_config.json",
						detail: "Provider、模型和 Endpoint 保存后立即生效",
					},
					{
						title: "敏感凭据",
						value: ".env",
						detail: "API Key 不回显，更新后需重启后端",
					},
					{
						title: "旧配置兼容",
						value: "providers.yaml",
						detail: "仅用于旧版本读取，不再作为运行配置源",
					},
				].map((item) => (
					<div
						key={item.title}
						className="rounded-xl border p-3"
						style={{
							background: "var(--bg-card)",
							borderColor: "var(--border-default)",
						}}
					>
						<div
							className="text-xs font-medium"
							style={{ color: "var(--text-tertiary)" }}
						>
							{item.title}
						</div>
						<div
							className="mt-1 font-mono text-sm font-semibold"
							style={{ color: "var(--text-primary)" }}
						>
							{item.value}
						</div>
						<div
							className="mt-1 text-xs"
							style={{ color: "var(--text-secondary)" }}
						>
							{item.detail}
						</div>
					</div>
				))}
			</div>

			<div
				className="mb-6 flex gap-2 overflow-x-auto border-b"
				style={{ borderColor: "var(--border-default)" }}
				role="tablist"
			>
				{availableSections.map(({ key: sectionKey, label, cssVar, icon }) => {
					const active = activeTab === sectionKey;
					const sectionColorVar = `var(${cssVar})`;
					const sectionColorMutedVar = `var(${cssVar}-muted)`;
					return (
						<button
							type="button"
							key={sectionKey}
							role="tab"
							aria-selected={active}
							className="flex items-center gap-[var(--tab-gap,8px)] px-[var(--tab-padding-x,16px)] py-[var(--tab-padding-y,10px)] text-[var(--tab-font-size,0.875rem)] font-medium border-b-2 transition-colors"
							style={{
								borderColor: active ? sectionColorVar : "transparent",
								color: active ? sectionColorVar : "var(--text-secondary)",
								background: active ? sectionColorMutedVar : "transparent",
							}}
							onClick={() => setActiveTab(sectionKey)}
						>
							<span style={{ color: sectionColorVar }}>
								{icon(sectionColorVar)}
							</span>
							{label}
						</button>
					);
				})}
			</div>

			<section
				key={key}
				className="rounded-xl border p-5"
				style={{
					background: "var(--bg-card)",
					borderColor: "var(--border-default)",
				}}
			>
				<div className="mb-5 flex flex-wrap items-start justify-between gap-3">
					<div>
						<h2
							className="font-semibold"
							style={{ color: "var(--text-primary)" }}
						>
							{activeSection.label}
						</h2>
						<p
							className="mt-1 text-xs"
							style={{ color: "var(--text-secondary)" }}
						>
							选择运行时 Provider，并配置它实际使用的连接参数
						</p>
					</div>
					{selected && (
						<div className="flex flex-wrap items-center gap-2 text-xs">
							{selectedModel && (
								<span
									className="rounded-full px-2 py-1"
									style={{
										background: "var(--bg-tag-blue)",
										color: "var(--text-tag-blue)",
									}}
								>
									模型：{selectedModel}
								</span>
							)}
							<span
								className="rounded-full px-2 py-1"
								style={
									secretConfigured
										? {
												background: "var(--bg-tag-green)",
												color: "var(--text-tag-green)",
											}
										: {
												background: "var(--badge-warning-bg)",
												color: "var(--badge-warning-text)",
											}
								}
							>
								{secretConfigured ? "API Key 已配置" : "API Key 未配置"}
							</span>
						</div>
					)}
				</div>

				<label
					className="mb-5 grid gap-1 text-xs"
					style={{ color: "var(--text-secondary)" }}
				>
					运行 Provider
					<select
						className="rounded-lg border px-3 py-2 text-sm"
						style={inputStyle}
						value={selected}
						onChange={(e) => {
							const next = structuredClone(config);
							next.providers[key].selected = e.target.value;
							setConfig(next);
							setDirty(true);
							setSaveMsg(null);
						}}
					>
						<option value="">未选择</option>
						{Object.entries(sectionOpts?.providers || {}).map(([k, v]) => (
							<option key={k} value={k}>
								{(v as { label: string }).label || k}
							</option>
						))}
					</select>
				</label>

				{selected &&
					sectionOpts?.providers[selected] &&
					selectedFields.map((field) => {
						const fieldId = `${key}-${selected}-${field.name}`;
						const rawValue = selectedProfile[field.name];
						const fieldValue = displayFieldValue(rawValue, field);
						const secretIsConfigured =
							field.secret &&
							typeof rawValue === "string" &&
							rawValue !== "" &&
							rawValue !== "__CLEAR__";
						return (
							<div key={field.name} className="mb-4 grid gap-1">
								<div className="flex items-center justify-between gap-3">
									<label
										htmlFor={fieldId}
										className="text-xs font-medium"
										style={{ color: "var(--text-secondary)" }}
									>
										{field.label}
									</label>
									{field.secret && secretIsConfigured && (
										<span
											className="text-xs"
											style={{ color: "var(--success)" }}
										>
											已配置
										</span>
									)}
								</div>
								{field.kind === "select" ? (
									<select
										id={fieldId}
										className="rounded-lg border px-3 py-2 text-sm"
										style={inputStyle}
										value={fieldValue}
										onChange={(e) =>
											updateField(key, selected, field.name, e.target.value)
										}
									>
										{(field.options || []).map((o) => (
											<option key={o} value={o}>
												{o}
											</option>
										))}
									</select>
								) : field.kind === "json" ? (
									<textarea
										id={fieldId}
										className="min-h-24 rounded-lg border px-3 py-2 font-mono text-sm"
										style={inputStyle}
										placeholder="{}"
										value={fieldValue}
										onChange={(e) =>
											updateField(key, selected, field.name, e.target.value)
										}
									/>
								) : (
									<input
										id={fieldId}
										className="rounded-lg border px-3 py-2 text-sm"
										style={inputStyle}
										type={field.secret ? "password" : "text"}
										autoComplete={field.secret ? "new-password" : undefined}
										placeholder={
											field.secret && secretIsConfigured
												? "已配置 · 留空保持不变"
												: "请输入"
										}
										value={fieldValue}
										onChange={(e) =>
											updateField(key, selected, field.name, e.target.value)
										}
									/>
								)}
								{FIELD_HINTS[field.name] && (
									<p
										className="text-xs"
										style={{ color: "var(--text-tertiary)" }}
									>
										{FIELD_HINTS[field.name]}
									</p>
								)}
							</div>
						);
					})}
			</section>
		</div>
	);
}
