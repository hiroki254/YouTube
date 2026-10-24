"""台本（Gist）から動画を作る。

使い方:
    python -m pipeline.main --gist <Gist の URL> --out out/
試験用:
    python -m pipeline.main --script-file 台本.md --plan scenes.json --voice silent --out out/
"""

import argparse
import dataclasses
import json
import pathlib
import re

from .config import Style
from .geo import LandData
from .planner import load_plan, plan_scenes
from .render import render_video
from .script import load_script
from .voice import SilentVoice, Voicevox, build_narration


def safe_name(title):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip("_")[:60] or "video"


def main(argv=None):
    parser = argparse.ArgumentParser(description="台本から動画を作る")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--gist", help="台本を置いた Gist の URL")
    source.add_argument("--script-file", help="台本ファイル（試験用）")
    parser.add_argument("--plan", help="保存済みのシーン割り当て（scenes.json）。指定すると Claude を呼ばない")
    parser.add_argument("--voice", choices=["voicevox", "silent"], default="voicevox",
                        help="silent は試験専用（無音）")
    parser.add_argument("--voicevox-url", default="http://localhost:50021")
    parser.add_argument("--speaker", default="13", help="VOICEVOX の話者（スタイル）ID")
    parser.add_argument("--land", default="data/ne_10m_land.geojson", help="Natural Earth の陸地データ")
    parser.add_argument("--out", default="out")
    args = parser.parse_args(argv)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    style = Style()

    script = load_script(gist_url=args.gist, path=args.script_file)
    print(f"台本: {script.title}（{len(script.sentences)} 文）")
    (out / "script.json").write_text(
        json.dumps([dataclasses.asdict(s) for s in script.sentences], ensure_ascii=False, indent=2), encoding="utf-8")

    plan = load_plan(args.plan, script) if args.plan else plan_scenes(script)
    (out / "scenes.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {}
    for scene in plan:
        counts[scene["type"]] = counts.get(scene["type"], 0) + 1
    print("シーンの内訳: " + "、".join(f"{k} {v}" for k, v in sorted(counts.items())))

    engine = SilentVoice() if args.voice == "silent" else Voicevox(args.voicevox_url, args.speaker)
    print(f"音声エンジン: {engine.wait_ready()}")
    character, style_name = engine.speaker_credit()
    audio_path = out / "narration.wav"
    timeline, total = build_narration(script.sentences, engine, style, audio_path)

    video_path = out / f"{safe_name(script.title)}.mp4"
    land = LandData(args.land) if any(s["type"] == "map" for s in plan) else None
    render_video(plan, script.sentences, timeline, total, style, land, audio_path, video_path)

    credit = f"VOICEVOX:{character}" if args.voice == "voicevox" else character
    (out / "credits.txt").write_text(
        f"{credit}\n地図データ: Natural Earth\n", encoding="utf-8")
    (out / "style-report.md").write_text(style.report_markdown(), encoding="utf-8")
    print(f"完成: {video_path}（{total:.1f} 秒）")
    print(f"概要欄に入れるクレジット: {credit} / 地図データ: Natural Earth")


if __name__ == "__main__":
    main()
