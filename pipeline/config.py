"""作風の数値を読み込む。

数値は docs/style-tokens.json（実測値）と config/render-provisional.json（仮の値）からだけ取る。
コードに色やサイズを直接書かないこと。使った値はすべて記録し、style-report.md に書き出す。
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKENS_PATH = ROOT / "docs" / "style-tokens.json"
PROVISIONAL_PATH = ROOT / "config" / "render-provisional.json"


class MissingTokenError(Exception):
    """value が null（未計測）のトークンを使おうとした。"""


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


class Style:
    def __init__(self, tokens_path=TOKENS_PATH, provisional_path=PROVISIONAL_PATH):
        self.tokens = json.loads(pathlib.Path(tokens_path).read_text(encoding="utf-8"))
        self.provisional_values = json.loads(
            pathlib.Path(provisional_path).read_text(encoding="utf-8"))["values"]
        self.used_tokens = {}
        self.used_provisional = {}

    def token(self, path):
        """'color.ocean' のようなパスで実測トークンを返す。"""
        group, name = path.split(".", 1)
        try:
            entry = self.tokens[group][name]
        except KeyError:
            raise KeyError(f"トークン {path} は docs/style-tokens.json にありません") from None
        if entry["value"] is None:
            raise MissingTokenError(
                f"トークン {path} は未計測（value が null）のため使えません。"
                f"計測して docs/style-tokens.json に値を入れてください。メモ: {entry.get('method', '')}")
        self.used_tokens[path] = entry
        return entry["value"]

    def color(self, name):
        return hex_to_rgb(self.token(f"color.{name}"))

    def provisional(self, name):
        try:
            entry = self.provisional_values[name]
        except KeyError:
            raise KeyError(f"仮の値 {name} は config/render-provisional.json にありません") from None
        self.used_provisional[name] = entry
        return entry["value"]

    def report_markdown(self):
        lines = ["# 作風の数値レポート", "",
                 "この動画で使った数値の一覧です。", "",
                 "## 実測トークン（docs/style-tokens.json）", "",
                 "| トークン | 値 | 状態 |", "|---|---|---|"]
        for path, entry in sorted(self.used_tokens.items()):
            value = entry["value"]
            if isinstance(value, list) and len(value) > 4:
                value = f"{len(value)} 点のリスト"
            lines.append(f"| `{path}` | `{value}` | {entry['status']} |")
        approx = [p for p, e in self.used_tokens.items() if e["status"] != "measured"]
        if approx:
            lines += ["", "**誤差のある値（approx / lower_bound）:** " + "、".join(f"`{p}`" for p in sorted(approx)),
                      "低解像度の素材から測った値のため、数％の誤差があります。"]
        lines += ["", "## 仮の値（config/render-provisional.json）", "",
                  "参照動画から計測できず、仮で決めた値です。", "",
                  "| 名前 | 値 | 単位 | メモ |", "|---|---|---|---|"]
        for name, entry in sorted(self.used_provisional.items()):
            lines.append(f"| `{name}` | `{entry['value']}` | {entry['unit']} | {entry['note']} |")
        return "\n".join(lines) + "\n"
