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

/**
 * 将上传的文案文本按空行拆分为多条文案。
 * - 使用 \n\s*\n 匹配空行，兼容 Windows 与 Unix 换行符
 * - 过滤空片段与仅含空白字符的片段
 * - 去除每个片段的首尾空白
 */
export function splitScriptText(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0);
}

/**
 * 将拆分后的文案应用到批量配置列表。
 * - 将每个片段填入对应配置项的 manualScript
 * - 将 scriptMode 设为 manual
 * - 当片段数超过现有配置时，补全默认配置
 * - 保留现有配置中的 name、skipSubtitle、audioMode 等字段
 */
export function applyScriptSplit(segments: string[], configs: BatchConfig[]): BatchConfig[] {
  const result: BatchConfig[] = [];
  for (let i = 0; i < segments.length; i++) {
    const base = configs[i] ?? defaultBatchConfig();
    result.push({
      ...base,
      scriptMode: "manual",
      manualScript: segments[i],
    });
  }
  return result;
}
