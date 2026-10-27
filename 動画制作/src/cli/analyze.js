// 使い方: npm run analyze -- <YouTube の URL> [--start 秒] [--end 秒] [--out ファイル]
import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { loadEnv, geminiSettings } from '../env.js';
import { analyzeYouTube } from '../gemini.js';
import { ANALYSES_DIR, PROJECT_DIR } from '../paths.js';
import { parseYouTubeUrl } from '../youtube.js';

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    start: { type: 'string' },
    end: { type: 'string' },
    out: { type: 'string' },
  },
});
if (positionals.length !== 1) {
  console.error('使い方: npm run analyze -- <YouTube の URL> [--start 秒] [--end 秒] [--out ファイル]');
  process.exit(1);
}

const toSec = (value, name) => {
  if (value == null) return null;
  const sec = Number(value);
  if (!Number.isFinite(sec) || sec < 0) throw new Error(`--${name} は0以上の秒数で指定してください: ${value}`);
  return sec;
};

loadEnv();
const settings = geminiSettings();
const { id, url } = parseYouTubeUrl(positionals[0]);
const startSec = toSec(values.start, 'start');
const endSec = toSec(values.end, 'end');
const clip = startSec != null || endSec != null ? { startSec, endSec } : null;
const prompt = fs.readFileSync(path.join(PROJECT_DIR, 'prompts', 'analyze.md'), 'utf8');

console.log(`分析中: ${url}（${settings.model}、thinking=${settings.thinkingLevel}）`);
try {
  const result = await analyzeYouTube({ settings, url, prompt, clip });
  const record = {
    meta: {
      url,
      video_id: id,
      clip,
      model: settings.model,
      model_version: result.modelVersion,
      thinking_level: settings.thinkingLevel,
      media_resolution: settings.mediaResolution,
      analyzed_at: new Date().toISOString(),
      attempts: result.attempts,
      usage: result.usage,
    },
    analysis: result.analysis,
  };
  const out = values.out ?? path.join(ANALYSES_DIR, `${id}.json`);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, `${JSON.stringify(record, null, 2)}\n`);
  const { chapters, scenes } = result.analysis;
  console.log(`保存しました: ${path.relative(process.cwd(), out)}（章 ${chapters.length}、シーン ${scenes.length}）`);
} catch (error) {
  if (error.rawText) {
    const raw = path.join(ANALYSES_DIR, `${id}.raw.txt`);
    fs.mkdirSync(ANALYSES_DIR, { recursive: true });
    fs.writeFileSync(raw, error.rawText);
    console.error(`Gemini の返答をそのまま保存しました: ${path.relative(process.cwd(), raw)}`);
  }
  console.error(error.message);
  process.exit(1);
}
