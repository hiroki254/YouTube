"""シーンを1フレームずつ描き、ffmpeg で音声と合わせて MP4 にする。"""

import math
import subprocess

from PIL import Image

from .scenes import Canvas, Subtitles, Typesetter, find_font, make_scene


def render_video(plan, sentences, timeline, total_sec, style, land, audio_path, out_path, log=print):
    font_path, font_index = find_font()
    if "wqy" in font_path:
        log("注意: Noto Sans CJK が見つからないため代替フォントで描画します（試験用）")
    canvas = Canvas(style, Typesetter(font_path, font_index))
    subtitles = Subtitles(canvas)
    scenes = [make_scene(canvas, scene, land) for scene in plan]
    W, H, fps = canvas.W, canvas.H, canvas.fps
    command = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
               "-i", str(audio_path),
               "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out_path)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    frames = math.ceil(total_sec * fps)
    current = 0
    try:
        for f in range(frames):
            t = f / fps
            while current < len(scenes) - 1 and t >= timeline[current][2]:
                current += 1
            start, speech_end, _ = timeline[current]
            local_t = t - start
            frame = canvas.background.copy()
            frame.alpha_composite(scenes[current].layer(local_t, timeline[current][2] - start))
            sentence = sentences[current]
            if not sentence.is_chapter_card and 0 <= local_t:
                frame.alpha_composite(subtitles.layer(sentence.text, local_t, speech_end - start))
            process.stdin.write(frame.convert("RGB").tobytes())
            if f % (fps * 30) == 0:
                log(f"描画 {t:.0f}/{total_sec:.0f} 秒")
    finally:
        process.stdin.close()
        code = process.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg が失敗しました（終了コード {code}）")
    return canvas
