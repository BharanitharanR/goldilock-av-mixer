import json

import pytest

from video_audio_mixer.context import discover_context


def _job_folder(tmp_path, names):
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "analysis.json").write_text(json.dumps({"video": {}}))
    (tmp_path / "song-spec.json").write_text(json.dumps({"song_spec_version": "1.0"}))
    return tmp_path


def test_rendered_wav_wins_over_its_lossy_copy(tmp_path):
    folder = _job_folder(tmp_path, ["input.mp4", "ace-step-song.wav", "music.mp3"])
    assert discover_context(folder).music_path.endswith("ace-step-song.wav")


def test_ambiguous_video_names_the_flag(tmp_path):
    folder = _job_folder(tmp_path, ["input.mp4", "original.mp4", "song.wav"])
    with pytest.raises(ValueError, match="--video"):
        discover_context(folder)


def test_explicit_names_resolve_inside_the_folder(tmp_path):
    folder = _job_folder(tmp_path, ["input.mp4", "original.mp4", "scored.mp4", "song.wav", "a.wav"])
    ctx = discover_context(folder, video="input.mp4", music="song.wav")
    assert ctx.video_path.endswith("input.mp4")
    assert ctx.music_path.endswith("song.wav")
