"""Natural Earth の陸地データと、経度緯度から画面座標への変換。"""

import json
import math


class LandData:
    def __init__(self, geojson_path):
        with open(geojson_path, encoding="utf-8") as f:
            data = json.load(f)
        self.polygons = []
        for feature in data["features"]:
            geometry = feature["geometry"]
            if geometry is None:
                continue
            if geometry["type"] == "Polygon":
                parts = [geometry["coordinates"]]
            elif geometry["type"] == "MultiPolygon":
                parts = geometry["coordinates"]
            else:
                continue
            for rings in parts:
                xs = [p[0] for p in rings[0]]
                ys = [p[1] for p in rings[0]]
                self.polygons.append(((min(xs), min(ys), max(xs), max(ys)), rings))

    def polygons_in(self, lon_min, lat_min, lon_max, lat_max):
        for (x0, y0, x1, y1), rings in self.polygons:
            if x1 >= lon_min and x0 <= lon_max and y1 >= lat_min and y0 <= lat_max:
                yield rings


class Projection:
    """経度方向を中央緯度の cos で縮める正距円筒図法。範囲を余白付きで画面に収める。"""

    def __init__(self, lon_min, lat_min, lon_max, lat_max, width, height, padding_px):
        self.kx = math.cos(math.radians((lat_min + lat_max) / 2))
        span_x = (lon_max - lon_min) * self.kx
        span_y = lat_max - lat_min
        self.scale = min((width - 2 * padding_px) / span_x, (height - 2 * padding_px) / span_y)
        self.cx = (lon_min + lon_max) / 2
        self.cy = (lat_min + lat_max) / 2
        self.width = width
        self.height = height
        # 画面全体に入る経度緯度の範囲（陸地の切り出しに使う）
        half_w = width / 2 / self.scale / self.kx
        half_h = height / 2 / self.scale
        self.view = (self.cx - half_w, self.cy - half_h, self.cx + half_w, self.cy + half_h)

    def __call__(self, lon, lat):
        x = self.width / 2 + (lon - self.cx) * self.kx * self.scale
        y = self.height / 2 - (lat - self.cy) * self.scale
        return x, y
