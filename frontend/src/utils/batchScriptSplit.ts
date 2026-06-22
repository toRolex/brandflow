export interface BatchConfig {
  name: string;
  scriptMode: "auto" | "manual";
  manualScript: string;
  skipSubtitle: boolean;
  language: "mandarin" | "cantonese";
  audioMode: "tts" | "upload" | "library";
  audioFile: File | null;
  musicPath: string;
  musicVolume: number;
}

export function defaultBatchConfig(): BatchConfig {
  return {
    name: "",
    scriptMode: "auto",
    manualScript: "",
    skipSubtitle: false,
    language: "mandarin",
    audioMode: "tts",
    audioFile: null,
    musicPath: "",
    musicVolume: 80,
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
