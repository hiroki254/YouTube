import json
import pathlib
import re
import unittest

from pipeline.config import MissingTokenError, Style, hex_to_rgb
from pipeline.planner import PLAN_SCHEMA, validate_scene
from pipeline.scenes import Canvas, Subtitles, Typesetter, find_font, make_scene
from pipeline.script import gist_id_from_url, parse_script

ROOT = pathlib.Path(__file__).resolve().parent.parent


class StyleRulesTest(unittest.TestCase):
    def test_no_hardcoded_colors_in_code(self):
        for path in (ROOT / "pipeline").glob("*.py"):
            found = re.findall(r"#[0-9A-Fa-f]{6}\b", path.read_text(encoding="utf-8"))
            self.assertEqual(found, [], f"{path.name} に色が直接書かれています")

    def test_unmeasured_token_is_refused(self):
        with self.assertRaises(MissingTokenError):
            Style().color("sepia_ocean")

    def test_schema_gives_ai_no_style_fields(self):
        text = json.dumps(PLAN_SCHEMA)
        for word in ("color", "size", "font", "duration", "opacity", "width", "height", "position"):
            self.assertNotIn(f'"{word}', text)


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.style = Style()
        cls.canvas = Canvas(cls.style, Typesetter(*find_font()))

    def test_background_matches_measured_profile(self):
        H = self.canvas.H
        for pos, value in self.style.token("color.background_profile"):
            y = round(pos * (H - 1))
            self.assertEqual(self.canvas.background.getpixel((0, y))[:3], hex_to_rgb(value), f"y={pos}")

    def test_subtitle_sits_on_measured_line(self):
        layer = Subtitles(self.canvas).layer("字幕の位置を確かめる文です。", 0.1, 3.0)
        rows = [y for y in range(self.canvas.H)
                if any(layer.getpixel((x, y))[3] > 0 for x in range(0, self.canvas.W, 2))]
        center = (min(rows) + max(rows)) / 2 / self.canvas.H
        expected = self.style.token("layout.subtitle_center_y")
        self.assertAlmostEqual(center, expected, delta=0.02)

    def test_emphasis_uses_accent_yellow(self):
        scene = {"type": "statement", "headline": "黄色の強調", "emphasis": "黄色"}
        layer = make_scene(self.canvas, scene, None).layer(5.0, 6.0)
        colors = {layer.getpixel((x, y))[:3] for x in range(0, self.canvas.W, 2)
                  for y in range(0, self.canvas.H, 2) if layer.getpixel((x, y))[3] == 255}
        self.assertIn(self.style.color("accent_yellow"), colors)
        self.assertIn(self.style.color("text_white"), colors)

    def test_balanced_wrap_has_no_orphan(self):
        ts = self.canvas.ts
        font = ts.font(40)
        text = "この海峡の真ん中には、どこの国の領海でもない帯があるのでしょうか？"
        lines = ts.wrap(text, font, ts.width(text, font) * 0.9)
        self.assertEqual("".join(lines), text)
        self.assertGreater(min(len(line) for line in lines), 5)


class ScriptTest(unittest.TestCase):
    def test_parse_chapters_and_sentences(self):
        script = parse_script("# タイトル\n導入です。二文目！\n## 第一の章\n本文です？\n")
        self.assertEqual(script.title, "タイトル")
        self.assertEqual([s.text for s in script.sentences], ["導入です。", "二文目！", "第一の章", "本文です？"])
        self.assertTrue(script.sentences[2].is_chapter_card)
        self.assertEqual(script.sentences[3].chapter_number, 1)

    def test_gist_id(self):
        self.assertEqual(gist_id_from_url("https://gist.github.com/someone/0123456789abcdef0123"),
                         "0123456789abcdef0123")


class ValidationTest(unittest.TestCase):
    def test_place_outside_map_is_rejected(self):
        scene = {"type": "map", "map": {"lon_min": 140, "lat_min": 40, "lon_max": 141, "lat_max": 41,
                                        "places": [{"name": "外", "lon": 150, "lat": 40.5}],
                                        "connect": False, "distance_label": None}}
        self.assertTrue(validate_scene(scene, ""))

    def test_emphasis_must_be_in_headline(self):
        self.assertTrue(validate_scene({"type": "statement", "headline": "見出し", "emphasis": "別"}, ""))

    def test_dot_grid_limits(self):
        self.assertTrue(validate_scene({"type": "dot_grid", "dots": {"filled": 5, "total": 3, "label": ""}}, ""))
        self.assertFalse(validate_scene({"type": "dot_grid", "dots": {"filled": 3, "total": 5, "label": ""}}, ""))

    def test_sample_plan_is_valid(self):
        for scene in json.loads((ROOT / "examples" / "sample-scenes.json").read_text(encoding="utf-8")):
            if scene["type"] != "chapter":
                self.assertEqual(validate_scene(scene, ""), [], scene["index"])


class FakeStream:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        block = type("Block", (), {"type": "text", "text": json.dumps({"scenes": self.payload})})()
        return type("Message", (), {"stop_reason": "end_turn", "stop_details": None, "content": [block]})()


class FakeClient:
    """Claude API の代わり。呼ばれた引数を記録し、用意した応答を順に返す。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = type("Beta", (), {})()
        self.beta.messages = self

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.responses.pop(0))


def statement(index, headline):
    return {"index": index, "type": "statement", "headline": headline, "emphasis": None, "prefix": None,
            "number_value": None, "unit": None, "year_text": None, "map": None, "dots": None, "items": None}


class PlannerTest(unittest.TestCase):
    def test_retry_then_fallback(self):
        from pipeline.planner import plan_scenes
        script = parse_script("# t\n一文目。\n## 章\n二文目。\n")
        bad = {**statement(3, "見出し"), "emphasis": "ない語"}
        client = FakeClient([[statement(0, "一"), bad], [bad]])
        plan = plan_scenes(script, client=client, log=lambda *_: None)
        self.assertEqual([s["type"] for s in plan], ["statement", "chapter", "statement"])
        self.assertEqual(plan[2]["headline"], "二文目。")  # 2回とも不正なので文そのものに置き換え
        self.assertEqual(len(client.calls), 2)
        call = client.calls[0]
        self.assertEqual(call["model"], "claude-opus-5-5")
        self.assertEqual(call["fallbacks"], "default")
        self.assertEqual(call["output_config"]["format"]["schema"], PLAN_SCHEMA)
        self.assertNotIn("temperature", call)
        self.assertIn("二文目", client.calls[1]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
