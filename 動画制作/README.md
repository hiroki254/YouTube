# 動画制作

YouTube 動画を **Gemini 3.8 Flash** で分析して「編集構造」を取り出し、それを型にしてオリジナル動画の設計図を作る環境です（Node.js）。

```
YouTube の URL ──(Gemini 3.8 Flash)──▶ 分析 work/analyses/<動画ID>.json
                                          │  章の役割・シーンの種類・カメラ・つなぎ方・テンポ
                                          ▼
                              設計図 work/blueprints/<動画ID>.json
                                          │  尺の配分・描画できるシーンの種類の並び（内容は入れない）
                                          ▼
                       オリジナルの台本 → 描画（これから作る）
```

取り込むのは**作り方だけ**です。分析ではナレーションや画面の文字を書き写させず（スキーマに項目がありません）、設計図にも参照動画の内容は入りません。

## 準備（最初に1回）

```bash
cd 動画制作
npm install
cp .env.example .env   # GEMINI_API_KEY を入れる
npm run doctor -- --ping
```

API キーは [Google AI Studio](https://aistudio.google.com/apikey) で発行します。

| 設定（.env） | 既定 | 説明 |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.8-flash` | 分析に使うモデル |
| `GEMINI_THINKING_LEVEL` | `medium` | `low` / `medium` / `high` |
| `GEMINI_MEDIA_RESOLUTION` | 空欄（既定） | `low` にすると入力トークンが減る。長い動画向け |

## 使い方

```bash
# 1. 分析（公開動画のみ。--start / --end で一部だけも可）
npm run analyze -- https://youtu.be/ipw2kDkjNa8

# 2. 設計図（--target-sec で目標の長さに伸縮）
npm run blueprint -- work/analyses/ipw2kDkjNa8.json --target-sec 600
```

- 分析結果がスキーマに合わない・時刻の並びがおかしいときは、問題点を添えて Gemini に1回だけ直させます。それでもだめなら、返答を `work/analyses/<動画ID>.raw.txt` に残して止まります。
- 設計図のシーンの種類は、既存の描画（`../pipeline/`）と同じ6種類（statement / big_number / year / map / dot_grid / compare）です。写真・実写・タイムライン・図解・セピア地図は描画できないので代わりの種類に置き換え、`unsupported` に一覧で出します。
- `work/` は git に入れません。

## ファイル

| パス | 役割 |
|---|---|
| `src/gemini.js` | YouTube の URL をそのまま Gemini に渡し、JSON で受け取る |
| `src/validate.js` | 分析結果の検査（スキーマ＋時刻の並び・章の対応） |
| `src/blueprint.js` | 分析 → 設計図の変換（API は使わない） |
| `src/style.js` | 作風の数値の読み込み（`../docs/style-tokens.json` と `../config/render-provisional.json` だけを読む。未計測の値は使えない） |
| `src/youtube.js` / `src/env.js` / `src/paths.js` | URL の解釈、設定の読み込み、パス |
| `src/cli/` | `npm run analyze` / `npm run blueprint` の本体 |
| `schemas/analysis.schema.json` | Gemini に返させる編集構造の形 |
| `prompts/analyze.md` | 分析の指示文 |
| `scripts/doctor.js` | 環境の点検 |
| `test/` | `npm test`（テスト用データは架空のもの） |

## 注意

- Gemini は動画を既定で1秒1コマとして見るので、シーンの区切りの時刻は±1秒程度ずれます。細かいカットやイージングは読み取れません。
- 分析で得られる数値（尺の配分など）は、作風の数値（色・位置・サイズ）とは別物です。作風の数値は今まで通り `../docs/style-tokens.json` だけを使います。
