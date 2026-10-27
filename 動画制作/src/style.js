import fs from 'node:fs';
import path from 'node:path';
import { REPO_DIR } from './paths.js';

export const TOKENS_PATH = path.join(REPO_DIR, 'docs', 'style-tokens.json');
export const PROVISIONAL_PATH = path.join(REPO_DIR, 'config', 'render-provisional.json');

export class MissingTokenError extends Error {}

// 作風の数値は docs/style-tokens.json（実測値）と config/render-provisional.json（仮の値）からだけ読む。
// コードに色やサイズを直接書かないこと。使った値は used に記録し、報告に使う。
export class Style {
  constructor(tokensPath = TOKENS_PATH, provisionalPath = PROVISIONAL_PATH) {
    this.tokens = JSON.parse(fs.readFileSync(tokensPath, 'utf8'));
    this.provisionalValues = JSON.parse(fs.readFileSync(provisionalPath, 'utf8')).values;
    this.used = { tokens: {}, provisional: {} };
  }

  token(tokenPath) {
    const [group, name] = tokenPath.split('.', 2);
    const entry = this.tokens[group]?.[name];
    if (!entry) throw new Error(`トークン ${tokenPath} は docs/style-tokens.json にありません`);
    if (entry.value === null) {
      throw new MissingTokenError(
        `トークン ${tokenPath} は未計測（value が null）のため使えません。計測して docs/style-tokens.json に値を入れてください。メモ: ${entry.method ?? ''}`,
      );
    }
    this.used.tokens[tokenPath] = entry;
    return entry.value;
  }

  provisional(name) {
    const entry = this.provisionalValues[name];
    if (!entry) throw new Error(`仮の値 ${name} は config/render-provisional.json にありません`);
    this.used.provisional[name] = entry;
    return entry.value;
  }

  // value が null のトークンの一覧（'color.sepia_ocean' など）
  unmeasured() {
    return Object.entries(this.tokens)
      .filter(([, group]) => group && typeof group === 'object')
      .flatMap(([groupName, group]) => Object.entries(group)
        .filter(([, entry]) => entry && typeof entry === 'object' && 'value' in entry && entry.value === null)
        .map(([name]) => `${groupName}.${name}`));
  }
}
