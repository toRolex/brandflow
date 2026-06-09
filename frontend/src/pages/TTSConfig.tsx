import { useState, useEffect } from "react";
import { api } from "../api/client";

interface TTSConfig {
  model: string;
  voice: string;
  fallback_voice: string;
  randomize_voice: boolean;
  random_voices: string[];
  voice_design_prompt: string;
  style_control_mode: string;
  style_prompt: string;
  director_character: string;
  director_scene: string;
  director_guidance: string;
  audio_tags_enabled: boolean;
  audio_tags: string;
  audio_format: string;
  sample_rate: number | null;
  bitrate: number | null;
  channel: number | null;
  optimize_text_preview?: boolean;
  voice_clone_sample_path?: string | null;
  voice_clone_mime_type?: string | null;
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
  { label: "温柔亲切", value: "温柔亲切，语速适中，像朋友聊天" },
  { label: "活力青春", value: "活力四射，语速偏快，充满青春气息" },
];

const VOICE_POOLS: Record<string, Voice[]> = {
  "mimo-v2.5-tts": [
    { id: "mimo_default", label: "MiMo 默认", note: "官方默认音色" },
    { id: "冰糖", label: "冰糖", note: "中文女声，清亮自然" },
    { id: "茉莉", label: "茉莉", note: "中文女声，柔和亲切" },
    { id: "苏打", label: "苏打", note: "中文男声，适合短视频口播" },
    { id: "白桦", label: "白桦", note: "中文男声，稳重讲解" },
    { id: "Mia", label: "Mia", note: "英文女声" },
    { id: "Chloe", label: "Chloe", note: "英文女声" },
    { id: "Milo", label: "Milo", note: "英文男声" },
    { id: "Dean", label: "Dean", note: "英文男声" },
  ],
  "mimo-v2-tts": [
    { id: "mimo_default", label: "MiMo 默认", note: "官方默认音色" },
    { id: "default_zh", label: "中文女声", note: "default_zh" },
    { id: "default_en", label: "英文女声", note: "default_en" },
  ],
};

const STYLE_TAGS = [
  // 情绪
  { label: "开心", value: "(开心)" },
  { label: "悲伤", value: "(悲伤)" },
  { label: "愤怒", value: "(愤怒)" },
  { label: "恐惧", value: "(恐惧)" },
  { label: "惊讶", value: "(惊讶)" },
  { label: "兴奋", value: "(兴奋)" },
  { label: "委屈", value: "(委屈)" },
  { label: "平静", value: "(平静)" },
  { label: "冷漠", value: "(冷漠)" },
  { label: "怅然", value: "(怅然)" },
  { label: "欣慰", value: "(欣慰)" },
  { label: "无奈", value: "(无奈)" },
  { label: "愧疚", value: "(愧疚)" },
  { label: "释然", value: "(释然)" },
  { label: "嫉妒", value: "(嫉妒)" },
  { label: "厌倦", value: "(厌倦)" },
  { label: "忐忑", value: "(忐忑)" },
  { label: "动情", value: "(动情)" },
  // 语气
  { label: "温柔", value: "(温柔)" },
  { label: "活泼", value: "(活泼)" },
  { label: "严肃", value: "(严肃)" },
  { label: "高冷", value: "(高冷)" },
  { label: "慵懒", value: "(慵懒)" },
  { label: "俏皮", value: "(俏皮)" },
  { label: "深沉", value: "(深沉)" },
  { label: "干练", value: "(干练)" },
  { label: "凌厉", value: "(凌厉)" },
  // 音色
  { label: "磁性", value: "(磁性)" },
  { label: "甜美", value: "(甜美)" },
  { label: "醇厚", value: "(醇厚)" },
  { label: "清亮", value: "(清亮)" },
  { label: "空灵", value: "(空灵)" },
  { label: "稚嫩", value: "(稚嫩)" },
  { label: "苍老", value: "(苍老)" },
  { label: "沙哑", value: "(沙哑)" },
  { label: "醇雅", value: "(醇雅)" },
  // 角色声音
  { label: "夹子音", value: "(夹子音)" },
  { label: "御姐音", value: "(御姐音)" },
  { label: "正太音", value: "(正太音)" },
  { label: "大叔音", value: "(大叔音)" },
  { label: "台湾腔", value: "(台湾腔)" },
  // 方言
  { label: "东北话", value: "(东北话)" },
  { label: "四川话", value: "(四川话)" },
  { label: "河南话", value: "(河南话)" },
  { label: "粤语", value: "(粤语)" },
  // 角色扮演
  { label: "孙悟空", value: "(孙悟空)" },
  { label: "林黛玉", value: "(林黛玉)" },
  // 唱歌
  { label: "唱歌", value: "(唱歌)" },
];

const AUDIO_TAGS = [
  // 呼吸
  { label: "吸气", value: "[吸气]" },
  { label: "深呼吸", value: "[深呼吸]" },
  { label: "叹气", value: "[叹气]" },
  { label: "长叹一口气", value: "[长叹一口气]" },
  { label: "喘息", value: "[喘息]" },
  { label: "屏息", value: "[屏息]" },
  // 情绪
  { label: "紧张", value: "[紧张]" },
  { label: "害怕", value: "[害怕]" },
  { label: "激动", value: "[激动]" },
  { label: "疲惫", value: "[疲惫]" },
  { label: "委屈", value: "[委屈]" },
  { label: "撒娇", value: "[撒娇]" },
  { label: "心虚", value: "[心虚]" },
  { label: "震惊", value: "[震惊]" },
  { label: "不耐烦", value: "[不耐烦]" },
  // 声音特征
  { label: "颤抖", value: "[颤抖]" },
  { label: "变调", value: "[变调]" },
  { label: "破音", value: "[破音]" },
  { label: "鼻音", value: "[鼻音]" },
  { label: "气声", value: "[气声]" },
  { label: "沙哑", value: "[沙哑]" },
  // 笑/哭
  { label: "笑声", value: "[笑声]" },
  { label: "笑", value: "[笑]" },
  { label: "轻笑", value: "[轻笑]" },
  { label: "大笑", value: "[大笑]" },
  { label: "冷笑", value: "[冷笑]" },
  { label: "抽泣", value: "[抽泣]" },
  { label: "呜咽", value: "[呜咽]" },
  { label: "哽咽", value: "[哽咽]" },
  { label: "嚎啕大哭", value: "[嚎啕大哭]" },
  // 停顿
  { label: "停顿", value: "[停顿]" },
];

export default function TTSConfigPage() {
  const [config, setConfig] = useState<TTSConfig | null>(null);
  const [previewText, setPreviewText] = useState("见手青是云南最美味的野生菌，口感鲜嫩，营养丰富。");
  const [previewAudioUrl, setPreviewAudioUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    const data = await api.getTTSConfig();
    setConfig(data as unknown as TTSConfig);
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
    setPreviewError(null);
    try {
      const voice = config.randomize_voice && config.random_voices.length > 0
        ? config.random_voices[Math.floor(Math.random() * config.random_voices.length)]
        : config.voice;
      const result = await api.previewTTS({
        text: previewText,
        model: config.model,
        voice,
        style_prompt: config.style_prompt,
        voice_design_prompt: config.voice_design_prompt,
      });
      if (previewAudioUrl) URL.revokeObjectURL(previewAudioUrl);
      setPreviewAudioUrl(result);
    } catch {
      setPreviewError("预览失败");
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
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
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
              <div
                className={`border-2 rounded-xl p-4 cursor-pointer ${
                  config.model === "mimo-v2.5-tts-voiceclone"
                    ? "border-green-500 bg-green-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
                onClick={() => setConfig({ ...config, model: "mimo-v2.5-tts-voiceclone" })}
              >
                <h3 className="font-semibold">音色克隆</h3>
                <p className="text-sm text-gray-500">mimo-v2.5-tts-voiceclone</p>
                <p className="text-sm text-gray-600 mt-2">通过音频样本克隆音色</p>
              </div>
              <div
                className={`border-2 rounded-xl p-4 cursor-pointer ${
                  config.model === "mimo-v2-tts"
                    ? "border-orange-500 bg-orange-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
                onClick={() => setConfig({ ...config, model: "mimo-v2-tts" })}
              >
                <h3 className="font-semibold">V2 预置</h3>
                <p className="text-sm text-gray-500">mimo-v2-tts</p>
                <p className="text-sm text-gray-600 mt-2">旧版 V2 预置音色</p>
              </div>
            </div>
          </section>

          {(config.model === "mimo-v2.5-tts" || config.model === "mimo-v2-tts") && (
            <section className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold mb-4">预置音色配置</h2>
              {(() => {
                const pool = VOICE_POOLS[config.model] || [];
                return (
                  <>
                    <div className="grid grid-cols-2 gap-4 mb-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">主音色</label>
                        <select
                          className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                          value={config.voice}
                          onChange={(e) => setConfig({ ...config, voice: e.target.value })}
                        >
                          {pool.map(v => (
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
                          {pool.map(v => (
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
                          {pool.filter(v => !config.random_voices.includes(v.id)).map(v => (
                            <option key={v.id} value={v.id}>{v.label}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </>
                );
              })()}
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
              <div className="flex items-center gap-3 mt-4">
                <input
                  type="checkbox"
                  id="optimize_text_preview"
                  checked={config.optimize_text_preview || false}
                  onChange={(e) => setConfig({ ...config, optimize_text_preview: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="optimize_text_preview" className="text-sm font-medium text-gray-700">启用文本优化预览</label>
              </div>
              <p className="mt-1 text-xs text-gray-500">启用后，系统会自动润色 assistant 文本</p>
            </section>
          )}

          {config.model === "mimo-v2.5-tts-voiceclone" && (
            <section className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold mb-4">音色克隆配置</h2>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
                {config.voice_clone_sample_path ? (
                  <div className="space-y-3">
                    <p className="text-sm text-green-600">✓ 已上传音频样本</p>
                    <p className="text-xs text-gray-500">{config.voice_clone_sample_path}</p>
                    <button
                      className="px-4 py-2 text-sm bg-red-100 text-red-700 rounded-lg hover:bg-red-200"
                      onClick={() => setConfig({ ...config, voice_clone_sample_path: null, voice_clone_mime_type: null })}
                    >
                      删除并重新上传
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm text-gray-600">点击上传音频样本</p>
                    <p className="text-xs text-gray-500">支持 mp3/wav 格式，最大 10MB</p>
                    <input
                      type="file"
                      accept=".mp3,.wav,audio/mpeg,audio/wav"
                      className="hidden"
                      id="voice-clone-upload"
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        const formData = new FormData();
                        formData.append("file", file);
                        try {
                          const response = await fetch("/api/tts/voice-clone-sample", { method: "POST", body: formData });
                          if (!response.ok) {
                            const error = await response.json();
                            alert(error.detail || "上传失败");
                            return;
                          }
                          const data = await response.json();
                          setConfig({ ...config, voice_clone_sample_path: data.path, voice_clone_mime_type: data.mime_type });
                        } catch {
                          alert("上传失败");
                        }
                      }}
                    />
                    <label htmlFor="voice-clone-upload" className="inline-block px-4 py-2 bg-blue-500 text-white rounded-lg cursor-pointer hover:bg-blue-600">
                      选择文件
                    </label>
                  </div>
                )}
              </div>
            </section>
          )}

          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">风格控制</h2>
            
            {/* 风格控制模式选择 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">控制模式</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="style_control_mode"
                    value="simple"
                    checked={config.style_control_mode === "simple"}
                    onChange={(e) => setConfig({ ...config, style_control_mode: e.target.value })}
                    className="rounded"
                  />
                  <span className="text-sm">简单模式</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="style_control_mode"
                    value="director"
                    checked={config.style_control_mode === "director"}
                    onChange={(e) => setConfig({ ...config, style_control_mode: e.target.value })}
                    className="rounded"
                  />
                  <span className="text-sm">导演模式</span>
                </label>
              </div>
            </div>

            {/* 简单模式 */}
            {config.style_control_mode === "simple" && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">风格指令</label>
                <textarea
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none"
                  rows={3}
                  placeholder="用自然语言描述想要的语音风格..."
                  value={config.style_prompt}
                  onChange={(e) => setConfig({ ...config, style_prompt: e.target.value })}
                />
                <p className="mt-1 text-xs text-gray-500">
                  示例：用轻快上扬的语调向领导报喜，语速稍快，带着查到成绩后压抑不住的激动与小骄傲
                </p>
              </div>
            )}

            {/* 导演模式 */}
            {config.style_control_mode === "director" && (
              <div className="space-y-4 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">【角色】人物描述</label>
                  <textarea
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none"
                    rows={2}
                    placeholder="描述角色特征：年龄、性别、性格、音色特点..."
                    value={config.director_character}
                    onChange={(e) => setConfig({ ...config, director_character: e.target.value })}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    示例：25岁活泼少女，声线清脆明亮，语尾带一点上扬
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">【场景】情境描述</label>
                  <textarea
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none"
                    rows={2}
                    placeholder="描述场景背景：场合、氛围、对象..."
                    value={config.director_scene}
                    onChange={(e) => setConfig({ ...config, director_scene: e.target.value })}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    示例：在美食直播间，面对观众介绍刚发现的宝藏小店
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">【指导】演绎要领</label>
                  <textarea
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none"
                    rows={3}
                    placeholder="详细指导：语速、气息、停顿、重音、情绪起伏..."
                    value={config.director_guidance}
                    onChange={(e) => setConfig({ ...config, director_guidance: e.target.value })}
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    示例：语速偏快，咬字轻巧，在强调食材时微微加重语气，整体保持兴奋但不做作
                  </p>
                </div>
              </div>
            )}

            {/* 预设风格模板 */}
            <div className="mb-4">
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
                    onClick={() => setConfig({ ...config, style_prompt: preset.value, style_control_mode: "simple" })}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 标签控制 */}
            <div className="border-t pt-4">
              <div className="flex items-center gap-3 mb-4">
                <input
                  type="checkbox"
                  id="audio_tags_enabled"
                  checked={config.audio_tags_enabled}
                  onChange={(e) => setConfig({ ...config, audio_tags_enabled: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="audio_tags_enabled" className="text-sm font-medium text-gray-700">
                  启用标签控制
                </label>
                <span className="text-xs text-gray-500">
                  在文本前添加风格标签和音频标签
                </span>
              </div>

              {config.audio_tags_enabled && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">风格标签</label>
                    <div className="flex flex-wrap gap-2">
                      {STYLE_TAGS.map(tag => (
                        <button
                          key={tag.label}
                          className="px-3 py-1 text-sm bg-purple-100 text-purple-700 rounded-full hover:bg-purple-200"
                          onClick={() => {
                            const currentTags = config.audio_tags || "";
                            if (!currentTags.includes(tag.value)) {
                              setConfig({ ...config, audio_tags: tag.value + currentTags });
                            }
                          }}
                        >
                          {tag.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">音频标签</label>
                    <div className="flex flex-wrap gap-2">
                      {AUDIO_TAGS.map(tag => (
                        <button
                          key={tag.label}
                          className="px-3 py-1 text-sm bg-green-100 text-green-700 rounded-full hover:bg-green-200"
                          onClick={() => {
                            const currentTags = config.audio_tags || "";
                            setConfig({ ...config, audio_tags: currentTags + tag.value });
                          }}
                        >
                          {tag.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">标签预览</label>
                    <input
                      type="text"
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                      placeholder="(风格标签)文本内容[音频标签]"
                      value={config.audio_tags}
                      onChange={(e) => setConfig({ ...config, audio_tags: e.target.value })}
                    />
                    <p className="mt-1 text-xs text-gray-500">
                      格式：(风格)开头，[标签]可插入文本任意位置
                    </p>
                  </div>
                </div>
              )}
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
                  <option value="wav">wav</option>
                  <option value="pcm16">pcm16</option>
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
              {previewError && (
                <div className="text-sm text-red-600 bg-red-50 rounded-lg p-3">
                  {previewError}
                </div>
              )}
              {previewAudioUrl && (
                <audio
                  className="w-full"
                  controls
                  autoPlay
                  src={previewAudioUrl}
                />
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
