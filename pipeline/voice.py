"""VOICEVOX でナレーションを作り、1本の音声とタイムラインにまとめる。"""

import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import wave


class VoicevoxError(Exception):
    pass


class Voicevox:
    def __init__(self, base_url, speaker_id):
        self.base_url = base_url.rstrip("/")
        self.speaker_id = int(speaker_id)

    def _request(self, method, path, params=None, body=None):
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        if method == "POST":
            data = json.dumps(body).encode("utf-8") if body is not None else b""
        request = urllib.request.Request(url, data=data, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()

    def wait_ready(self, timeout_sec=180):
        deadline = time.monotonic() + timeout_sec
        while True:
            try:
                return self._request("GET", "/version").decode("utf-8")
            except (urllib.error.URLError, ConnectionError):
                if time.monotonic() > deadline:
                    raise VoicevoxError(f"VOICEVOX エンジン {self.base_url} に接続できません")
                time.sleep(2)

    def speaker_credit(self):
        """クレジット表記用の「キャラクター名（スタイル名）」。話者 ID が無ければ候補を出して止める。"""
        speakers = json.loads(self._request("GET", "/speakers"))
        choices = []
        for speaker in speakers:
            for style in speaker["styles"]:
                if style["id"] == self.speaker_id:
                    return speaker["name"], style["name"]
                choices.append(f"{style['id']}: {speaker['name']}（{style['name']}）")
        raise VoicevoxError(f"話者 ID {self.speaker_id} がありません。使える ID:\n" + "\n".join(choices))

    def synthesize(self, text):
        query = json.loads(self._request("POST", "/audio_query", {"text": text, "speaker": self.speaker_id}))
        return self._request("POST", "/synthesis", {"speaker": self.speaker_id}, body=query)


class SilentVoice:
    """テスト専用: VOICEVOX なしで、文字数に比例した無音を返す。本番では使わない。"""

    rate = 24000
    seconds_per_char = 0.12

    def wait_ready(self, timeout_sec=0):
        return "silent"

    def speaker_credit(self):
        return "（テスト用の無音）", ""

    def synthesize(self, text):
        frames = int(self.rate * self.seconds_per_char * max(len(text), 1))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(b"\x00\x00" * frames)
        return buffer.getvalue()


def build_narration(sentences, engine, style, out_path, log=print):
    """各文を合成して1本の WAV にまとめ、文ごとの (話し始め, 話し終わり, 次の文の開始) 秒と全体の長さを返す。"""
    gap = style.provisional("sentence_gap_sec")
    lead_in = style.provisional("lead_in_sec")
    tail = style.provisional("tail_sec")
    chapter_extra = style.provisional("chapter_extra_sec")
    params = None
    chunks = []
    timeline = []
    cursor = 0.0

    def silence(seconds):
        return b"\x00" * (int(params.framerate * seconds) * params.sampwidth * params.nchannels)

    for i, sentence in enumerate(sentences):
        spoken = f"{sentence.chapter_number}章、{sentence.text}" if sentence.is_chapter_card else sentence.text
        log(f"ナレーション {i + 1}/{len(sentences)}: {spoken}")
        with wave.open(io.BytesIO(engine.synthesize(spoken)), "rb") as w:
            if params is None:
                params = w.getparams()
                chunks.append(silence(lead_in))
                cursor = lead_in
            elif (w.getframerate(), w.getsampwidth(), w.getnchannels()) != (
                    params.framerate, params.sampwidth, params.nchannels):
                raise VoicevoxError("音声の形式が文によって違います")
            frames = w.readframes(w.getnframes())
            duration = w.getnframes() / w.getframerate()
        chunks.append(frames)
        start = cursor
        cursor += duration
        pause = gap + (chapter_extra if sentence.is_chapter_card else 0.0)
        if i == len(sentences) - 1:
            pause = tail
        chunks.append(silence(pause))
        speech_end = cursor
        cursor += pause
        timeline.append((start, speech_end, cursor))
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for chunk in chunks:
            out.writeframes(chunk)
    return timeline, cursor
