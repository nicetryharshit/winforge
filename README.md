# WinForge

Build a customised Windows ISO from a JSON profile, with a GUI for editing it.

It does what NTLite does: remove Appx apps, capabilities, features and drivers,
apply offline registry tweaks, disable services, drop in files, add an
unattended answer file, run commands at specialize, SetupComplete and first
logon, then rebuild the ISO.

## Setup (on the Windows build machine)

1. Install Python 3.11+ and the Windows ADK (Deployment Tools only, for `oscdimg.exe`).
2. `pip install -r requirements.txt`
3. Run PowerShell or the GUI **as Administrator** for real builds.

## Use

```
python -m winforge gui                     # editor window
python -m winforge validate profiles\example.json
python -m winforge build profiles\example.json --source C:\iso\Win11.iso --out C:\WinForge\out\lite.iso --dry-run
python -m winforge build profiles\example.json --source C:\iso\Win11.iso --out C:\WinForge\out\lite.iso
```

Always do a `--dry-run` first to see the exact DISM and reg commands. Then test
the ISO in a VM (Hyper-V or VirtualBox) before using it on real hardware.

## Profile

See `profiles/example.json`. Main sections:

| Section | What it does |
|---|---|
| `edition` / `index` | Which image in install.wim to customise. `index` overrides `edition`. |
| `options` | `reset_base`, `compress` (re-export WIM), `oscdimg` path |
| `remove` | Appx display names, capability names, feature names |
| `drivers`, `updates` | Driver folders to inject, `.msu`/`.cab` packages to add |
| `registry` | Offline edits in `SOFTWARE`, `SYSTEM` or `DEFAULT` (Default user hive) |
| `services_disable` | Sets `Start = 4` on each named service |
| `tasks_remove` | Deletes scheduled task files |
| `files` | Copies files or folders into the image (`from` relative to the profile) |
| `scripts.specialize` | Runs as SYSTEM after install, before OOBE |
| `scripts.setupcomplete` | Written to `SetupComplete.cmd`, runs as SYSTEM before first logon |
| `scripts.firstlogon` | Runs in order at first logon as the new account |
| `account` | Local admin name and password, autologon, skip OOBE |

## Notes and limits

- Edition lookup reads DISM output, which must be in English. Set `index` if your system uses another language.
- Per-user settings written to the `DEFAULT` hive only apply to new accounts. Use `firstlogon` for the account you create.
- Passwords in the profile are stored in plain text. Keep profiles private.
- Some Windows components cannot be removed safely. Deleting system files by hand breaks servicing, so WinForge sticks to DISM operations.
- `ResetBase` means updates can no longer be uninstalled.
- Failed removals of capabilities, features or services are logged and skipped; check the log.
- If a previous build left the image mounted, the pipeline runs `dism /Cleanup-Wim` first.

## Tests

```
python -m unittest discover -s tests
```

These run on any OS. They check profile validation, generated XML and the dry-run plan.
