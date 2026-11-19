---
name: goldilock-av-mixer
description: Plan and execute context-aware mixing of original video audio and generated music. Consumes source media, complete video-analysis output, and SongSpec 1.0. Uses an LLM for mix decisions and FFmpeg for deterministic execution. Exposes post-render evaluation without an automatic revision loop.
---

# Goldilock AV Mixer

## Role
Act as a soundtrack mixing director. Given a video, the audio embedded in that video, a generated audio track, the complete video-analysis artifact, and the SongSpec that describes the generated music, produce a structured MixPlan and execute it.

## Context inputs
- Source video file.
- Generated music/audio file.
- Complete `analysis.json` from video-analysis.
- `song-spec.json` (SongSpec 1.0) from text-to-compose.

The planner receives the complete JSON artifacts, not just a summary. Treat analysis.json as evidence about the video and SongSpec as evidence about the musical intent.

## Analysis evidence
Use the semantic timeline, events, moments, edit points, mood, activities, interactions, people/objects, audio observations, technical duration, deterministic audio evidence, temporal measurements, quality evidence, and scene boundaries where present.

Do not infer speech content from silence or invent timestamps, events, speakers, or emotions. Use confidence and missing-data fields conservatively.

## SongSpec evidence
Use the creative world, style, tempo, key/raga, instruments, ending, and arrangement sections/timing. Do not rewrite the SongSpec.

## Planning decisions
Determine:
- whether original video audio should be retained;
- relative original-audio and music gain;
- music entry/exit timing;
- fades and pauses;
- time-bounded music ducking to protect speech or meaningful natural sound;
- whether sections should use different music levels;
- how to end the soundtrack cleanly.

Prefer intelligibility of speech and meaningful environmental sounds. Do not apply arbitrary loudness targets without measurement. Avoid aggressive pumping and clipping.

## Output contract
Emit only MixPlan 1.0 JSON. Do not output FFmpeg commands or alter source files.

## Execution
Python validates the plan and builds FFmpeg filters. FFmpeg performs all media operations deterministically.

## Evaluation
After rendering, call the EvaluationHook. This version exposes the hook but does not automatically re-plan or re-render. Preserve the rendered artifact and report the evaluation result.
