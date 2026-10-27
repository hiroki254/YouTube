// 環境の点検。npm run doctor -- --ping で、API キーとモデルIDが通るかも確かめる（料金はほぼかからない）
import { execFileSync } from 'node:child_process';
import { GoogleGenAI } from '@google/genai';
import { loadEnv, geminiSettings } from '../src/env.js';
import { Style } from '../src/style.js';

let ok = true;
const pass = (message) => console.log(`OK    ${message}`);
const warn = (message) => console.log(`注意  ${message}`);
const fail = (message) => { ok = false; console.log(`NG    ${message}`); };

const major = Number(process.versions.node.split('.')[0]);
if (major >= 22) pass(`Node.js ${process.versions.node}`);
else fail(`Node.js ${process.versions.node}（22 以上が必要）`);

try {
  const style = new Style();
  pass('作風の数値を読み込めた（docs/style-tokens.json、config/render-provisional.json）');
  const missing = style.unmeasured();
  if (missing.length) warn(`未計測のトークン: ${missing.join(', ')}（使う場面ではユーザーに確認）`);
} catch (error) {
  fail(`作風の数値を読み込めない: ${error.message}`);
}

try {
  execFileSync('ffmpeg', ['-version'], { stdio: 'ignore' });
  pass('ffmpeg');
} catch {
  warn('ffmpeg が見つからない（分析には不要。動画の書き出しで使う予定）');
}

loadEnv();
let settings = null;
try {
  settings = geminiSettings();
  pass(`Gemini の設定（モデル ${settings.model}、thinking=${settings.thinkingLevel}、解像度=${settings.mediaResolution ?? '既定'}）`);
} catch (error) {
  fail(error.message);
}

if (settings && process.argv.includes('--ping')) {
  try {
    const ai = new GoogleGenAI({ apiKey: settings.apiKey });
    const model = await ai.models.get({ model: settings.model });
    pass(`API に接続できた: ${model.name}（入力上限 ${model.inputTokenLimit ?? '?'} トークン）`);
  } catch (error) {
    fail(`API に接続できない: ${error.message}`);
  }
}

process.exit(ok ? 0 : 1);
