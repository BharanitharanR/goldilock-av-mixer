from __future__ import annotations

import json
from pathlib import Path

from .models import MixingContext


VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def discover_context(directory: str | Path) -> MixingContext:
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(directory)

    videos = [p for p in directory.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS]
    audios = [p for p in directory.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS]
    if len(videos) != 1:
        raise ValueError(f"Expected exactly one video in {directory}; found {len(videos)}")
    if len(audios) != 1:
        raise ValueError(f"Expected exactly one music/audio file in {directory}; found {len(audios)}")

    analysis_path = directory / "analysis.json"
    song_spec_path = directory / "song-spec.json"
    if not analysis_path.is_file():
        raise FileNotFoundError(analysis_path)
    if not song_spec_path.is_file():
        raise FileNotFoundError(song_spec_path)

    return MixingContext(
        video_path=str(videos[0]),
        music_path=str(audios[0]),
        analysis=_read_json(analysis_path),
        song_spec=_read_json(song_spec_path),
    )


def load_context(video, music, analysis, song_spec) -> MixingContext:
    return MixingContext(
        video_path=str(video),
        music_path=str(music),
        analysis=_read_json(Path(analysis)),
        song_spec=_read_json(Path(song_spec)),
    )
