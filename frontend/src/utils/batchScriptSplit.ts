export interface BatchConfig {
  name: string;
  scriptMode: "auto" | "manual";
  manualScript: string;
  skipSubtitle: boolean;
  audioMode: "tts" | "upload";
  audioFile: File | null;
}

export function defaultBatchConfig(): BatchConfig {
  return {
    name: "",
    scriptMode: "auto",
    manualScript: "",
    skipSubtitle: false,
    audioMode: "tts",
    audioFile: null,
  };
}

export function splitScriptText(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function applyScriptSplit(segments: string[], configs: BatchConfig[]): BatchConfig[] {
  return Array.from({ length: segments.length }, (_, i) => ({
    ...(configs[i] ?? defaultBatchConfig()),
    scriptMode: "manual" as const,
    manualScript: segments[i],
  }));
}
