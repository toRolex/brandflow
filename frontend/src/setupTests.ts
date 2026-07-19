import "@testing-library/jest-dom/vitest";

// ponytail: EventSource stub for jsdom
globalThis.EventSource = class {
	constructor(_url: string | URL, _eventSourceInitDict?: EventSourceInit) {}
	close() {}
	onopen: ((_event: Event) => void) | null = null;
	onmessage: ((_event: MessageEvent) => void) | null = null;
	onerror: ((_event: Event) => void) | null = null;
	readyState = 2;
	static readonly CONNECTING = 0;
	static readonly OPEN = 1;
	static readonly CLOSED = 2;
	addEventListener() {}
	removeEventListener() {}
	dispatchEvent(_event: Event) {
		return true;
	}
} as unknown as typeof globalThis.EventSource;
