# WinForge style guide

WinForge's editor is styled after Ableton Live: dense, dark, flat, one amber accent, small
uppercase section labels, and no native Windows chrome. This guide says how to keep it that way.
Colours and sizes come from `winforge/theme.py`. Change them there, not in the widgets.

## 1. Principles

1. **Dark and flat.** Charcoal panels, hairline dividers, no gradients, no shadows, no rounded corners beyond 2px.
2. **One accent.** Amber marks what is selected, focused, or the single primary action. Nothing else is amber.
3. **Dense but calm.** Small type, tight rows, generous margins around each page.
4. **Nothing native.** No Windows title bar, no Windows file dialogs, no default Fusion chrome. Every dialog and control comes from the app's stylesheet.
5. **Explain every control.** Each control has a tooltip, and each page has a one-line description under its title.

## 2. Layout

```
+--------------------------------------------------------------------------+
| WINFORGE  profile name  ● unsaved      Open  Save  Save as  Build   ─ ▢ ✕ |  top bar (drag handle)
+----------------+---------------------------------------------------------+
| 01 Start       | PAGE TITLE                                              |  page header strip
| 02 Source      | one-line description                                    |
| 03 Debloat     +---------------------------------------------------------+
| 04 Tweaks      |                                                         |
| 05 Scripts     |  page body: sections, forms, lists, tabs                |
| 06 Account     |                                                         |
| 07 Build       |                                                         |
+----------------+---------------------------------------------------------+
| status message                                       Profile is valid   |  status bar
+--------------------------------------------------------------------------+
```

- **Top bar (`QFrame#topbar`).** Brand on the left, profile name and unsaved marker next to it, actions on the right, then window controls. The bar also drags the window and double-click maximises it.
- **Browser (`QListWidget#nav`).** 176 px wide. Each page is numbered in the order it is normally used.
- **Page header (`QFrame#pageHeader`).** Title plus one description line, separated from the body by a hairline.
- **Body.** Forms scroll. Tabbed pages fill the window.
- **Info strip.** 64 px strip above the status bar. Hover text goes here.
- **Status bar.** Messages on the left. Profile validity on the right.

## 3. Colour

| Token | Hex | Use |
|---|---|---|
| `BG` | `#181818` | Window, top bar, page header, status bar |
| `PANEL` | `#1f1f1f` | Page background, selected browser item, tab pane |
| `PANEL_2` | `#282828` | Buttons, cards, hover fills, tooltips |
| `SUNKEN` | `#121212` | Inputs, lists, the log, the browser |
| `LINE` | `#2f2f2f` | Hairline dividers and input borders |
| `LINE_STRONG` | `#414141` | Button borders, checkbox borders, scrollbar handles |
| `TEXT` | `#d4d4d4` | Body text |
| `MUTED` | `#7f7f7f` | Captions, help text, unselected tabs and browser items |
| `DIM` | `#555555` | Disabled text, placeholder text |
| `ACCENT` | `#ffb13b` | Selection, focus, primary action, checked boxes |
| `ACCENT_HOVER` | `#ffc566` | Primary action on hover |
| `ACCENT_TEXT` | `#1c1c1c` | Text on amber |
| `OK` | `#9ccc65` | Success messages |
| `WARN` | `#ff7a6b` | Errors, the problem banner, destructive hover |

Rules:
- Amber is for state, not decoration. Use one primary (amber) button per view.
- Red (`WARN`) is for problems only, never for emphasis.
- The close button hover uses `#c42b1c`, the standard Windows close red. It is the only fixed colour outside the palette.
- Do not hard-code colours in widgets. Use an object name and add the rule to the stylesheet.

**Open item:** these values are WinForge's own palette. To match Ableton Live exactly, replace the
values above with the ones from a Live theme file (`.ask`) or measured from a screenshot of a
default-theme Live window, then update this table.

## 4. Typography

| Role | Font | Size | Weight | Object name |
|---|---|---|---|---|
| Body and controls | Segoe UI, Helvetica Neue, Arial | 8.5 pt | normal | (default) |
| Brand | same | 10 pt | 700 | `brand` |
| Page title | same | 11 pt | 600 | `pageTitle` |
| Page description | same | 9 pt | normal, muted | `pageHint` |
| Section label | same | 7.5 pt | 700, uppercase, muted | `section` |
| Help text | same | 9 pt | normal, muted | `help` |
| Card title | same | 10 pt | 600 | `cardTitle` |
| Log and code | Cascadia Mono, Consolas | 8.5 pt | normal | `log` |

Section labels are always uppercase and separated from the content above by a hairline.

## 5. Spacing

- Page padding: 20 px sides, 10 px top, 20 px bottom.
- Gap between controls: 8 px vertically, 6 px between buttons in a row.
- Form rows: 10 px vertical, 18 px between label and field.
- Section labels: 14 px above, 6 px below, then the hairline.
- Inputs: 5 px vertical and 7 px horizontal padding.
- Radius: 2 px at most.

## 6. Controls

| Control | Object name | When to use |
|---|---|---|
| Primary button | `primary` | The one action the page is for: Load a preset, Build ISO. Only one per view. |
| Default button | (none) | Everything else that does something. |
| Ghost button | `ghost` | Low-emphasis actions inside a row. |
| Chip | `chip` | Small toggles and bulk actions in a list header: Recommended, All, None. |
| Danger button | `danger` | Deletes. Shows red on hover. Always asks for confirmation. |
| Window control | `winctl`, `winclose` | Top bar only. |
| Check box | (none) | On/off options. Checked = amber. |
| Tabs | (none) | Switch between groups on a page. Selected tab is amber with an underline. |
| Browser item | `nav` | Pages. Selected item has an amber left edge. |
| Card | `card` | Presets. Amber border on hover. |
| Tag | `tag`, `tagAccent` | Labels such as BUILT-IN (amber) and YOURS (muted). |
| Banner | `banner` | Blocking problems only. Red border. |
| Panel header | `panelHead` | One strip at the top of a tab saying what it is for. Not for warnings. |
| Checklist | (widget `CheckList`) | Pick-many lists. ★ column, amber box when ticked, bright name, dim description. Clicking the row toggles it. |
| Info strip | `info` | Fixed strip above the status bar. Shows the description of whatever the mouse is over, like Live's Info View. Every control's tooltip text appears here. |

Dialogs use Qt's own file dialogs, never the native Windows ones. Message boxes use the same buttons as the rest of the app.

## 7. Tooltips and help text

Every control has a tooltip. Write them in this order:

1. **What it does**, in one sentence.
2. **The cost or effect** if it matters: "Stops Windows Update completely, including security fixes."
3. **The example** if the value is not obvious: "for example Windows\\Setup\\Scripts."

Page descriptions say what the page is for and what does not happen until the user builds.

Help text under a section explains the section, not the control. Long help goes under the page title or on a tab's first line.

## 8. Copy

- Plain English. Name the Windows term once, then use the plain word after that.
- Use the user's words: "Scripts", "Account", "Build", not internal names.
- Destructive or irreversible things say so: "Nothing on your disk is deleted", "cannot uninstall updates later".
- Do not use exclamation marks or the word "simply".
- Sentence case for labels and tooltips. Title case only for page names and the top bar.
- Use the same name for the same thing everywhere. Profile, preset, build, edition.

## 9. States

| State | Look |
|---|---|
| Disabled | `DIM` text on `PANEL`, border `LINE` |
| Focused input | Amber border |
| Hover (button) | Amber border and text |
| Unsaved changes | Amber "● unsaved changes" in the top bar |
| Problem | Red banner on the Build page, and the status bar shows the first problem |
| Success | Status bar message in `OK` |
| Building | Amber stage label, log streams below |

## 10. Things we do not do

- No Windows title bar or native dialogs.
- No gradients, shadows, icons from other design systems, or emoji. The only symbols are the window controls and the unsaved dot.
- No extra accent colours.
- No modal dialogs for things that can be shown inline.

## 11. Checklist for a new screen

- [ ] Page has a title and one description line.
- [ ] Every control has a tooltip that follows section 7.
- [ ] At most one primary button.
- [ ] Sections use the uppercase section label and hairline.
- [ ] Colours come from `theme.py`, not from the widget.
- [ ] Destructive actions say what they cannot undo.
- [ ] Works at 1200 × 820 and at the minimum size without clipping.
- [ ] Looks right in the offscreen preview (`QT_QPA_PLATFORM=offscreen`) before it goes to the PC.
