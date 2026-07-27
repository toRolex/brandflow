import type { ProviderField, ProviderOptions } from "../types";
import { displayFieldValue } from "../utils/providerForm";

interface ConfigSettingsPanelProps {
	settings: Record<string, Record<string, unknown>>;
	options: NonNullable<ProviderOptions["settings"]>;
	onChange: (section: string, field: string, value: unknown) => void;
}

interface SettingInputProps {
	field: ProviderField;
	fieldId: string;
	secretConfigured: boolean;
	value: string;
	onChange: (value: unknown) => void;
}

const inputStyle: React.CSSProperties = {
	backgroundColor: "var(--bg-input)",
	borderColor: "var(--input-border)",
	color: "var(--input-text)",
};

function SettingInput({
	field,
	fieldId,
	secretConfigured,
	value,
	onChange,
}: SettingInputProps) {
	if (field.kind === "json") {
		return (
			<textarea
				id={fieldId}
				className="min-h-28 rounded-lg border px-3 py-2 font-mono text-sm"
				style={inputStyle}
				value={value}
				onChange={(event) => onChange(event.target.value)}
			/>
		);
	}
	if (field.kind === "select") {
		return (
			<select
				id={fieldId}
				className="rounded-lg border px-3 py-2 text-sm"
				style={inputStyle}
				value={value}
				onChange={(event) => onChange(event.target.value)}
			>
				{field.options?.map((option) => (
					<option key={option} value={option}>
						{option}
					</option>
				))}
			</select>
		);
	}
	let inputType = field.secret ? "password" : "text";
	if (field.kind === "number") {
		inputType = "number";
	}
	return (
		<input
			id={fieldId}
			className="rounded-lg border px-3 py-2 text-sm"
			style={inputStyle}
			type={inputType}
			autoComplete={field.secret ? "new-password" : undefined}
			placeholder={
				field.secret && secretConfigured ? "已配置 · 留空保持不变" : undefined
			}
			min={field.min}
			max={field.max}
			step={field.step}
			value={value}
			onChange={(event) => {
				let nextValue: unknown = event.target.value;
				if (field.kind === "number") {
					nextValue = event.target.valueAsNumber;
				}
				onChange(nextValue);
			}}
		/>
	);
}

export function ConfigSettingsPanel({
	settings,
	options,
	onChange,
}: ConfigSettingsPanelProps) {
	return (
		<div className="grid gap-4 lg:grid-cols-2">
			{Object.entries(options).map(([sectionKey, section]) => (
				<section
					key={sectionKey}
					className="rounded-xl border p-5"
					style={{
						background: "var(--bg-card)",
						borderColor: "var(--border-default)",
					}}
				>
					<h2
						className="font-semibold"
						style={{ color: "var(--text-primary)" }}
					>
						{section.label}
					</h2>
					{section.description && (
						<p
							className="mb-5 mt-1 text-xs"
							style={{ color: "var(--text-secondary)" }}
						>
							{section.description}
						</p>
					)}
					{section.fields.map((field) => {
						const fieldId = `setting-${sectionKey}-${field.name}`;
						const rawValue = settings[sectionKey]?.[field.name];
						const value = displayFieldValue(rawValue, field);
						const secretConfigured = Boolean(
							field.secret && typeof rawValue === "string" && rawValue !== "",
						);
						return (
							<div key={field.name} className="mb-4 grid gap-1">
								<label
									htmlFor={fieldId}
									className="text-xs font-medium"
									style={{ color: "var(--text-secondary)" }}
								>
									{field.label}
								</label>
								{secretConfigured && (
									<span className="text-xs" style={{ color: "var(--success)" }}>
										已配置
									</span>
								)}
								<SettingInput
									field={field}
									fieldId={fieldId}
									secretConfigured={secretConfigured}
									value={value}
									onChange={(nextValue) =>
										onChange(sectionKey, field.name, nextValue)
									}
								/>
								{field.hint && (
									<p
										className="text-xs"
										style={{ color: "var(--text-tertiary)" }}
									>
										{field.hint}
									</p>
								)}
							</div>
						);
					})}
				</section>
			))}
		</div>
	);
}
