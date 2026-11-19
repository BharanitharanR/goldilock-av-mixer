from __future__ import annotations

import argparse

from .context import discover_context, load_context
from .service import create_plan, load_plan, mix, write_plan


def add_context_args(parser):
    parser.add_argument("context_dir", nargs="?")
    parser.add_argument("--video")
    parser.add_argument("--music")
    parser.add_argument("--analysis")
    parser.add_argument("--song-spec")


def get_context(args):
    if args.context_dir:
        return discover_context(args.context_dir)
    values = (args.video, args.music, args.analysis, args.song_spec)
    if not all(values):
        raise SystemExit("Supply CONTEXT_DIR or all of --video --music --analysis --song-spec")
    return load_context(*values)


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

    args = parser.parse_args()
    context = get_context(args)

    if args.command == "plan":
        mix_plan = create_plan(context, use_llm=not args.no_llm, model=args.gemini_model)
        write_plan(mix_plan, args.output)
        print(f"Wrote {args.output}")
    elif args.command == "execute":
        result, evaluation = mix(context, load_plan(args.plan), args.output)
        print(f"Wrote {result}")
        print(f"Evaluation: {evaluation.status}")
    else:
        mix_plan = create_plan(context, use_llm=not args.no_llm, model=args.gemini_model)
        write_plan(mix_plan, "mix-plan.json")
        result, evaluation = mix(context, mix_plan, args.output)
        print("Wrote mix-plan.json")
        print(f"Wrote " + str(result))
        print(f"Evaluation: {evaluation.status}")


if __name__ == "__main__":
    main()
