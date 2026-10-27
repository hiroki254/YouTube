import fs from 'node:fs';
import path from 'node:path';
import { PROJECT_DIR } from './paths.js';

const THINKING_LEVELS = ['low', 'medium', 'high'];
const MEDIA_RESOLUTIONS = ['low', 'medium', 'high'];

// .env があれば読み込む（シェルで設定済みの値が優先）
export function loadEnv() {
  const file = path.join(PROJECT_DIR, '.env');
  if (fs.existsSync(file)) process.loadEnvFile(file);
}

export function geminiSettings(env = process.env) {
  const apiKey = env.GEMINI_API_KEY?.trim();
  if (!apiKey) {
    throw new Error('GEMINI_API_KEY がありません。.env.example をコピーして .env を作り、API キーを入れてください。');
  }
  const model = env.GEMINI_MODEL?.trim() || 'gemini-3.8-flash';
  const thinkingLevel = (env.GEMINI_THINKING_LEVEL?.trim() || 'medium').toLowerCase();
  if (!THINKING_LEVELS.includes(thinkingLevel)) {
    throw new Error(`GEMINI_THINKING_LEVEL は ${THINKING_LEVELS.join(' / ')} のどれかにしてください（いま: ${thinkingLevel}）`);
  }
  const mediaResolution = env.GEMINI_MEDIA_RESOLUTION?.trim().toLowerCase() || null;
  if (mediaResolution && !MEDIA_RESOLUTIONS.includes(mediaResolution)) {
    throw new Error(`GEMINI_MEDIA_RESOLUTION は ${MEDIA_RESOLUTIONS.join(' / ')} か空欄にしてください（いま: ${mediaResolution}）`);
  }
  return { apiKey, model, thinkingLevel, mediaResolution };
}
