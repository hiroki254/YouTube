"""Gist から台本を取り出し、1文ずつに分ける。

台本の書き方:
    # 動画のタイトル
    導入の文。導入の文。
    ## 章の名前
    本文の文。本文の文。

- 「# 」で始まる行は動画のタイトル（最初の1つだけ使う）
- 「## 」で始まる行は章。章タイトルは読み上げ、章カードを出す
- それ以外は本文。「。」「！」「？」と改行で1文に区切る
"""

import dataclasses
import json
import os
import re
import urllib.request

GIST_ID = re.compile(r"(?:gist\.github(?:usercontent)?\.com/(?:[^/]+/)?)?([0-9a-f]{20,40})", re.I)
SENTENCE_END = re.compile(r"(?<=[。！？!?])")
TEXT_SUFFIXES = (".md", ".txt", ".markdown")


@dataclasses.dataclass
class Sentence:
    index: int
    text: str
    chapter_number: int  # 導入は 0
    chapter_title: str
    is_chapter_card: bool = False


@dataclasses.dataclass
class Script:
    title: str
    sentences: list


def gist_id_from_url(url):
    match = GIST_ID.search(url.strip())
    if not match:
        raise ValueError(f"Gist の URL から ID を読み取れません: {url}")
    return match.group(1)


def fetch_gist_text(url, token=None):
    gist_id = gist_id_from_url(url)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "youtube-video-pipeline"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com/gists/{gist_id}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        gist = json.load(response)
    files = sorted(gist["files"].values(), key=lambda f: f["filename"])
    texts = [f for f in files if f["filename"].lower().endswith(TEXT_SUFFIXES)] or files
    if not texts:
        raise ValueError(f"Gist {gist_id} にファイルがありません")
    chosen = texts[0]
    if chosen.get("truncated"):
        raw = urllib.request.Request(chosen["raw_url"], headers={"User-Agent": "youtube-video-pipeline"})
        with urllib.request.urlopen(raw, timeout=30) as response:
            return response.read().decode("utf-8")
    return chosen["content"]


def split_sentences(paragraph):
    parts = []
    for line in paragraph.splitlines():
        line = re.sub(r"^\s*[-*・]\s*", "", line).strip()
        parts += [p.strip() for p in SENTENCE_END.split(line) if p.strip()]
    return parts


def parse_script(text):
    title = ""
    sentences = []
    chapter_number = 0
    chapter_title = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            chapter_number += 1
            chapter_title = line[3:].strip()
            sentences.append(Sentence(len(sentences), chapter_title, chapter_number, chapter_title,
                                      is_chapter_card=True))
            continue
        if line.startswith("# "):
            title = title or line[2:].strip()
            continue
        for part in split_sentences(line):
            sentences.append(Sentence(len(sentences), part, chapter_number, chapter_title))
    if not any(not s.is_chapter_card for s in sentences):
        raise ValueError("台本に本文の文がありません")
    return Script(title=title or "untitled", sentences=sentences)


def load_script(gist_url=None, path=None):
    if path:
        with open(path, encoding="utf-8") as f:
            return parse_script(f.read())
    return parse_script(fetch_gist_text(gist_url, os.environ.get("GITHUB_TOKEN")))
