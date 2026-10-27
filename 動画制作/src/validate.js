import fs from 'node:fs';
import path from 'node:path';
import Ajv from 'ajv';
import { PROJECT_DIR } from './paths.js';

export const ANALYSIS_SCHEMA = JSON.parse(
  fs.readFileSync(path.join(PROJECT_DIR, 'schemas', 'analysis.schema.json'), 'utf8'),
);

const ajv = new Ajv({ allErrors: true });
const validateSchema = ajv.compile(ANALYSIS_SCHEMA);

// スキーマの形と、時刻の並びなどスキーマでは書けない約束を確かめる。問題の一覧を返す（空なら OK）
export function checkAnalysis(analysis) {
  if (!validateSchema(analysis)) {
    return validateSchema.errors.map((e) => `${e.instancePath || '(全体)'} ${e.message}`);
  }
  const problems = [];
  const duration = analysis.video.duration_sec;
  const chapterIds = new Set(analysis.chapters.map((c) => c.index));
  const checkSpans = (items, label) => {
    items.forEach((item, i) => {
      if (!(item.end_sec > item.start_sec)) problems.push(`${label}[${i}] の end_sec が start_sec 以下です`);
      if (item.start_sec < 0 || item.end_sec > duration + 1) problems.push(`${label}[${i}] が動画の長さ（${duration}秒）の外にあります`);
      if (i > 0 && item.start_sec < items[i - 1].start_sec) problems.push(`${label}[${i}] が時間順に並んでいません`);
    });
  };
  if (analysis.chapters.length === 0) problems.push('chapters が空です');
  if (analysis.scenes.length === 0) problems.push('scenes が空です');
  checkSpans(analysis.chapters, 'chapters');
  checkSpans(analysis.scenes, 'scenes');
  analysis.scenes.forEach((s, i) => {
    if (!chapterIds.has(s.chapter_index)) problems.push(`scenes[${i}] の chapter_index ${s.chapter_index} に当たる章がありません`);
  });
  return problems;
}
