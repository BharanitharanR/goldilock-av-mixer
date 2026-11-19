from __future__ import annotations

import json

from .models import MixingContext

SYSTEM_PROMPT = """
You are a film soundtrack mixing director.

Make a mix plan for generated music and the natural audio embedded in a source video.
The complete analysis.json and SongSpec are authoritative context.

Do not re-analyze the video, invent events, speakers, emotions, locations, or timestamps,
change the SongSpec, or produce FFmpeg commands. Return only valid MixPlan JSON.

Preserve speech and meaningful natural sound. Use semantic moments, audio observations,
and SongSpec arrangement timing to make music support the scene. Use fades and
time-bounded ducking where supported by evidence. Avoid pumping, clipping, and
unnecessary changes in gain. If the evidence is insufficient, choose a conservative mix.
""".strip()


def build_prompt(context: MixingContext) -> str:
    payload = {
        "video_path": context.video_path,
        "music_path": context.music_path,
        "video_analysis": context.analysis,
        "song_spec": context.song_spec,
    }
    return "Create a MixPlan 1.0 for this context:\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
