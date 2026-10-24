"""各文に合う画面（シーン）を Claude に割り当てさせる。

Claude が決めるのは「シーンの種類」と「中身（見出し・数字・地点など）」だけ。
色・位置・サイズ・尺はスキーマに含めておらず、Claude は作風の数値に触れられない。
数値はすべて描画側が docs/style-tokens.json から読む。
"""

import json

import anthropic

MODEL = "claude-opus-5-5"
SCENE_TYPES = ["statement", "big_number", "year", "map", "dot_grid", "compare"]

SYSTEM_PROMPT = """あなたは地理解説動画の映像ディレクターです。
ナレーション台本の各文に、画面に出す「シーン」を1つずつ割り当てます。
映像は濃紺の海の地図を基調にした、落ち着いたドキュメンタリー調のインフォグラフィックです。
色・大きさ・位置・動きの速さは別の仕組みで決まるので、あなたは「どの種類のシーンで、何を見せるか」だけを決めます。

シーンの種類:
- map: 文に具体的な地名・海峡・島・都市・ルートが出てくるとき。範囲（経度緯度の矩形）と地点を指定する。
  - 座標は WGS84 の実在する位置を正確に。確信がない地点は入れない。地点は必ず範囲の内側に置く。
  - 範囲は地点が収まり、周りの地形がわかる程度に取る。
  - connect=true で地点を順番に線で結ぶ（航路・移動の説明）。
  - distance_label は最初の2地点の間の距離ラベル（例「約14km」）。文に距離が書かれているときだけ使う。
- big_number: 文の主役が1つの数字のとき（例「1日140便」）。number_value は数字部分、prefix と unit は前後の短い語。
- year: 年号や時代が話の区切りになるとき（例「1905」「1920年代」）。
- dot_grid: 割合・比率を見せるとき。total 個のうち filled 個を色付きにする。total は 100 以下。
- compare: 2〜6個の量を比べるとき。value は比較用の数値、value_text は画面に出す表記。
- statement: 上のどれにも当たらないとき。問いかけや要点を短い見出しにする（30文字以内）。emphasis は見出しの中で強調する部分（見出しに含まれる文字列）。

ルール:
- 数字は文に書かれているものだけを使う。文にない数字を作らない。
- 同じ場所の話が続くときは、同じ範囲の map を続けて使ってよい。
- 使わない項目は null にする。
"""

PLACE = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "lon": {"type": "number"}, "lat": {"type": "number"}},
    "required": ["name", "lon", "lat"],
    "additionalProperties": False,
}
MAP = {
    "type": "object",
    "properties": {
        "lon_min": {"type": "number"}, "lat_min": {"type": "number"},
        "lon_max": {"type": "number"}, "lat_max": {"type": "number"},
        "places": {"type": "array", "items": PLACE},
        "connect": {"type": "boolean"},
        "distance_label": {"type": ["string", "null"]},
    },
    "required": ["lon_min", "lat_min", "lon_max", "lat_max", "places", "connect", "distance_label"],
    "additionalProperties": False,
}
DOTS = {
    "type": "object",
    "properties": {"filled": {"type": "integer"}, "total": {"type": "integer"}, "label": {"type": "string"}},
    "required": ["filled", "total", "label"],
    "additionalProperties": False,
}
ITEM = {
    "type": "object",
    "properties": {"label": {"type": "string"}, "value": {"type": "number"}, "value_text": {"type": "string"}},
    "required": ["label", "value", "value_text"],
    "additionalProperties": False,
}
NULLABLE_STRING = {"type": ["string", "null"]}
SCENE = {
    "type": "object",
    "properties": {
        "index": {"type": "integer"},
        "type": {"type": "string", "enum": SCENE_TYPES},
        "headline": NULLABLE_STRING,
        "emphasis": NULLABLE_STRING,
        "prefix": NULLABLE_STRING,
        "number_value": NULLABLE_STRING,
        "unit": NULLABLE_STRING,
        "year_text": NULLABLE_STRING,
        "map": {"anyOf": [MAP, {"type": "null"}]},
        "dots": {"anyOf": [DOTS, {"type": "null"}]},
        "items": {"anyOf": [{"type": "array", "items": ITEM}, {"type": "null"}]},
    },
    "required": ["index", "type", "headline", "emphasis", "prefix", "number_value", "unit",
                 "year_text", "map", "dots", "items"],
    "additionalProperties": False,
}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {"scenes": {"type": "array", "items": SCENE}},
    "required": ["scenes"],
    "additionalProperties": False,
}


class PlanningError(Exception):
    pass


def validate_scene(scene, sentence_text):
    """問題点のリストを返す（空なら合格）。"""
    kind = scene.get("type")
    errors = []
    if kind == "statement":
        if not scene.get("headline"):
            errors.append("statement に headline がない")
        elif scene.get("emphasis") and scene["emphasis"] not in scene["headline"]:
            errors.append("emphasis が headline に含まれていない")
    elif kind == "big_number":
        if not scene.get("number_value"):
            errors.append("big_number に number_value がない")
        elif not any(ch.isdigit() for ch in scene["number_value"]):
            errors.append("number_value に数字がない")
    elif kind == "year":
        if not scene.get("year_text"):
            errors.append("year に year_text がない")
    elif kind == "map":
        m = scene.get("map")
        if not m:
            errors.append("map に map がない")
        else:
            if not (-180 <= m["lon_min"] < m["lon_max"] <= 180 and -90 <= m["lat_min"] < m["lat_max"] <= 90):
                errors.append("map の範囲が不正（min < max、経度±180・緯度±90 の内側）")
            for p in m["places"]:
                if not (m["lon_min"] <= p["lon"] <= m["lon_max"] and m["lat_min"] <= p["lat"] <= m["lat_max"]):
                    errors.append(f"地点「{p['name']}」が範囲の外にある")
            if m["connect"] and len(m["places"]) < 2:
                errors.append("connect=true なのに地点が2つ未満")
            if m["distance_label"] and len(m["places"]) < 2:
                errors.append("distance_label があるのに地点が2つ未満")
    elif kind == "dot_grid":
        d = scene.get("dots")
        if not d:
            errors.append("dot_grid に dots がない")
        elif not (0 <= d["filled"] <= d["total"] <= 100 and d["total"] > 0):
            errors.append("dots は 0 <= filled <= total <= 100、total > 0 にする")
    elif kind == "compare":
        items = scene.get("items")
        if not items or not 2 <= len(items) <= 6:
            errors.append("compare の items は 2〜6 個にする")
        elif any(i["value"] < 0 for i in items) or max(i["value"] for i in items) <= 0:
            errors.append("compare の value は 0 以上で、最大値は 0 より大きくする")
    else:
        errors.append(f"未知のシーン種類 {kind}")
    return errors


def fallback_scene(index, text):
    return {"index": index, "type": "statement", "headline": text, "emphasis": None, "prefix": None,
            "number_value": None, "unit": None, "year_text": None, "map": None, "dots": None, "items": None}


def request_plan(client, lines, feedback=None):
    content = "次の台本の各文にシーンを割り当ててください。index は文の番号と同じにしてください。\n\n" + "\n".join(lines)
    if feedback:
        content += "\n\n前回の割り当てには次の問題がありました。直してください。\n" + "\n".join(feedback)
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise PlanningError(f"Claude がシーン割り当てを断りました: {message.stop_details}")
    if message.stop_reason == "max_tokens":
        raise PlanningError("出力が上限に達しました。台本を短く分けてください。")
    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)["scenes"]


def plan_scenes(script, client=None, log=print):
    """台本の各文に対応するシーンのリストを返す（章カードは固定の chapter シーン）。"""
    body = [s for s in script.sentences if not s.is_chapter_card]
    lines = [f"{s.index}: {s.text}" for s in body]
    client = client or anthropic.Anthropic()
    texts = {s.index: s.text for s in body}

    def check(scenes):
        by_index, problems = {}, []
        for scene in scenes:
            idx = scene.get("index")
            if idx not in texts:
                problems.append(f"index {idx} は台本にない")
                continue
            errors = validate_scene(scene, texts[idx])
            if errors:
                problems.append(f"{idx}: " + "、".join(errors))
            else:
                by_index[idx] = scene
        missing = [i for i in texts if i not in by_index]
        problems += [f"{i}: シーンがない" for i in missing if not any(p.startswith(f"{i}:") for p in problems)]
        return by_index, problems

    by_index, problems = check(request_plan(client, lines))
    if problems:
        log(f"シーン割り当てに {len(problems)} 件の問題。1回だけ直させます。")
        retry, problems = check(request_plan(client, lines, feedback=problems))
        by_index = {**by_index, **retry}
    for idx in texts:
        if idx not in by_index:
            log(f"文 {idx} は割り当てに失敗したため、文をそのまま見出しにします")
            by_index[idx] = fallback_scene(idx, texts[idx])
    return build_plan(script, by_index)


def build_plan(script, by_index):
    plan = []
    for s in script.sentences:
        if s.is_chapter_card:
            plan.append({"index": s.index, "type": "chapter", "chapter_number": s.chapter_number,
                         "headline": s.chapter_title})
        else:
            plan.append({**by_index[s.index], "index": s.index})
    return plan


def load_plan(path, script):
    """保存済みの割り当て（scenes.json）を読み直し、検証する。"""
    with open(path, encoding="utf-8") as f:
        scenes = json.load(f)
    by_index = {}
    for scene in scenes:
        if scene["type"] == "chapter":
            continue
        errors = validate_scene(scene, "")
        if errors:
            raise PlanningError(f"{path} の文 {scene['index']}: " + "、".join(errors))
        by_index[scene["index"]] = scene
    missing = [s.index for s in script.sentences if not s.is_chapter_card and s.index not in by_index]
    if missing:
        raise PlanningError(f"{path} に文 {missing} のシーンがありません")
    return build_plan(script, by_index)
