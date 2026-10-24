# 台本から動画を自動で作る仕組み

Gist に置いた台本の URL を入れてボタンを押すと、MP4 が出てきます。

```
Gist の台本 → 1文ずつに分ける → Claude が各文にシーンを割り当てる
            → VOICEVOX でナレーション → 作風の数値どおりに描画 → MP4
```

## 最初に1回だけやること

1. **Anthropic の API キーを登録する**
   GitHub のリポジトリ → Settings → Secrets and variables → Actions → New repository secret
   名前：`ANTHROPIC_API_KEY`、値：API キー
2. **このブランチを main にマージする**
   ボタン（workflow_dispatch）は、デフォルトブランチにワークフローがあるときだけ表示されます。

## 動画を作る

1. 台本を Gist に置く（公開・非公開どちらでも可）
2. GitHub の **Actions** タブ → **台本から動画を作る** → **Run workflow**
3. Gist の URL と話者 ID を入れて実行
4. 終わったら、実行結果のページ下部の **Artifacts** から `video` をダウンロード

実行結果のページ（Summary）には、使った作風の数値の一覧と、概要欄に入れるクレジットが出ます。

## 台本の書き方

```markdown
# 動画のタイトル
導入の文。2つ目の文。

## 章の名前
本文の文。本文の文？
```

- `# ` で始まる行：動画のタイトル（ファイル名になる）
- `## ` で始まる行：章。「1章、〇〇」と読み上げ、章カード（黄色の番号＋白の章名）を出す
- それ以外：本文。「。」「！」「？」と改行で1文に区切る。1文が1シーンになる

## Claude が選ぶシーン

| 種類 | 使う場面 | 画面 |
|---|---|---|
| `map` | 地名・海峡・ルートが出てくる文 | 濃紺の海に陸地、白い地点と地名、ルート線、距離線。ゆっくりズーム |
| `big_number` | 主役が1つの数字の文 | 黄色の大きな数字（カウントアップ）＋白い単位 |
| `year` | 年号・時代が区切りになる文 | 白の太いイタリックの年号を左寄りに |
| `dot_grid` | 割合の文 | 点を並べ、該当分を黄色に |
| `compare` | 2〜6個の量を比べる文 | 白い棒グラフ＋黄色の数値 |
| `statement` | それ以外 | 画面中央の見出し。強調部分だけ黄色 |

Claude が決めるのは「種類」と「中身」だけです。色・位置・サイズ・尺はスキーマに入っていないので、Claude には変えられません。割り当ての結果が不正（地点が地図の範囲外、数字のない big_number など）なら1回だけ直させ、それでもだめな文は statement にします。

## 作風の数値を守らせる仕組み

- 描画のコードは、数値を `docs/style-tokens.json`（実測値）と `config/render-provisional.json`（仮の値）からだけ読みます。
- テストで次を確かめ、通らなければ動画を作りません。
  - コードに色が直接書かれていない
  - 背景の色が実測のグラデーションと1画素単位で一致する
  - 字幕が実測の高さにある
  - 未計測のトークン（値が null）を使おうとすると止まる
  - AI に渡すスキーマに色・サイズ・位置の項目がない
- 動画ごとに `style-report.md` を出し、使った実測値（誤差のある値を含む）と仮の値を一覧にします。

## いまの制限

- **地図は陸地のベタ塗りです。** 参照動画のような衛星写真の質感や、斜めから見下ろす3D表現はありません。陸の色は、参照動画の陸の平均色（実測）です。浅瀬の水色の縁取りは、色を計測できていないので描いていません。
- **歴史パートのセピア地図は使えません。** 色が未計測（null）のためです。計測して値を入れれば使えるようにできます。
- **仮の値があります。** 大きな数字の大きさ、地名ラベルの大きさ、アニメーションの長さなどは計測できず、`config/render-provisional.json` に仮の値として置いています。
- **写真は入りません。** 実写写真のシーンは、権利の確認が必要なため、仕組みには入れていません。
- **地図の座標は Claude が出します。** 範囲外の地点などの明らかな誤りは検証で弾きますが、位置が少しずれている可能性はあります。`scenes.json` を確認してください。

## 手元で試す

```bash
pip install -r requirements.txt
docker run -d --rm -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu22.04-0.25.2
mkdir -p data && curl -sSfL -o data/ne_10m_land.geojson \
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_land.geojson

# Claude を呼ばずに、保存済みの割り当てで作る
python -m pipeline.main --script-file examples/sample-script.md --plan examples/sample-scenes.json --out out/sample

# テスト
python -m unittest discover -s tests -t .
```

## クレジット

VOICEVOX の音声を使った動画には、`VOICEVOX:キャラクター名` の表記が必要です（各キャラクターの利用規約も確認してください）。地図は Natural Earth（パブリックドメイン）を使っています。どちらも `credits.txt` に出ます。
