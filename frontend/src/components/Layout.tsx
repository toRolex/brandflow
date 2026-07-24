import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
	checkVersion,
	getUpdateStatus,
	triggerUpdate,
	type UpdateStatus,
} from "../api/version";
import { useTheme } from "../context/ThemeContext";
import ProductSelector from "./ProductSelector";

/* ------------------------------------------------------------------ */
/*  SVG Icons — 18x18, currentColor, stroke-width 1.5, round caps     */
/* ------------------------------------------------------------------ */

const IconGrid = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<rect x="1.5" y="1.5" width="6" height="6" rx="1" />
		<rect x="10.5" y="1.5" width="6" height="6" rx="1" />
		<rect x="1.5" y="10.5" width="6" height="6" rx="1" />
		<rect x="10.5" y="10.5" width="6" height="6" rx="1" />
	</svg>
);

const IconImage = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<rect x="1.5" y="2.5" width="15" height="13" rx="2" />
		<circle cx="5.5" cy="6.5" r="1.5" />
		<path d="M1.5 13.5l4-4 3 3 3-3 5 5" />
	</svg>
);

const IconGear = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<circle cx="9" cy="9" r="2.5" />
		<path d="M9 1.5v1.5M9 15v1.5M3.7 3.7l1.06 1.06M13.24 13.24l1.06 1.06M1.5 9h1.5M15 9h1.5M3.7 14.3l1.06-1.06M13.24 4.76l1.06-1.06" />
	</svg>
);

const IconChart = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<path d="M3.5 14.5V9" />
		<path d="M9 14.5V3.5" />
		<path d="M14.5 14.5V7" />
	</svg>
);

const IconSun = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<circle cx="9" cy="9" r="3.5" />
		<path d="M9 1v1.5M9 15.5V17M3.34 3.34l1.06 1.06M15.6 15.6l1.06 1.06M1 9h1.5M15.5 9H17M3.34 16.66l1.06-1.06M15.6 2.4l1.06-1.06" />
	</svg>
);

const IconMoon = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<path d="M15.5 10.5a6.5 6.5 0 0 1-8-8 6.5 6.5 0 1 0 8 8z" />
	</svg>
);

const IconExpand = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<path d="M7 1.5H1.5V7M11 16.5h5.5V11" />
	</svg>
);

const IconCollapse = () => (
	<svg
		width="18"
		height="18"
		viewBox="0 0 18 18"
		fill="none"
		stroke="currentColor"
		strokeWidth="1.5"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<path d="M1.5 7V1.5H7M16.5 11v5.5H11" />
	</svg>
);

/* ------------------------------------------------------------------ */
/*  Icon mapping – key -> ReactNode                                   */
/* ------------------------------------------------------------------ */

const ICON_MAP: Record<string, ReactNode> = {
	grid: <IconGrid />,
	image: <IconImage />,
	gear: <IconGear />,
	chart: <IconChart />,
};

const NAV_ITEMS = [
	{ path: "/", label: "项目列表", icon: "grid" },
	{ path: "/assets", label: "素材库", icon: "image" },
	{ path: "/config", label: "系统配置", icon: "gear" },
	{ path: "/analytics", label: "数据追踪", icon: "chart" },
];

const CONFIG_ITEMS = [
	{ path: "/config", label: "Provider 配置" },
	{ path: "/system/config/product", label: "产品配置" },
	{ path: "/system/config/templates", label: "脚本模板" },
	{ path: "/system/config/quality", label: "质检规则" },
	{ path: "/system/config/knowledge", label: "知识库" },
	{ path: "/tts-config", label: "TTS 配置" },
];

/* ------------------------------------------------------------------ */
/*  Update state machine types + helpers                              */
/* ------------------------------------------------------------------ */

type UpdateState =
	| { status: "idle" }
	| { status: "available"; current: string; latest: string }
	| { status: "running"; progress: UpdateStatus | null }
	| { status: "restarting"; message: string }
	| { status: "done"; version: string }
	| { status: "failed"; step?: string; error?: string; logPath: string }
	| { status: "stalled"; progress: UpdateStatus };

const SpinnerIcon = () => (
	<svg
		className="animate-spin"
		width="16"
		height="16"
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		strokeWidth="2"
	>
		<circle cx="12" cy="12" r="10" strokeDasharray="50" strokeDashoffset="15" />
	</svg>
);

const UPDATE_LOG_PATH = "packaging/windows/update.log";

export default function Layout({ children }: { children: ReactNode }) {
	const location = useLocation();
	const { theme, layout, toggleTheme, toggleLayout } = useTheme();
	const active = location.pathname;

	const inSystemConfig =
		active.startsWith("/system/config/") ||
		active === "/config" ||
		active === "/tts-config";

	const [versionInfo, setVersionInfo] = useState<{
		current: string;
		latest: string;
		updateAvailable: boolean;
	} | null>(null);
	const [bannerDismissed, setBannerDismissed] = useState(
		() => sessionStorage.getItem("bf-update-dismissed") === "1",
	);
	const [updateState, setUpdateState] = useState<UpdateState>({
		status: "idle",
	});
	const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
	const currentVersionRef = useRef("");
	const isJoinedRef = useRef(false);

	const stopPolling = () => {
		if (pollingRef.current) {
			clearInterval(pollingRef.current);
			pollingRef.current = null;
		}
	};

	const fetchVersion = () => {
		checkVersion()
			.then((v) => {
				currentVersionRef.current = v.current;
				setVersionInfo({
					current: v.current,
					latest: v.latest,
					updateAvailable: v.update_available,
				});
				setUpdateState((prev) => {
					if (prev.status !== "idle" && prev.status !== "available")
						return prev;
					return v.update_available
						? { status: "available", current: v.current, latest: v.latest }
						: { status: "idle" };
				});
			})
			.catch(() => {
				// silent — network failure is not an error to show
			});
	};
	/** Poll the server-side progress endpoint every 1 s. */
	const pollProgress = () => {
		getUpdateStatus()
			.then((p) => {
				if (p.status === "idle") {
					// progress.json was cleaned — fall back to version poll
					return checkVersion().then((v) => {
						if (v.current !== currentVersionRef.current) {
							stopPolling();
							setUpdateState({ status: "done", version: v.current });
						}
					});
				}
				if (p.stalled) {
					stopPolling();
					setUpdateState({ status: "stalled", progress: p });
					return;
				}
				if (p.status === "restarting") {
					setUpdateState({
						status: "restarting",
						message: "服务重启中，即将完成...",
					});
					return;
				}
				if (p.status === "done") {
					stopPolling();
					setUpdateState({ status: "done", version: p.step_label || "" });
					return;
				}
				if (p.status === "failed") {
					stopPolling();
					setUpdateState({
						status: "failed",
						step: p.step,
						error: p.error,
						logPath: UPDATE_LOG_PATH,
					});
					return;
				}
				setUpdateState({ status: "running", progress: p });
			})
			.catch(() => {
				// silent — treat as transient
			});
	};

	const startPolling = () => {
		stopPolling();
		pollingRef.current = setInterval(pollProgress, 1000);
	};

	/** On mount: restore running updates (multi-user shared state). */
	useEffect(() => {
		fetchVersion();
		getUpdateStatus()
			.then((p) => {
				if (p.status === "running" || p.status === "restarting") {
					isJoinedRef.current = true;
					if (p.status === "restarting") {
						setUpdateState({
							status: "restarting",
							message: "服务重启中，即将完成...",
						});
					} else {
						setUpdateState({ status: "running", progress: p });
					}
					startPolling();
				}
			})
			.catch(() => {
				// silent
			});
	}, []);

	const handleUpdate = async () => {
		try {
			const result = await triggerUpdate();
			if (result.status === "in_progress") {
				// 409 — join as observer
				isJoinedRef.current = true;
				// fetch progress once to show current state, then start polling
				getUpdateStatus()
					.then((p) => {
						if (p.status === "running") {
							setUpdateState({ status: "running", progress: p });
						}
					})
					.catch(() => {});
				startPolling();
			} else {
				setUpdateState({ status: "running", progress: null });
				startPolling();
			}
		} catch {
			setUpdateState({ status: "failed", logPath: UPDATE_LOG_PATH });
		}
	};

	const dismissAvailableBanner = () => {
		setBannerDismissed(true);
		sessionStorage.setItem("bf-update-dismissed", "1");
	};

	const dismissUpdateBanner = () => {
		stopPolling();
		setUpdateState({ status: "idle" });
	};

	useEffect(() => () => stopPolling(), []);

	return (
		<div
			className="flex h-screen"
			style={{ background: "var(--bg-page)", color: "var(--text-primary)" }}
		>
			{/* Left sidebar */}
			<nav
				className="flex flex-col w-12 border-r py-2 items-center gap-1 shrink-0"
				style={{
					background: "var(--bg-nav)",
					borderColor: "var(--border-default)",
				}}
			>
				{NAV_ITEMS.map((item) => {
					const isActive =
						item.path === "/" ? active === "/" : active.startsWith(item.path);
					return (
						<Link
							key={item.path}
							to={item.path}
							className={`w-9 h-9 flex items-center justify-center rounded-md text-sm transition-colors ${
								isActive ? "" : "hover:bg-[var(--color-steel)]"
							}`}
							title={item.label}
							style={{
								background: isActive
									? "var(--color-electric-blue-muted)"
									: undefined,
								color: isActive
									? "var(--color-electric-blue)"
									: "var(--text-secondary)",
							}}
						>
							{ICON_MAP[item.icon]}
						</Link>
					);
				})}
				{/* Bottom controls */}
				<div className="mt-auto flex flex-col items-center gap-1">
					<button
						onClick={toggleLayout}
						className="w-9 h-9 flex items-center justify-center rounded-md transition-colors hover:bg-[var(--color-steel)]"
						style={{ color: "var(--text-secondary)" }}
						title={layout === "normal" ? "紧凑模式" : "正常模式"}
					>
						{layout === "normal" ? <IconCollapse /> : <IconExpand />}
					</button>
					<button
						onClick={toggleTheme}
						className="w-9 h-9 flex items-center justify-center rounded-md transition-colors hover:bg-[var(--color-steel)]"
						style={{ color: "var(--text-secondary)" }}
						title={theme === "light" ? "暗色模式" : "亮色模式"}
					>
						{theme === "light" ? <IconMoon /> : <IconSun />}
					</button>
				</div>
			</nav>

			{/* Right content area */}
			<div className="flex-1 flex flex-col overflow-hidden">
				{/* Top header */}
				<header
					className="flex items-center justify-between px-4 py-2 border-b shrink-0"
					style={{
						background: "var(--bg-header)",
						borderColor: "var(--border-default)",
					}}
				>
					<div className="flex items-center gap-2">
						<span
							className="text-sm font-semibold"
							style={{ color: "var(--text-primary)" }}
						>
							Brandflow
						</span>
						{versionInfo && (
							<span
								className="text-xs inline-flex items-center gap-1"
								style={{ color: "var(--text-tertiary)" }}
							>
								· v{versionInfo.current}
								{versionInfo.updateAvailable ? (
									<span
										data-testid="version-update-dot"
										className="inline-block w-2 h-2 rounded-full"
										style={{ backgroundColor: "orange" }}
									/>
								) : (
									<>
										<span style={{ color: "green" }}>✓</span>
										<span>最新</span>
									</>
								)}
								<button
									onClick={fetchVersion}
									aria-label="检查更新"
									type="button"
									className="ml-0.5 hover:opacity-70"
								>
									<svg
										width="12"
										height="12"
										viewBox="0 0 12 12"
										fill="none"
										stroke="currentColor"
										strokeWidth="1.5"
										strokeLinecap="round"
										strokeLinejoin="round"
									>
										<path d="M1.5 6a4.5 4.5 0 1 1 9 0 4.5 4.5 0 0 1-9 0" />
										<path d="M1.5 3.5V6h2.5" />
									</svg>
								</button>
							</span>
						)}
						{inSystemConfig && (
							<span
								className="text-xs"
								style={{ color: "var(--text-tertiary)" }}
							>
								/ 系统配置
							</span>
						)}
					</div>
					<div className="flex items-center gap-2">
						<ProductSelector />
					</div>
				</header>

				{updateState.status !== "idle" &&
					(() => {
						switch (updateState.status) {
							case "available":
								if (bannerDismissed) return null;
								return (
									<div
										className="flex items-center gap-2 px-4 py-2 text-sm border-b shrink-0"
										style={{
											background:
												"var(--color-caution-amber-muted, oklch(65% .14 75 / .12))",
											borderColor: "var(--border-default)",
											color: "var(--text-primary)",
										}}
									>
										<svg
											width="16"
											height="16"
											viewBox="0 0 16 16"
											fill="none"
											stroke="currentColor"
											strokeWidth="1.5"
											strokeLinecap="round"
											strokeLinejoin="round"
											style={{ flexShrink: 0 }}
										>
											<circle cx="8" cy="8" r="6.5" />
											<path d="M8 4.5v4M8 11v.5" />
										</svg>
										<span className="flex-1">
											<strong>新版本可用</strong> v{updateState.latest} 已发布
										</span>
										<button
											onClick={handleUpdate}
											type="button"
											className="px-3 py-0.5 text-xs font-medium rounded"
											style={{
												background: "var(--color-electric-blue)",
												color: "#fff",
											}}
										>
											更新
										</button>
										<button
											onClick={dismissAvailableBanner}
											aria-label="关闭"
											type="button"
											className="text-sm font-medium hover:opacity-70 flex-shrink-0"
										>
											✕
										</button>
									</div>
								);

							case "running": {
								const p = updateState.progress;
								return (
									<div
										data-testid="update-progress-banner"
										className="flex items-center gap-3 px-4 py-2 text-sm border-b shrink-0"
										style={{
											background:
												"var(--color-caution-amber-muted, oklch(65% .14 75 / .12))",
											borderColor: "var(--border-default)",
											color: "var(--text-primary)",
										}}
									>
										<SpinnerIcon />
										<span data-testid="update-step-label">
											{isJoinedRef.current ? "正在观察更新 — " : ""}
											{p?.step_label || "正在准备..."}
										</span>
										{/* percent bar */}
										<div
											className="flex-1 h-1.5 rounded-full overflow-hidden"
											style={{ background: "var(--color-steel)" }}
										>
											<div
												data-testid="update-percent-bar"
												className="h-full rounded-full transition-all duration-500"
												style={{
													width: `${p?.percent ?? 0}%`,
													background: "var(--color-electric-blue)",
												}}
											/>
										</div>
										<span className="text-xs opacity-70">
											{p?.percent ?? 0}%
										</span>
									</div>
								);
							}

							case "restarting":
								return (
									<div
										className="flex items-center gap-2 px-4 py-2 text-sm border-b shrink-0"
										style={{
											background:
												"var(--color-caution-amber-muted, oklch(65% .14 75 / .12))",
											borderColor: "var(--border-default)",
											color: "var(--text-primary)",
										}}
									>
										<SpinnerIcon />
										<span>{updateState.message}</span>
									</div>
								);

							case "done":
								return (
									<div
										className="flex items-center gap-2 px-4 py-2 text-sm border-b shrink-0"
										style={{
											background:
												"var(--color-caution-amber-muted, oklch(65% .14 75 / .12))",
											borderColor: "var(--border-default)",
											color: "var(--text-primary)",
										}}
									>
										<span>✅</span>
										<span className="flex-1">
											更新完成 v{updateState.version}
										</span>
										<button
											onClick={dismissUpdateBanner}
											aria-label="关闭"
											type="button"
											className="text-sm font-medium hover:opacity-70 flex-shrink-0"
										>
											✕
										</button>
									</div>
								);

							case "failed":
								return (
									<div
										className="flex items-center gap-2 px-4 py-2 text-sm border-b shrink-0"
										style={{
											background:
												"var(--color-caution-amber-muted, oklch(65% .14 75 / .12))",
											borderColor: "var(--border-default)",
											color: "var(--text-primary)",
										}}
									>
										<span>❌</span>
										<span className="flex-1">
											更新失败
											{updateState.step ? ` — 步骤: ${updateState.step}` : ""}
											{updateState.error
												? ` — ${updateState.error}`
												: "，请检查服务端日志"}
										</span>
										<code className="text-xs opacity-70">
											{updateState.logPath}
										</code>
										<button
											onClick={dismissUpdateBanner}
											aria-label="关闭"
											type="button"
											className="text-sm font-medium hover:opacity-70 flex-shrink-0"
										>
											✕
										</button>
									</div>
								);

							case "stalled":
								return (
									<div
										className="flex items-center gap-2 px-4 py-2 text-sm border-b shrink-0"
										style={{
											background:
												"var(--color-caution-amber-muted, oklch(65% .14 75 / .12))",
											borderColor: "var(--border-default)",
											color: "var(--text-primary)",
										}}
									>
										<span>⚠️</span>
										<span className="flex-1">
											更新已停滞在步骤{" "}
											{updateState.progress.step_label ||
												updateState.progress.step ||
												"—"}
											，请检查服务端日志
										</span>
										<button
											onClick={dismissUpdateBanner}
											aria-label="关闭"
											type="button"
											className="text-sm font-medium hover:opacity-70 flex-shrink-0"
										>
											✕
										</button>
									</div>
								);
						}
					})()}

				{/* Content area with optional sub-nav */}
				<div className="flex-1 flex overflow-hidden">
					{inSystemConfig && <SystemConfigSidebar />}
					<main
						className="flex-1 overflow-auto"
						style={{ padding: "var(--spacing-lg)" }}
					>
						{children}
					</main>
				</div>
			</div>
		</div>
	);
}

function SystemConfigSidebar() {
	const location = useLocation();
	const active = location.pathname;
	return (
		<nav
			className="w-44 border-r shrink-0 overflow-y-auto py-2"
			style={{
				background: "var(--bg-nav)",
				borderColor: "var(--border-default)",
			}}
		>
			{CONFIG_ITEMS.map((item) => {
				const isActive =
					item.path === "/config"
						? active === "/config"
						: active.startsWith(item.path);
				return (
					<Link
						key={item.path}
						to={item.path}
						className="block px-3 py-1.5 text-sm rounded-md mx-1 transition-colors"
						style={{
							background: isActive ? "var(--bg-nav-active)" : "transparent",
							color: isActive
								? "var(--text-nav-active)"
								: "var(--text-secondary)",
						}}
					>
						{item.label}
					</Link>
				);
			})}
		</nav>
	);
}
