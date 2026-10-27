// 使い方: npm run blueprint -- <分析ファイル> [--target-sec 秒] [--out ファイル]
import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { buildBlueprint } from '../blueprint.js';
import { BLUEPRINTS_DIR } from '../paths.js';
import { checkAnalysis } from '../validate.js';

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    'target-sec': { type: 'string' },
    out: { type: 'string' },
  },
});
if (positionals.length !== 1) {
  console.error('使い方: npm run blueprint -- <分析ファイル> [--target-sec 秒] [--out ファイル]');
  process.exit(1);
}

const record = JSON.parse(fs.readFileSync(positionals[0], 'utf8'));
const problems = checkAnalysis(record.analysis);
if (problems.length) {
  console.error(`分析ファイルが不正です:\n- ${problems.join('\n- ')}`);
  process.exit(1);
}
let targetSec = null;
if (values['target-sec'] != null) {
  targetSec = Number(values['target-sec']);
  if (!(targetSec > 0)) {
    console.error(`--target-sec は正の秒数で指定してください: ${values['target-sec']}`);
    process.exit(1);
  }
}

const blueprint = buildBlueprint(record, { targetSec });
const name = path.basename(positionals[0], '.json');
const out = values.out ?? path.join(BLUEPRINTS_DIR, `${name}.json`);
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, `${JSON.stringify(blueprint, null, 2)}\n`);
console.log(`保存しました: ${path.relative(process.cwd(), out)}（${blueprint.total_sec}秒、章 ${blueprint.chapters.length}、シーン ${blueprint.pacing.scene_count}）`);
for (const item of blueprint.unsupported) {
  console.log(`注意: ${item.visual_type} × ${item.count} — ${item.note}`);
}
