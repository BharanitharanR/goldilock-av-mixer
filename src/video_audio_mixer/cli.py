from __future__ import annotations

import argparse

from .context import discover_context, load_context
from .service import create_plan, load_plan, mix, write_plan, write_speech


def add_context_args(parser):
    parser.add_argument("context_dir", nargs="?")
    parser.add_argument("--video")
    parser.add_argument("--music")
    parser.add_argument("--analysis")
    parser.add_argument("--song-spec")
    parser.add_argument("--voiceover", help="voiceover.wav (48 kHz mono, as long as the video)")
    parser.add_argument("--voice-timeline", help="voiceover-timeline.json from the narrator")
    parser.add_argument("--original-under-voice", choices=["keep", "drop"], default="keep",
                        help="keep: original audio lowered under the voice (default); "
                             "drop: muted inside voice windows")


def get_context(args):
    if args.context_dir:
        # Flags given alongside the folder pick specific files inside it.
        return discover_context(args.context_dir, video=args.video, music=args.music,
                                analysis=args.analysis, song_spec=args.song_spec,
                                voiceover=args.voiceover, voice_timeline=args.voice_timeline)
    values = (args.video, args.music, args.analysis, args.song_spec)
    if not all(values):
        raise SystemExit("Supply CONTEXT_DIR or all of --video --music --analysis --song-spec")
    return load_context(*values, voiceover=args.voiceover, voice_timeline=args.voice_timeline)


def main():
    parser = argparse.ArgumentParser(prog="goldilock-av-mixer")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Create a MixPlan")
    add_context_args(plan)
    plan.add_argument("-o", "--output", default="mix-plan.json")
    plan.add_argument("--gemini-model", default="gemini-3.6-flash")
    plan.add_argument("--no-llm", action="store_true")

    execute = sub.add_parser("execute", help="Execute an existing MixPlan")
    add_context_args(execute)
    execute.add_argument("--plan", required=True)
    execute.add_argument("-o", "--output", default="final.mp4")

    combined = sub.add_parser("mix", help="Plan and execute")
    add_context_args(combined)
    combined.add_argument("-o", "--output", default="final.mp4")
    combined.add_argument("--gemini-model", default="gemini-3.6-flash")
    combined.add_argument("--no-llm", action="store_true")

    detect = sub.add_parser("detect-speech", help="Write the speech segments of a video's audio as JSON")
    detect.add_argument("video")
    detect.add_argument("-o", "--output", default="speech.json")

    args = parser.parse_args()
    if args.command == "detect-speech":
        write_speech(args.video, args.output)
        print(f"Wrote {args.output}")
        return
    context = get_context(args)

    if args.command == "plan":
        mix_plan = create_plan(context, use_llm=not args.no_llm, model=args.gemini_model,
                                 original_under_voice=args.original_under_voice)
        write_plan(mix_plan, args.output)
        print(f"Wrote {args.output}")
    elif args.command == "execute":
        result, evaluation = mix(context, load_plan(args.plan), args.output)
        print(f"Wrote {result}")
        print(f"Evaluation: {evaluation.status}")
    else:
        mix_plan = create_plan(context, use_llm=not args.no_llm, model=args.gemini_model,
                                 original_under_voice=args.original_under_voice)
        write_plan(mix_plan, "mix-plan.json")
        result, evaluation = mix(context, mix_plan, args.output)
        print("Wrote mix-plan.json")
        print(f"Wrote " + str(result))
        print(f"Evaluation: {evaluation.status}")


if __name__ == "__main__":
    main()
