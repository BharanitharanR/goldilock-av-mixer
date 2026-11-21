# Goldilock AV Mixer

Standalone skill for LLM-planned, deterministic audio/video mixing.

Initial scaffold will be added here.

## Voiceover layer

`mix` accepts an optional voiceover (the narrator skill's output):

```bash
python -m video_audio_mixer.cli mix --no-llm . --video X --music song.wav \
  --voiceover voiceover.wav --voice-timeline voiceover-timeline.json \
  --original-under-voice keep -o final.mp4
```

- `voiceover.wav` and `voiceover-timeline.json` in the context folder are picked
  up automatically; explicit flags win. The voiceover is never treated as the
  music file. Without a timeline, speech windows are detected in the voiceover.
- Windows come from the timeline lines, padded 0.15 s and merged when the gap is
  under 0.4 s. Inside them the music drops a further 11 dB (same ramp as speech
  ducking) and the original audio is lowered 12 dB (`keep`, default) or muted
  (`drop`); outside them the original is untouched.
- Voice gain is set from the voiceover's mean level over its non-silent parts,
  aiming at about -17 dB mean before the final -16 LUFS loudnorm, with peaks
  kept under -1 dBFS.
- Works with a video that has no audio track, and with music disabled
  (`music_enabled: false` in the plan; no music file is passed to ffmpeg then).
- Original-speech ducking is trimmed to the stretches outside voice windows, so
  nothing is ducked twice.
- The MixPlan gains `voice_enabled`, `voice_gain_db`, `voice_windows`,
  `original_under_voice`, `original_under_voice_db`. Without a voiceover the
  plan and filtergraph are unchanged.

The Gemini planner (`gemini.py`, without `--no-llm`) is voice-unaware. When a
voiceover is present, its plan is passed through the same rule-based voice layer
afterwards, and any voice fields the model returned are cleared. The rule-based
path is the one designed for voice.

`detect-speech VIDEO -o speech.json` writes `[{start_seconds, end_seconds}]` for
the video's own audio (`[]` when it has none), for the narrator to avoid talking
over speech.
