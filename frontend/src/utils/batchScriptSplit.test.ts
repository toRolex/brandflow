import { describe, it, expect } from "vitest";
import { splitScriptText, applyScriptSplit, defaultBatchConfig } from "./batchScriptSplit";

describe("splitScriptText", () => {
  it("按空行拆分 Unix 换行符文案", () => {
    const text = "第一段文案。\n\n第二段文案。";
    expect(splitScriptText(text)).toEqual(["第一段文案。", "第二段文案。"]);
  });

  it("按空行拆分 Windows 换行符文案", () => {
    const text = "第一段文案。\r\n\r\n第二段文案。";
    expect(splitScriptText(text)).toEqual(["第一段文案。", "第二段文案。"]);
  });

  it("过滤空片段与仅空白字符片段", () => {
    const text = "\n\n  \n第一段文案。\n\n\n\n第二段文案。\n\n   \n";
    expect(splitScriptText(text)).toEqual(["第一段文案。", "第二段文案。"]);
  });

  it("去除每个片段首尾空白", () => {
    const text = "  第一段文案。  \n\n  第二段文案。  ";
    expect(splitScriptText(text)).toEqual(["第一段文案。", "第二段文案。"]);
  });

  it("兼容连续空行", () => {
    const text = "A\n\n\nB";
    expect(splitScriptText(text)).toEqual(["A", "B"]);
  });
});

describe("applyScriptSplit", () => {
  it("为每个片段设置手动输入模式与文案", () => {
    const configs = [defaultBatchConfig(), defaultBatchConfig()];
    const result = applyScriptSplit(["文案一", "文案二"], configs);
    expect(result).toHaveLength(2);
    expect(result[0].scriptMode).toBe("manual");
    expect(result[0].manualScript).toBe("文案一");
    expect(result[1].scriptMode).toBe("manual");
    expect(result[1].manualScript).toBe("文案二");
  });

  it("当片段数超过现有配置时补全默认配置", () => {
    const configs = [defaultBatchConfig()];
    const result = applyScriptSplit(["文案一", "文案二"], configs);
    expect(result).toHaveLength(2);
    expect(result[1].scriptMode).toBe("manual");
    expect(result[1].manualScript).toBe("文案二");
  });

  it("保留现有卡片的名称与跳过字幕等字段", () => {
    const configs = [{ ...defaultBatchConfig(), name: "保留名称", skipSubtitle: true }];
    const result = applyScriptSplit(["文案一"], configs);
    expect(result[0].name).toBe("保留名称");
    expect(result[0].skipSubtitle).toBe(true);
    expect(result[0].scriptMode).toBe("manual");
  });
});
