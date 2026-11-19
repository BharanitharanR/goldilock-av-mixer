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


LOSSLESS_AUDIO_EXTENSIONS = {".wav", ".flac"}


def _resolve(directory: Path, given) -> Path:
    """An explicit path wins; a bare name is looked up inside the directory."""
    path = Path(given)
    if not path.is_absolute() and not path.exists() and (directory / path).exists():
        path = directory / path
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _pick(directory: Path, candidates: list[Path], kind: str, flag: str) -> Path:
    names = ", ".join(sorted(p.name for p in candidates)) or "none"
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        f"Expected exactly one {kind} in {directory}; found {len(candidates)} ({names}). "
        f"Name the one to use with {flag}."
    )


def discover_context(directory: str | Path, *, video=None, music=None,
                     analysis=None, song_spec=None) -> MixingContext:
    """Collects the four inputs from one folder. Any of them can be named
    explicitly, which is needed when a working folder also holds derived
    copies (a browser-playable MP4 next to the original, an MP3 next to the
    rendered WAV)."""
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(directory)

    files = [p for p in directory.iterdir() if p.is_file()]
    if video:
        video_path = _resolve(directory, video)
    else:
        videos = [p for p in files if p.suffix.lower() in VIDEO_EXTENSIONS]
        video_path = _pick(directory, videos, "video", "--video")

    if music:
        music_path = _resolve(directory, music)
    else:
        audios = [p for p in files if p.suffix.lower() in AUDIO_EXTENSIONS]
        lossless = [p for p in audios if p.suffix.lower() in LOSSLESS_AUDIO_EXTENSIONS]
        # A rendered WAV plus its MP3/OGG preview is the common case: the
        # lossless file is the source, the lossy ones are copies of it.
        music_path = _pick(directory, lossless if len(audios) > 1 and len(lossless) == 1 else audios,
                           "music/audio file", "--music")

    analysis_path = _resolve(directory, analysis) if analysis else directory / "analysis.json"
    song_spec_path = _resolve(directory, song_spec) if song_spec else directory / "song-spec.json"
    if not analysis_path.is_file():
        raise FileNotFoundError(analysis_path)
    if not song_spec_path.is_file():
        raise FileNotFoundError(song_spec_path)

    return MixingContext(
        video_path=str(video_path),
        music_path=str(music_path),
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
