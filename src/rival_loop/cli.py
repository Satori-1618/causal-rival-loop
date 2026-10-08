"""Small command surface; live runs are fail-closed by default."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded causal-rival generation pilot")
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Create unmeasured public/private case manifests")
    prep.add_argument("--out", required=True)
    prep.add_argument("--config")
    qa = commands.add_parser("qualify", help="Engineering checks on development graphs and actual sparse budget")
    qa.add_argument("--prepared", required=True)
    qa.add_argument("--out", required=True)
    smoke = commands.add_parser("smoke", help="Fake-provider integration check; no empirical result")
    smoke.add_argument("--out", required=True)
    smoke.add_argument("--cases", type=int, default=4)
    freeze = commands.add_parser("freeze", help="Local freeze; independent public review/release still required")
    freeze.add_argument("--prepared", required=True)
    freeze.add_argument("--qualification", required=True)
    freeze.add_argument("--split", choices=("development", "evaluation"), required=True)
    freeze.add_argument("--development-run")
    freeze.add_argument("--out", required=True)
    run = commands.add_parser("run", help="Live generator; refused without bound freeze/review/release")
    run.add_argument("--prepared", required=True)
    run.add_argument("--freeze")
    run.add_argument("--review")
    run.add_argument("--release")
    run.add_argument("--split", choices=("development", "evaluation"), required=True)
    run.add_argument("--execute", action="store_true")
    run.add_argument("--out", required=True)
    for name in ("verify", "analyze"):
        command = commands.add_parser(name)
        command.add_argument("--run", required=True)
        if name == "analyze":
            command.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        from . import governance
        if args.command == "prepare":
            result = governance.prepare(args.out, args.config)
        elif args.command == "qualify":
            result = governance.qualification(args.prepared, args.out)
        elif args.command == "freeze":
            result = governance.freeze(args.prepared, args.qualification, args.split,
                                       args.out, args.development_run)
        else:
            from . import runner
            if args.command == "smoke":
                result = runner.smoke(args.out, args.cases)
            elif args.command == "run":
                result = runner.execute_live(args.prepared, args.freeze, args.review,
                                             args.release, args.split, args.out, args.execute)
            else:
                result = runner.verify_run(args.run)
                if args.command == "analyze":
                    from .artifacts import read_json, write_json
                    manifest = read_json(Path(args.run) / "run.json")
                    if manifest["engineering_only"]:
                        result = read_json(Path(args.run) / "summary.json")
                    else:
                        from .inference import analyze
                        result = analyze(read_json(Path(args.run) / "records.json"), split=manifest["split"])
                    write_json(args.out, result)
        # Keep complete matrices in artifacts rather than printing them.
        concise = {key: value for key, value in result.items()
                   if key not in ("source_bindings", "files", "development_checks", "config", "known_bank_preflight")}
        print(json.dumps(concise, indent=2, allow_nan=False))
        if result.get("status") in ("incomplete", "not_qualified"):
            raise SystemExit(1)
    except (ValueError, FileNotFoundError, KeyError) as error:
        parser.exit(2, f"Refused: {error}\n")


if __name__ == "__main__":
    main()
