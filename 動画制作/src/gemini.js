import { GoogleGenAI } from '@google/genai';
import { ANALYSIS_SCHEMA, checkAnalysis } from './validate.js';

const MEDIA_RESOLUTION = {
  low: 'MEDIA_RESOLUTION_LOW',
  medium: 'MEDIA_RESOLUTION_MEDIUM',
  high: 'MEDIA_RESOLUTION_HIGH',
};

// Gemini に渡すスキーマ。$comment は API に送らない
function responseSchema() {
  const { $comment, ...schema } = ANALYSIS_SCHEMA;
  return schema;
}

function videoPart(url, clip) {
  const part = { fileData: { fileUri: url } };
  if (clip) {
    part.videoMetadata = {};
    if (clip.startSec != null) part.videoMetadata.startOffset = `${clip.startSec}s`;
    if (clip.endSec != null) part.videoMetadata.endOffset = `${clip.endSec}s`;
  }
  return part;
}

// 公開 YouTube 動画を URL のまま Gemini に渡し、編集構造の JSON を受け取る。
// 形や時刻の並びが不正なら、問題点を添えて1回だけ直させる。
// temperature などのサンプリング設定は 3.8 Flash では無視されるため送らない。
export async function analyzeYouTube({ settings, url, prompt, clip = null }) {
  const ai = new GoogleGenAI({ apiKey: settings.apiKey });
  const config = {
    responseMimeType: 'application/json',
    responseJsonSchema: responseSchema(),
    thinkingConfig: { thinkingLevel: settings.thinkingLevel.toUpperCase() },
  };
  if (settings.mediaResolution) config.mediaResolution = MEDIA_RESOLUTION[settings.mediaResolution];

  const contents = [{ role: 'user', parts: [videoPart(url, clip), { text: prompt }] }];
  const usage = [];
  for (let attempt = 1; attempt <= 2; attempt++) {
    const response = await ai.models.generateContent({ model: settings.model, contents, config });
    usage.push(response.usageMetadata ?? null);
    const text = response.text ?? '';
    let analysis = null;
    let problems;
    try {
      analysis = JSON.parse(text);
      problems = checkAnalysis(analysis);
    } catch (error) {
      problems = [`JSON として読めません: ${error.message}`];
    }
    if (problems.length === 0) {
      return { analysis, modelVersion: response.modelVersion ?? null, usage, attempts: attempt };
    }
    if (attempt === 2) {
      const error = new Error(`分析結果が不正です:\n- ${problems.join('\n- ')}`);
      error.rawText = text;
      throw error;
    }
    contents.push(
      { role: 'model', parts: [{ text }] },
      { role: 'user', parts: [{ text: `次の問題を直して、JSON 全体を返し直してください。\n- ${problems.join('\n- ')}` }] },
    );
  }
}
