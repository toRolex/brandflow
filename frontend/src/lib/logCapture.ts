import { type LogEntry, reportError } from "../api/logs";

const DEDUPE_WINDOW_MS = 10_000;
const recentlyReported = new Map<string, number>();
let originalError: typeof console.error | undefined;
let originalWarn: typeof console.warn | undefined;

function stringify(value: unknown): string {
	if (value instanceof Error) return value.message;
	if (typeof value === "string") return value;
	try {
		return JSON.stringify(value);
	} catch {
		return String(value);
	}
}

function send(entry: LogEntry): void {
	const signature = hashSignature(
		`${entry.message}\n${entry.stack_trace ?? ""}`,
	);
	const now = Date.now();
	if ((recentlyReported.get(signature) ?? 0) + DEDUPE_WINDOW_MS > now) return;
	recentlyReported.set(signature, now);
	void reportError(entry).catch(() => undefined);
}

function hashSignature(value: string): string {
	let hash = 0x81_1c_9d_c5;
	for (let index = 0; index < value.length; index++) {
		hash ^= value.charCodeAt(index);
		hash = Math.imul(hash, 0x01_00_01_93);
	}
	return (hash >>> 0).toString(16);
}

function consoleEntry(level: "error" | "warn", args: unknown[]): LogEntry {
	const error = args.find((arg): arg is Error => arg instanceof Error);
	const message = args.map(stringify).join(" ");
	return {
		source: "frontend",
		level,
		message,
		stack_trace: error?.stack ?? new Error(message).stack,
	};
}

export function initLogReporting(): void {
	if (originalError) return;
	originalError = console.error;
	originalWarn = console.warn;
	window.addEventListener("error", onError);
	window.addEventListener("unhandledrejection", onUnhandledRejection);
	console.error = (...args: unknown[]) => {
		originalError?.(...args);
		send(consoleEntry("error", args));
	};
	console.warn = (...args: unknown[]) => {
		originalWarn?.(...args);
		send(consoleEntry("warn", args));
	};
}

function onError(event: ErrorEvent): void {
	send({
		source: "frontend",
		level: "error",
		message: event.message,
		stack_trace: event.error?.stack,
		extra: { url: event.filename, line: event.lineno, column: event.colno },
	});
}

function onUnhandledRejection(event: PromiseRejectionEvent): void {
	const reason = event.reason;
	send({
		source: "frontend",
		level: "error",
		message: stringify(reason),
		stack_trace: reason instanceof Error ? reason.stack : undefined,
	});
}

export function stopLogReporting(): void {
	window.removeEventListener("error", onError);
	window.removeEventListener("unhandledrejection", onUnhandledRejection);
	if (originalError) console.error = originalError;
	if (originalWarn) console.warn = originalWarn;
	originalError = undefined;
	originalWarn = undefined;
	recentlyReported.clear();
}
