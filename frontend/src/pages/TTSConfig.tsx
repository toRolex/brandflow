import { useState, useEffect } from "react";
import { api } from "../api/client";

interface TTSConfig {
  model: string;
  voice: string;
  fallback_voice: string;
  randomize_voice: boolean;
  random_voices: string[];
  voice_design_prompt: string;
  style_prompt: string;
  audio_format: string;
  sample_rate: number | null;
  bitrate: number | null;
  channel: number | null;
}

interface Voice {
  id: string;
  label: string;
  note: string;
}

const STYLE_PRESETS = [
  { label: "自然口播", value: "自然 清晰 适合短视频带货口播" },
  { label: "热情推荐", value: "活泼热情，语速稍快，带着发现美食的惊喜感" },
  { label: "沉稳讲解", value: "沉稳专业，语速适中，适合知识讲解" },
  { label: "美食探店", value: "热情洋溢，充满食欲，让人垂涎欲滴" },
];

export default function TTSConfigPage() {
  const [config, setConfig] = useState<TTSConfig | null>(null);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [previewText, setPreviewText] = useState("见手青是云南最美味的野生菌，口感鲜嫩，营养丰富。");
  const [previewResult, setPreviewResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
    loadVoices();
  }, []);

  const loadConfig = async () => {
    const data = await api.getTTSConfig();
    setConfig(data as unknown as TTSConfig);
  };

  const loadVoices = async () => {
    const data = await api.getTTSVoices();
    setVoices(data.preset_voices || []);
  };

  const handleSave = async () => {
    if (!config) return;
    setLoading(true);
    try {
      await api.saveTTSConfig(config as unknown as Record<string, unknown>);
      setSaveMsg("配置已保存");
      setTimeout(() => setSaveMsg(null), 3000);
    } catch {
      setSaveMsg("保存失败");
    }
    setLoading(false);
  };

  const handlePreview = async () => {
    if (!config) return;
    setLoading(true);
    try {
      const result = await api.previewTTS({
        text: previewText,
        model: config.model,
        voice: config.voice,
        style_prompt: config.style_prompt,
        voice_design_prompt: config.voice_design_prompt,
      });
      setPreviewResult(result);
    } catch {
      setPreviewResult({ error: "预览失败" });
    }
    setLoading(false);
  };

  const addVoiceToPool = (voiceId: string) => {
    if (!config || config.random_voices.includes(voiceId)) return;
    setConfig({
      ...config,
      random_voices: [...config.random_voices, voiceId],
    });
  };

  const removeVoiceFromPool = (voiceId: string) => {
    if (!config) return;
    setConfig({
      ...config,
      random_voices: config.random_voices.filter(v => v !== voiceId),
    });
  };

  if (!config) {
    return <div className="text-center py-12 text-gray-400">加载配置中...</div>;
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">TTS 配置</h1>

      {saveMsg && (
        <div className={`mb-4 px-4 py-3 rounded-lg text-sm ${
          saveMsg.includes("失败") ? "bg-red-50 border border-red-200 text-red-700" : "bg-green-50 border border-green-200 text-green-700"
        }`}>
          {saveMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">TTS 模型选择</h2>
            <div className="grid grid-cols-2 gap-4">
              <div
                className={`border-2 rounded-xl p-4 cursor-pointer ${
                  config.model === "mimo-v2.5-tts"
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
                onClick={() => setConfig({ ...config, model: "mimo-v2.5-tts" })}
              >
                <h3 className="font-semibold">预置音色</h3>
                <p className="text-sm text-gray-500">mimo-v2.5-tts</p>
                <p className="text-sm text-gray-600 mt-2">使用官方精选音色</p>
              </div>
              <div
                className={`border-2 rounded-xl p-4 cursor-pointer ${
                  config.model === "mimo-v2.5-tts-voicedesign"
                    ? "border-purple-500 bg-purple-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
                onClick={() => setConfig({ ...config, model: "mimo-v2.5-tts-voicedesign" })}
              >
                <h3 className="font-semibold">音色设计</h3>
                <p className="text-sm text-gray-500">mimo-v2.5-tts-voicedesign</p>
                <p className="text-sm text-gray-600 mt-2">通过文字描述自定义音色</p>
              </div>
            </div>
          </section>

          {config.model === "mimo-v2.5-tts" && (
            <section className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold mb-4">预置音色配置</h2>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">主音色</label>
                  <select
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                    value={config.voice}
                    onChange={(e) => setConfig({ ...config, voice: e.target.value })}
                  >
                    {voices.map(v => (
                      <option key={v.id} value={v.id}>{v.label} - {v.note}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">备用音色</label>
                  <select
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                    value={config.fallback_voice}
                    onChange={(e) => setConfig({ ...config, fallback_voice: e.target.value })}
                  >
                    {voices.map(v => (
                      <option key={v.id} value={v.id}>{v.label} - {v.note}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-3 mb-4">
                <input
                  type="checkbox"
                  id="randomize"
                  checked={config.randomize_voice}
                  onChange={(e) => setConfig({ ...config, randomize_voice: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="randomize" className="text-sm">启用音色随机化</label>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">随机音色池</label>
                <div className="flex flex-wrap gap-2 p-3 bg-gray-50 rounded-lg">
                  {config.random_voices.map(voiceId => (
                    <span key={voiceId} className="px-3 py-1 bg-blue-500 text-white text-sm rounded-full flex items-center gap-1">
                      {voiceId}
                      <button onClick={() => removeVoiceFromPool(voiceId)} className="hover:text-red-200">×</button>
                    </span>
                  ))}
                  <select
                    className="px-3 py-1 border-2 border-dashed border-gray-300 text-sm rounded-full"
                    onChange={(e) => { addVoiceToPool(e.target.value); e.target.value = ""; }}
                    value=""
                  >
                    <option value="" disabled>+ 添加音色</option>
                    {voices.filter(v => !config.random_voices.includes(v.id)).map(v => (
                      <option key={v.id} value={v.id}>{v.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </section>
          )}

          {config.model === "mimo-v2.5-tts-voicedesign" && (
            <section className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold mb-4">音色设计配置</h2>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">音色描述</label>
                <textarea
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none"
                  rows={3}
                  placeholder="描述想要的音色特征..."
                  value={config.voice_design_prompt}
                  onChange={(e) => setConfig({ ...config, voice_design_prompt: e.target.value })}
                />
              </div>
            </section>
          )}

          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">风格控制</h2>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">风格指令</label>
              <textarea
                className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none"
                rows={3}
                value={config.style_prompt}
                onChange={(e) => setConfig({ ...config, style_prompt: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">预设风格模板</label>
              <div className="flex flex-wrap gap-2">
                {STYLE_PRESETS.map(preset => (
                  <button
                    key={preset.label}
                    className={`px-4 py-2 text-sm rounded-lg ${
                      config.style_prompt === preset.value
                        ? "bg-blue-500 text-white"
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    }`}
                    onClick={() => setConfig({ ...config, style_prompt: preset.value })}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          </section>

          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">音频参数</h2>
            <div className="grid grid-cols-4 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">格式</label>
                <select
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  value={config.audio_format}
                  onChange={(e) => setConfig({ ...config, audio_format: e.target.value })}
                >
                  <option value="mp3">mp3</option>
                  <option value="wav">wav</option>
                  <option value="pcm">pcm</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">采样率</label>
                <select
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  value={config.sample_rate || ""}
                  onChange={(e) => setConfig({ ...config, sample_rate: e.target.value ? Number(e.target.value) : null })}
                >
                  <option value="">默认</option>
                  <option value="16000">16000</option>
                  <option value="24000">24000</option>
                  <option value="32000">32000</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">比特率</label>
                <select
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  value={config.bitrate || ""}
                  onChange={(e) => setConfig({ ...config, bitrate: e.target.value ? Number(e.target.value) : null })}
                >
                  <option value="">默认</option>
                  <option value="64000">64000</option>
                  <option value="128000">128000</option>
                  <option value="192000">192000</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">声道</label>
                <select
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  value={config.channel || ""}
                  onChange={(e) => setConfig({ ...config, channel: e.target.value ? Number(e.target.value) : null })}
                >
                  <option value="">默认</option>
                  <option value="1">单声道</option>
                  <option value="2">立体声</option>
                </select>
              </div>
            </div>
          </section>

          <div className="flex items-center gap-4">
            <button
              className="px-6 py-3 bg-blue-500 text-white font-medium rounded-xl hover:bg-blue-600 disabled:opacity-50"
              onClick={handleSave}
              disabled={loading}
            >
              {loading ? "保存中..." : "保存配置"}
            </button>
            <button
              className="px-6 py-3 bg-gray-100 text-gray-700 font-medium rounded-xl hover:bg-gray-200"
              onClick={loadConfig}
            >
              重置默认
            </button>
          </div>
        </div>

        <div className="space-y-6">
          <section className="bg-white rounded-xl border border-gray-200 p-6 sticky top-6">
            <h2 className="text-lg font-semibold mb-4">TTS 预览</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">测试文本</label>
                <textarea
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none"
                  rows={3}
                  value={previewText}
                  onChange={(e) => setPreviewText(e.target.value)}
                />
              </div>
              <button
                className="w-full px-4 py-3 bg-blue-500 text-white font-medium rounded-xl hover:bg-blue-600 disabled:opacity-50"
                onClick={handlePreview}
                disabled={loading || !previewText}
              >
                {loading ? "生成中..." : "播放预览"}
              </button>
              {previewResult && (
                <div className="bg-gray-50 rounded-xl p-4">
                  <pre className="text-sm text-gray-600 whitespace-pre-wrap">
                    {JSON.stringify(previewResult, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
