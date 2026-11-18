"""Command line entry point: python -m winforge {build,validate,gui}."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import BuildError, build
from .profile import ProfileError, load_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="winforge", description="Build custom Windows ISOs from a profile.")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build an ISO from a profile")
    b.add_argument("profile", type=Path)
    b.add_argument("--source", required=True, help="Windows ISO file or extracted folder")
    b.add_argument("--work", type=Path, default=Path(r"C:\WinForge\work"))
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--oscdimg", help="path to oscdimg.exe")
    b.add_argument("--dry-run", action="store_true", help="print commands without running them")

    v = sub.add_parser("validate", help="check a profile file")
    v.add_argument("profile", type=Path)

    sub.add_parser("gui", help="open the editor window")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            load_profile(args.profile)
            print("Profile OK")
            return 0
        if args.command == "gui":
            from .gui import run
            return run()
        build(args.profile, args.source, args.work, args.out,
              oscdimg=args.oscdimg, dry_run=args.dry_run,
              log=lambda msg: print(msg, flush=True))
        return 0
    except (ProfileError, BuildError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
