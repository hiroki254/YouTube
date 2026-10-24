"""シーンの描画。色・位置・サイズはすべて Style（トークンと仮の値）から取る。"""

import math
import re

from PIL import Image, ImageDraw, ImageFont

from .geo import Projection

FONT_CANDIDATES = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),  # Noto Sans CJK JP Bold（Actions で導入）
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),  # ローカル試験用の代替
]
REFERENCE_GLYPH = "国"
PLAIN_NUMBER = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^\d+(?:\.\d+)?$")


def find_font():
    for path, index in FONT_CANDIDATES:
        try:
            ImageFont.truetype(path, 10, index=index)
            return path, index
        except OSError:
            continue
    raise FileNotFoundError("日本語フォントが見つかりません（fonts-noto-cjk を入れてください）")


class Typesetter:
    """「文字の高さ（px）」でフォントを選ぶ。高さは基準の字（国）の外接矩形の高さ。"""

    def __init__(self, font_path, font_index):
        self.path = font_path
        self.index = font_index
        probe = ImageFont.truetype(font_path, 200, index=font_index)
        top, bottom = probe.getbbox(REFERENCE_GLYPH, anchor="ls")[1::2]
        self.height_per_size = (bottom - top) / 200
        self.cache = {}

    def font(self, text_height_px):
        size = max(1, round(text_height_px / self.height_per_size))
        if size not in self.cache:
            self.cache[size] = ImageFont.truetype(self.path, size, index=self.index)
        return self.cache[size]

    @staticmethod
    def width(text, font):
        return font.getlength(text)

    @staticmethod
    def baseline_for_center(font, center_y):
        """基準の字の縦中心が center_y に来るベースライン位置。"""
        top, bottom = font.getbbox(REFERENCE_GLYPH, anchor="ls")[1::2]
        return center_y - (top + bottom) / 2

    def wrap(self, text, font, max_width):
        """max_width に収まる最少の行数で、各行の長さをそろえて折り返す（読点の直後を優先）。"""
        greedy, current = [], ""
        for ch in text:
            if current and self.width(current + ch, font) > max_width:
                greedy.append(current)
                current = ch
            else:
                current += ch
        if current:
            greedy.append(current)
        if len(greedy) <= 1:
            return greedy
        balanced = self._balanced(text, len(greedy))
        if all(self.width(line, font) <= max_width for line in balanced):
            return balanced
        return greedy

    @staticmethod
    def _balanced(text, count):
        lines, start = [], 0
        for n in range(1, count):
            target = round(len(text) * n / count)
            window = range(max(start + 1, target - 4), min(len(text) - 1, target + 4) + 1)
            breaks = [i for i in window if text[i - 1] in "、。，,・"]
            cut = min(breaks, key=lambda i: abs(i - target)) if breaks else target
            lines.append(text[start:cut])
            start = cut
        lines.append(text[start:])
        return [line for line in lines if line]


def with_opacity(layer, opacity):
    if opacity >= 1:
        return layer
    faded = layer.copy()
    faded.putalpha(layer.getchannel("A").point(lambda v: int(v * max(opacity, 0))))
    return faded


def rgba(color, alpha=255):
    return (*color, int(alpha))


class Canvas:
    """共通の寸法と色。"""

    def __init__(self, style, typesetter):
        self.style = style
        self.ts = typesetter
        self.W = style.token("format.width")
        self.H = style.token("format.height")
        self.fps = style.token("format.fps")
        self.white = style.color("text_white")
        self.yellow = style.color("accent_yellow")
        self.background = self._background()

    def _background(self):
        stops = [(pos, tuple(int(v.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))
                 for pos, v in self.style.token("color.background_profile")]
        column = Image.new("RGBA", (1, self.H))
        for y in range(self.H):
            pos = y / (self.H - 1)
            for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
                if p0 <= pos <= p1:
                    k = 0 if p1 == p0 else (pos - p0) / (p1 - p0)
                    column.putpixel((0, y), rgba(tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))))
                    break
        return column.resize((self.W, self.H), Image.NEAREST)

    def px_h(self, ratio):
        return ratio * self.H

    def px_w(self, ratio):
        return ratio * self.W

    def blank(self):
        return Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))

    def draw_runs(self, draw, x, baseline, runs, font, alpha=255):
        for text, color in runs:
            draw.text((x, baseline), text, font=font, fill=rgba(color, alpha), anchor="ls")
            x += self.ts.width(text, font)
        return x


def fade(style, local_t):
    return min(max(local_t / style.provisional("overlay_fade_sec"), 0.0), 1.0)


def progress(seconds, local_t):
    return min(max(local_t / seconds, 0.0), 1.0)


def ease_out(k):
    return 1 - (1 - k) ** 3


class StaticOverlayScene:
    """描画結果が時間で変わらず、フェードインするだけのシーン。"""

    def __init__(self, canvas):
        self.c = canvas
        self._overlay = None

    def build(self):
        raise NotImplementedError

    def layer(self, local_t, duration):
        if self._overlay is None:
            self._overlay = self.build()
        return with_opacity(self._overlay, fade(self.c.style, local_t))


class StatementScene(StaticOverlayScene):
    def __init__(self, canvas, scene):
        super().__init__(canvas)
        self.headline = scene["headline"]
        self.emphasis = scene.get("emphasis") or ""

    def build(self):
        c, s = self.c, self.c.style
        height = c.px_h(s.token("layout.statement_text_height"))
        font = c.ts.font(height)
        lines = c.ts.wrap(self.headline, font, c.px_w(s.provisional("statement_max_width")))
        step = height * (1 + s.provisional("statement_line_gap"))
        first_center = c.px_h(s.token("layout.statement_center_y")) - step * (len(lines) - 1) / 2
        start = self.headline.find(self.emphasis) if self.emphasis else -1
        emph = range(start, start + len(self.emphasis)) if start >= 0 else range(0)
        layer = c.blank()
        draw = ImageDraw.Draw(layer)
        offset = 0
        for i, line in enumerate(lines):
            runs = [(ch, c.yellow if offset + j in emph else c.white) for j, ch in enumerate(line)]
            offset += len(line)
            x = (c.W - c.ts.width(line, font)) / 2
            c.draw_runs(draw, x, c.ts.baseline_for_center(font, first_center + step * i), runs, font)
        return layer


class ChapterScene(StaticOverlayScene):
    def __init__(self, canvas, scene):
        super().__init__(canvas)
        self.number = str(scene["chapter_number"])
        self.title = scene["headline"]

    def build(self):
        c, s = self.c, self.c.style
        font = c.ts.font(c.px_h(s.token("layout.chapter_text_height")))
        layer = c.blank()
        draw = ImageDraw.Draw(layer)
        baseline = c.ts.baseline_for_center(font, c.px_h(s.token("layout.chapter_center_y")))
        c.draw_runs(draw, c.px_w(s.token("layout.chapter_left_x")), baseline,
                    [(self.number, c.yellow), ("章 " + self.title, c.white)], font)
        return layer


class YearScene(StaticOverlayScene):
    def __init__(self, canvas, scene):
        super().__init__(canvas)
        self.text = scene["year_text"]

    def build(self):
        c, s = self.c, self.c.style
        font = c.ts.font(c.px_h(s.token("layout.year_text_height")))
        skew = s.provisional("year_skew")
        upright = c.blank()
        draw = ImageDraw.Draw(upright)
        center_y = c.px_h(s.token("layout.year_center_y"))
        draw.text((c.px_w(s.token("layout.year_left_x")), c.ts.baseline_for_center(font, center_y)),
                  self.text, font=font, fill=rgba(c.white), anchor="ls")
        # 縦中心の行を動かさずに右へ傾ける（イタリック）
        return upright.transform(upright.size, Image.AFFINE, (1, skew, -skew * center_y, 0, 1, 0),
                                 resample=Image.BICUBIC)


def format_like(template, value):
    decimals = len(template.split(".")[1]) if "." in template else 0
    text = f"{value:,.{decimals}f}" if "," in template else f"{value:.{decimals}f}"
    return text


class BigNumberScene:
    def __init__(self, canvas, scene):
        self.c = canvas
        self.prefix = scene.get("prefix") or ""
        self.value = scene["number_value"]
        self.unit = scene.get("unit") or ""
        self.countable = bool(PLAIN_NUMBER.match(self.value))
        self.target = float(self.value.replace(",", "")) if self.countable else None

    def layer(self, local_t, duration):
        c, s = self.c, self.c.style
        count = progress(s.provisional("count_up_sec"), local_t)
        shown = format_like(self.value, self.target * ease_out(count)) if self.countable and count < 1 else self.value
        big = c.ts.font(c.px_h(s.provisional("big_number_text_height")))
        small = c.ts.font(c.px_h(s.provisional("big_number_text_height") * s.provisional("big_number_unit_ratio")))
        # 位置は最終の表記で決め、カウント中に左右へ揺れないようにする
        runs = [(self.prefix, self.prefix, c.white, small), (shown, self.value, c.yellow, big),
                (self.unit, self.unit, c.white, small)]
        x = (c.W - sum(c.ts.width(final, font) for _, final, _, font in runs)) / 2
        baseline = c.ts.baseline_for_center(big, c.px_h(s.provisional("big_number_center_y")))
        layer = c.blank()
        draw = ImageDraw.Draw(layer)
        for text, final, color, font in runs:
            if text:
                draw.text((x, baseline), text, font=font, fill=rgba(color), anchor="ls")
            x += c.ts.width(final, font)
        return with_opacity(layer, fade(s, local_t))


class DotGridScene:
    def __init__(self, canvas, scene):
        self.c = canvas
        self.filled = scene["dots"]["filled"]
        self.total = scene["dots"]["total"]
        self.label = scene["dots"]["label"]

    def layer(self, local_t, duration):
        c, s = self.c, self.c.style
        cols = min(s.provisional("dot_grid_columns"), self.total)
        rows = math.ceil(self.total / cols)
        cell = c.px_h(s.provisional("dot_grid_cell"))
        radius = cell * s.provisional("dot_grid_dot_ratio") / 2
        label_h = c.px_h(s.token("layout.statement_text_height"))
        font = c.ts.font(label_h)
        block_h = label_h * 2 + rows * cell
        top = c.px_h(s.token("layout.statement_center_y")) - block_h / 2
        left = (c.W - cols * cell) / 2
        layer = c.blank()
        draw = ImageDraw.Draw(layer)
        draw.text((c.W / 2, c.ts.baseline_for_center(font, top + label_h / 2)), self.label,
                  font=font, fill=rgba(c.white), anchor="ms")
        lit = round(self.filled * ease_out(progress(s.provisional("count_up_sec"), local_t)))
        dim = s.provisional("dot_grid_unfilled_opacity") * 255
        for i in range(self.total):
            cx = left + (i % cols + 0.5) * cell
            cy = top + label_h * 2 + (i // cols + 0.5) * cell
            fill = rgba(c.yellow) if i < lit else rgba(c.white, dim)
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=fill)
        return with_opacity(layer, fade(s, local_t))


class CompareScene:
    def __init__(self, canvas, scene):
        self.c = canvas
        self.items = scene["items"]

    def layer(self, local_t, duration):
        c, s = self.c, self.c.style
        bar_h = c.px_h(s.provisional("compare_bar_height"))
        step = bar_h * (1 + s.provisional("compare_row_gap"))
        font = c.ts.font(c.px_h(s.provisional("map_label_text_height")))
        label_w = c.px_w(s.provisional("compare_label_width"))
        max_w = c.px_w(s.provisional("compare_bar_max_width"))
        left = (c.W - label_w - max_w) / 2
        top = c.px_h(s.token("layout.statement_center_y")) - step * len(self.items) / 2
        grow = ease_out(progress(s.provisional("count_up_sec"), local_t))
        biggest = max(i["value"] for i in self.items)
        layer = c.blank()
        draw = ImageDraw.Draw(layer)
        for n, item in enumerate(self.items):
            y = top + n * step + (step - bar_h) / 2
            baseline = c.ts.baseline_for_center(font, y + bar_h / 2)
            draw.text((left + label_w - font.size / 2, baseline), item["label"], font=font,
                      fill=rgba(c.white), anchor="rs")
            length = max_w * item["value"] / biggest * grow
            draw.rectangle((left + label_w, y, left + label_w + length, y + bar_h), fill=rgba(c.white))
            draw.text((left + label_w + length + font.size / 2, baseline), item["value_text"], font=font,
                      fill=rgba(c.yellow), anchor="ls")
        return with_opacity(layer, fade(s, local_t))


class MapScene:
    """陸地（ベタ塗り）＋地点・ルート・距離線。背景は動かさず、この層だけをゆっくりズームする。"""

    supersample = 2

    def __init__(self, canvas, scene, land):
        self.c = canvas
        self.m = scene["map"]
        s = canvas.style
        padding = s.provisional("map_padding") * min(canvas.W, canvas.H)
        self.proj = Projection(self.m["lon_min"], self.m["lat_min"], self.m["lon_max"], self.m["lat_max"],
                               canvas.W, canvas.H, padding)
        self.land_layer = self._land(land)
        self.points = [self.proj(p["lon"], p["lat"]) for p in self.m["places"]]
        self._final = None

    def _land(self, land):
        c, k = self.c, self.supersample
        mask = Image.new("L", (c.W * k, c.H * k), 0)
        draw = ImageDraw.Draw(mask)
        for rings in land.polygons_in(*self.proj.view):
            for n, ring in enumerate(rings):
                pts = [tuple(v * k for v in self.proj(lon, lat)) for lon, lat in ring]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=255 if n == 0 else 0)
        mask = mask.resize((c.W, c.H), Image.LANCZOS)
        layer = Image.new("RGBA", (c.W, c.H), rgba(c.style.color("land")))
        layer.putalpha(mask)
        return layer

    def _overlay(self, local_t):
        c, s = self.c, self.c.style
        layer = self.land_layer.copy()
        draw = ImageDraw.Draw(layer)
        width = max(1, round(c.px_h(s.provisional("map_line_width"))))
        appear = fade(s, local_t)
        if self.m["connect"] and len(self.points) > 1:
            self._partial_line(draw, self.points, progress(s.provisional("line_draw_sec"), local_t), width)
        font = c.ts.font(c.px_h(s.provisional("map_label_text_height")))
        if self.m["distance_label"] and len(self.points) > 1:
            self._bracket(draw, self.points[0], self.points[1], self.m["distance_label"], font, width, appear)
        radius = c.px_h(s.provisional("map_point_radius"))
        offset = c.px_h(s.provisional("map_label_offset"))
        for (x, y), place in zip(self.points, self.m["places"]):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rgba(c.white, 255 * appear))
            draw.text((x + radius + offset, c.ts.baseline_for_center(font, y)), place["name"], font=font,
                      fill=rgba(c.white, 255 * appear), anchor="ls")
        return layer

    def _partial_line(self, draw, points, k, width):
        lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
        remaining = sum(lengths) * k
        for (a, b), length in zip(zip(points, points[1:]), lengths):
            if remaining <= 0:
                break
            part = min(1.0, remaining / length) if length else 1.0
            end = (a[0] + (b[0] - a[0]) * part, a[1] + (b[1] - a[1]) * part)
            draw.line([a, end], fill=rgba(self.c.white), width=width)
            remaining -= length

    def _bracket(self, draw, a, b, label, font, width, appear):
        """2地点の間の距離線（両端に短い縦線）と、中央の上のラベル。"""
        alpha = 255 * appear
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy) or 1
        nx, ny = -dy / norm, dx / norm
        tick = font.size / 2
        draw.line([a, b], fill=rgba(self.c.white, alpha), width=width)
        for p in (a, b):
            draw.line([(p[0] - nx * tick, p[1] - ny * tick), (p[0] + nx * tick, p[1] + ny * tick)],
                      fill=rgba(self.c.white, alpha), width=width)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        draw.text((mid[0], mid[1] - tick * 2), label, font=font, fill=rgba(self.c.white, alpha), anchor="ms")

    def layer(self, local_t, duration):
        s = self.c.style
        settled = local_t >= max(s.provisional("line_draw_sec"), s.provisional("overlay_fade_sec"))
        if settled:
            if self._final is None:
                self._final = self._overlay(local_t)
            layer = self._final
        else:
            layer = self._overlay(local_t)
        zoom = 1 + (s.provisional("map_zoom_end") - 1) * min(max(local_t / max(duration, 1e-6), 0), 1)
        if zoom <= 1:
            return layer
        W, H = self.c.W, self.c.H
        cw, ch = W / zoom, H / zoom
        box = ((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)
        return layer.resize((W, H), Image.BICUBIC, box=box)


def make_scene(canvas, scene, land):
    kind = scene["type"]
    if kind == "map":
        return MapScene(canvas, scene, land)
    return {"statement": StatementScene, "chapter": ChapterScene, "year": YearScene,
            "big_number": BigNumberScene, "dot_grid": DotGridScene, "compare": CompareScene}[kind](canvas, scene)


class Subtitles:
    """文を字幕1行に収まる長さで区切り、話している間に順に出す。"""

    def __init__(self, canvas):
        self.c = canvas
        s = canvas.style
        self.font = canvas.ts.font(canvas.px_h(s.token("layout.subtitle_text_height")))
        self.max_width = canvas.px_w(s.provisional("subtitle_max_width"))
        self.baseline = canvas.ts.baseline_for_center(self.font, canvas.px_h(s.token("layout.subtitle_center_y")))
        assert s.token("layout.subtitle_align") == "center"
        self.cache = {}

    def chunks(self, text):
        return self.c.ts.wrap(text, self.font, self.max_width)

    def layer(self, text, local_t, speech_duration):
        pieces = self.chunks(text)
        total_chars = sum(len(p) for p in pieces)
        elapsed = 0
        chosen = pieces[-1]
        for piece in pieces:
            elapsed += len(piece)
            if local_t < speech_duration * elapsed / total_chars:
                chosen = piece
                break
        if chosen not in self.cache:
            layer = self.c.blank()
            ImageDraw.Draw(layer).text((self.c.W / 2, self.baseline), chosen, font=self.font,
                                       fill=rgba(self.c.white), anchor="ms")
            self.cache[chosen] = layer
        return self.cache[chosen]
