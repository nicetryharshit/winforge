# WinForge

Build a customised Windows ISO. Pick a preset, tweak it in the editor or on the command line, and build.
WinForge does what NTLite does: it removes apps, features and services, applies registry tweaks, copies files,
adds an unattended answer file, runs your commands at setup and first logon, and rebuilds the ISO.

The GUI and the command line use the same code, so a build from either one behaves the same way.

## Setup (Windows build machine)

1. Install Python 3.11 or newer from python.org. Tick **Add python.exe to PATH**.
2. Install the Windows ADK, choosing **Deployment Tools** only. WinForge uses `oscdimg.exe` from it.
3. In PowerShell, from the project folder:

   ```powershell
   cd C:\Projects\Misc\winforge
   py -m pip install -r requirements.txt
   ```

Real builds need an **Administrator** PowerShell (right-click it and choose Run as administrator).
Previews and validation don't.

## The GUI

```powershell
py -m winforge gui
```

The pages go from left to right:

- **Start:** pick a preset (Lean, Everything, Blank, or one you saved), or open a profile file.
- **Source:** pick your Windows ISO or extracted folder, click **Read editions**, then choose one.
- **Debloat:** tick apps, features and services to remove or switch off. ★ marks the recommended ones.
- **Tweaks:** tick registry tweaks. Custom entries go in the table below them.
- **Scripts & files:** commands for setup, first logon, files to copy, drivers, and updates.
- **Account:** the local account, autologon, and whether to skip the setup screens.
- **Build:** a summary, a **Preview (dry run)** button, and **Build ISO**. The log and stage show what is happening.

Ctrl+S saves. The Build page refuses to run while the profile has an error and says which one.

## Command line

```powershell
py -m winforge presets list
py -m winforge editions "C:\Users\aDMIN\Downloads\Windows11.iso"
py -m winforge validate profiles\example.json
py -m winforge build --preset lean --source "C:\Users\aDMIN\Downloads\Windows11.iso" --out C:\WinForge\out\lean.iso --dry-run
py -m winforge build --preset lean --source "C:\Users\aDMIN\Downloads\Windows11.iso" --out C:\WinForge\out\lean.iso
py -m winforge build profiles\example.json --source "C:\...\Windows11.iso" --out C:\WinForge\out\test.iso
py -m winforge cleanup
```

- `editions` reads the image list straight from the ISO. Nothing is copied. Add `--json` for scripts.
- `build --dry-run` prints every command it would run, runs no changes, and makes no ISO.
- `cleanup` unmounts an image left behind by a build that was cancelled or crashed.
- Exit codes: `0` success, `1` a problem with the profile, source or build, `130` interrupted.

Every real build writes a log to `<work>\logs\build-<timestamp>.log`, and saves a copy of the profile
next to the ISO (for example `test.iso` gets `test.profile.json`), so you can see what produced it.

## Presets

- **Lean (recommended):** removes the bundled apps, telemetry and sponsored content, and disables the telemetry services. Keeps the Store, Defender and Windows Update.
- **Everything (aggressive):** everything in the catalog. Expect some breakage, so test it in a VM first.
- **Blank:** no changes.

Your own presets are saved in `%APPDATA%\WinForge\presets` (usually `C:\Users\<you>\AppData\Roaming\WinForge\presets`).
You can save from the GUI (Start page, **Save current as preset…**) or from the command line:
`py -m winforge presets save "My setup" profiles\mine.json`.

## Profile format

A profile is a JSON file. See `profiles/example.json`.

| Section | What it does |
|---|---|
| `edition` / `index` | Which image to customise. `index` overrides `edition`. |
| `options` | `reset_base`, `compress` (re-export the image), `oscdimg` path |
| `remove` | `appx` (display names), `features`, `capabilities` |
| `drivers`, `updates` | Driver folders to inject, `.msu` or `.cab` packages to add |
| `registry` | Offline edits in the `SOFTWARE`, `SYSTEM` or `DEFAULT` (Default user) hive. Key is relative to the hive. An empty `name` sets the default value. |
| `services_disable` | Sets `Start = 4` on each service |
| `tasks_remove` | Deletes scheduled task files |
| `files` | Copies files or folders into the image. `from` is relative to the profile, `to` is inside the image. |
| `scripts.specialize` | Runs as SYSTEM after install, before the setup screens |
| `scripts.setupcomplete` | Written to `SetupComplete.cmd`. Runs as SYSTEM before first logon |
| `scripts.firstlogon` | Runs in order at first logon as the new account |
| `account` | Local account name and password, autologon, skip setup screens |

## Safety

- **Preflight checks run first.** They verify admin rights, `oscdimg.exe`, that every file and driver exists, and that the work drive has enough free space. Nothing is changed if a check fails.
- **Your original ISO is never modified.** The source is copied into the work folder first.
- **Failures discard the changes.** If the build fails partway, the mounted image is discarded, not committed.
- **Interrupted builds can be cleaned up.** Use **Clean up leftovers** in the GUI, or `py -m winforge cleanup`.
- **Test every ISO in a VM** before installing it on real hardware.

## Notes and limits

- Edition names come from DISM's English output. If your Windows display language differs, set `index` instead.
- Items missing from your image are skipped without failing the build. Check the log for the warnings.
- Per-user registry tweaks in the `DEFAULT` hive apply to new accounts only. Use `firstlogon` for the account you create.
- Passwords in profiles and presets are stored in plain text.
- Some Windows components can't be removed safely. WinForge uses DISM for removals and never deletes system files by hand.
- `ResetBase` makes the image smaller, but updates can no longer be uninstalled.

## Tests

```powershell
py -m unittest discover -s tests
```

The tests run on any OS. They check the profile rules, the generated unattend XML, edition parsing against
real DISM output, presets, the dry-run plan, and the CLI exit codes. They don't exercise DISM itself, so a
real build still needs to be tested on Windows.
