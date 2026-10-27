import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it } from 'node:test';
import { buildBlueprint, SCENE_KINDS, VISUAL_TO_KIND } from '../src/blueprint.js';
import { geminiSettings } from '../src/env.js';
import { PROJECT_DIR, REPO_DIR } from '../src/paths.js';
import { MissingTokenError, Style } from '../src/style.js';
import { ANALYSIS_SCHEMA, checkAnalysis } from '../src/validate.js';
import { parseYouTubeUrl } from '../src/youtube.js';

const sample = () => JSON.parse(fs.readFileSync(path.join(PROJECT_DIR, 'test', 'fixtures', 'sample-analysis.json'), 'utf8'));
const sceneProps = ANALYSIS_SCHEMA.properties.scenes.items.properties;

describe('YouTube の URL', () => {
  it('いろいろな形の URL から動画IDを取り出す', () => {
    for (const input of [
      'https://youtu.be/ipw2kDkjNa8',
      'https://youtu.be/ipw2kDkjNa8?si=abc',
      'https://www.youtube.com/watch?v=ipw2kDkjNa8&t=30s',
      'https://m.youtube.com/watch?v=ipw2kDkjNa8',
      'https://www.youtube.com/shorts/ipw2kDkjNa8',
    ]) {
      assert.deepEqual(parseYouTubeUrl(input), { id: 'ipw2kDkjNa8', url: 'https://www.youtube.com/watch?v=ipw2kDkjNa8' });
    }
  });

  it('YouTube 以外や動画IDのない URL は断る', () => {
    for (const input of ['https://example.com/watch?v=ipw2kDkjNa8', 'https://www.youtube.com/', 'not a url']) {
      assert.throws(() => parseYouTubeUrl(input));
    }
  });
});

describe('分析結果の検査', () => {
  it('正しい分析結果は通る', () => {
    assert.deepEqual(checkAnalysis(sample().analysis), []);
  });

  it('時間順の乱れ・存在しない章・長さの外を見つける', () => {
    const { analysis } = sample();
    analysis.scenes[1].start_sec = -5;
    analysis.scenes[2].chapter_index = 9;
    analysis.scenes[4].end_sec = 500;
    const problems = checkAnalysis(analysis);
    assert.ok(problems.some((p) => p.includes('時間順')));
    assert.ok(problems.some((p) => p.includes('chapter_index 9')));
    assert.ok(problems.some((p) => p.includes('長さ')));
  });

  it('スキーマに書き起こしの項目がない（参照動画の文章を持ち込まない）', () => {
    const text = JSON.stringify(ANALYSIS_SCHEMA);
    for (const word of ['transcript', 'narration_text', 'quote', 'script', 'on_screen_text']) {
      assert.ok(!text.includes(`"${word}`), `${word} がスキーマにあります`);
    }
  });
});

describe('設計図', () => {
  it('シーンの種類が pipeline/planner.py の SCENE_TYPES と一致する', () => {
    const planner = fs.readFileSync(path.join(REPO_DIR, 'pipeline', 'planner.py'), 'utf8');
    const list = planner.match(/^SCENE_TYPES = \[(.*)\]$/m)[1];
    assert.deepEqual(SCENE_KINDS, [...list.matchAll(/"(\w+)"/g)].map((m) => m[1]));
  });

  it('分析のすべての visual_type に描画の種類が割り当ててある', () => {
    assert.deepEqual(Object.keys(VISUAL_TO_KIND).sort(), [...sceneProps.visual_type.enum].sort());
    for (const { kind } of Object.values(VISUAL_TO_KIND)) assert.ok(SCENE_KINDS.includes(kind));
  });

  it('目標の長さに合わせて尺を伸縮し、未対応の演出を書き出す', () => {
    const blueprint = buildBlueprint(sample(), { targetSec: 60 });
    assert.equal(blueprint.total_sec, 60);
    assert.deepEqual(blueprint.chapters.map((c) => c.duration_sec), [15, 25, 20]);
    assert.equal(blueprint.sequence.reduce((sum, s) => sum + s.duration_sec, 0), 60);
    assert.deepEqual(blueprint.unsupported.map((u) => u.visual_type).sort(), ['historic_map', 'photo']);
    assert.equal(blueprint.sequence[4].kind, 'compare');
  });
});

describe('作風の数値', () => {
  it('未計測のトークンは使えない', () => {
    assert.throws(() => new Style().token('color.sepia_ocean'), MissingTokenError);
    assert.ok(new Style().unmeasured().includes('color.sepia_land'));
  });

  it('コードに色が直接書かれていない', () => {
    const dirs = ['src', 'scripts'].map((d) => path.join(PROJECT_DIR, d));
    const files = dirs.flatMap((d) => fs.readdirSync(d, { recursive: true }).filter((f) => f.endsWith('.js')).map((f) => path.join(d, f)));
    for (const file of files) {
      assert.deepEqual(fs.readFileSync(file, 'utf8').match(/#[0-9A-Fa-f]{6}\b/g) ?? [], [], file);
    }
  });
});

describe('Gemini の設定', () => {
  it('既定のモデルは Gemini 3.8 Flash', () => {
    assert.equal(geminiSettings({ GEMINI_API_KEY: 'x' }).model, 'gemini-3.8-flash');
  });

  it('API キーがない・考える深さが不正なら止まる', () => {
    assert.throws(() => geminiSettings({}), /GEMINI_API_KEY/);
    assert.throws(() => geminiSettings({ GEMINI_API_KEY: 'x', GEMINI_THINKING_LEVEL: 'minimal' }), /THINKING/);
  });
});
