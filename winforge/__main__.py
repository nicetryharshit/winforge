"""Command line interface. The GUI runs these same commands, so headless and GUI builds match.

Exit codes: 0 success, 1 a problem with the profile, source or build, 130 interrupted.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import presets
from .editions import read_editions
from .pipeline import BuildError, build, cleanup
from .profile import ProfileError, load_profile


def _log(msg: str) -> None:
    print(msg, flush=True)


def cmd_build(args) -> int:
    if args.preset:
        profile = presets.load_preset(args.preset)
        base = Path.cwd()
    elif args.profile:
        profile = load_profile(args.profile)
        base = args.profile.resolve().parent
    else:
        raise ValueError("give a profile file or --preset NAME")
    build(profile, base, args.source, args.work, args.out,
          oscdimg=args.oscdimg, dry_run=args.dry_run, log=_log)
    return 0


def cmd_validate(args) -> int:
    p = load_profile(args.profile)
    print(f"OK: '{p['name']}' for {p['edition'] or 'index ' + str(p['index'])}")
    print(f"    apps {len(p['remove']['appx'])}, features {len(p['remove']['features'])}, "
          f"capabilities {len(p['remove']['capabilities'])}, services {len(p['services_disable'])}, "
          f"registry edits {len(p['registry'])}, files {len(p['files'])}, drivers {len(p['drivers'])}, "
          f"updates {len(p['updates'])}")
    return 0


def cmd_editions(args) -> int:
    editions = read_editions(args.source)
    if args.json:
        print(json.dumps([asdict(e) for e in editions], indent=2))
    else:
        for e in editions:
            print(f"{e.index:>3}  {e.name}")
    return 0


def cmd_presets(args) -> int:
    if args.action == "list":
        for info in presets.list_presets():
            tag = "built-in" if info.builtin else "yours"
            print(f"{info.name:<20} [{tag}] {info.description}")
    elif args.action == "show":
        print(json.dumps(presets.load_preset(args.name), indent=2))
    elif args.action == "save":
        path = presets.save_preset(args.name, load_profile(Path(args.file)))
        print(f"Saved preset '{args.name}' to {path}")
    elif args.action == "delete":
        presets.delete_preset(args.name)
        print(f"Deleted preset '{args.name}'")
    return 0


def cmd_cleanup(args) -> int:
    cleanup(args.work, log=_log)
    return 0


def cmd_gui(args) -> int:
    from .gui import run
    return run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="winforge", description="Build custom Windows ISOs from a profile.")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build an ISO from a profile or preset")
    b.add_argument("profile", nargs="?", type=Path, help="profile JSON file (or use --preset)")
    b.add_argument("--preset", help="built-in or saved preset name, e.g. lean")
    b.add_argument("--source", required=True, help="Windows ISO file or extracted folder")
    b.add_argument("--out", required=True, type=Path, help="output ISO path")
    b.add_argument("--work", type=Path, default=Path(r"C:\WinForge\work"), help="scratch folder (needs free space)")
    b.add_argument("--oscdimg", help="path to oscdimg.exe")
    b.add_argument("--dry-run", action="store_true", help="print the plan without changing anything")
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="check a profile file and show what it changes")
    v.add_argument("profile", type=Path)
    v.set_defaults(func=cmd_validate)

    e = sub.add_parser("editions", help="list editions in an ISO, folder, WIM or ESD")
    e.add_argument("source", type=Path)
    e.add_argument("--json", action="store_true", help="print JSON instead of a table")
    e.set_defaults(func=cmd_editions)

    p = sub.add_parser("presets", help="list, show, save or delete presets")
    ps = p.add_subparsers(dest="action", required=True)
    ps.add_parser("list", help="list built-in and saved presets")
    show = ps.add_parser("show", help="print a preset as JSON")
    show.add_argument("name")
    save = ps.add_parser("save", help="save a profile file as a named preset")
    save.add_argument("name")
    save.add_argument("file", type=Path)
    delete = ps.add_parser("delete", help="delete a saved preset")
    delete.add_argument("name")
    p.set_defaults(func=cmd_presets)

    c = sub.add_parser("cleanup", help="unmount a build left behind by a cancelled or crashed run")
    c.add_argument("--work", type=Path, default=Path(r"C:\WinForge\work"))
    c.set_defaults(func=cmd_cleanup)

    g = sub.add_parser("gui", help="open the editor window")
    g.set_defaults(func=cmd_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ProfileError, BuildError, KeyError, ValueError, OSError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        print(f"ERROR: {message}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. If a build was in progress, run 'winforge cleanup' to unmount it.",
              file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
