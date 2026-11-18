# Testing the stages branch

Run everything from the WinForge folder in PowerShell. Use `.\wf.cmd` for the shortcuts.

## 1. Automatic checks (about 1 minute)

    .\wf.cmd test

Expect 83 tests, all OK. Any failure: send the last 30 lines of output.

## 2. Look and feel (10 minutes)

    .\wf.cmd gui

Click through every page and check:

- The sidebar shows SETTINGS and RUN ON THE PC, with five stage pages under the second heading.
- The dropdowns have a chevron and open a styled list.
- The title bar is short and the three window buttons sit flush top-right.
- Choosing an ISO fills the edition dropdown on its own. Reload list works.
- While editions are being read, the window is dimmed and clicks do nothing. Cancel works.

## 3. Stage pages (10 minutes)

Open **After setup, once**. Tick "Install the NVIDIA driver silently". Save, reopen the profile, and check the tick is still there.

Type a command in the box, for example `echo hello`, then click **Build** and check the preview shows it.

Open **Every sign-in**, click **Add my own script…**, and choose any `.ps1` file. Expect a line in the box like `powershell -NoProfile ... -File "%WINDIR%\Setup\Scripts\name.ps1"`, and a row on the Files and drivers page.

## 4. Dry-run build (no changes made to any PC)

Save a profile, then:

    .\wf.cmd build --dry-run

Read the plan. You should see:

- `write ...\WinForge-every-sign-in.cmd` if you added a sign-in command
- `write ...\WinForge-every-boot.cmd` if you added a boot command
- `write ...\SetupComplete.cmd`

Nothing is changed on disk in a dry run.

## 5. Real build (use a VM, not your main PC)

Only after the dry run looks right. Run a real build against a copy of the Windows ISO, and tell me the first ERROR line if it stops.

## Known unverified points

- Scheduled tasks for every sign-in (`/ru "BUILTIN\Users"`) and every boot (`/ru SYSTEM`) have not been created on a real PC yet.
- Ready-made steps assume their files are copied in on the Files and drivers page.
- The scan (Debloat > Scan image) has not been run on a real image.
