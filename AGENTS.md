# Morelia

Single-file wxPython (Phoenix) text editor: `main.py` (251 lines, `Frame1`), no package/build/test/CI/lint. CWD is repo root.

## Run

```bash
./linux/run.sh
```

Or: `source linux/activate.sh && python main.py` (must run from repo root — `run.sh` handles `cd ..` after sourcing). On Windows: `win\setup.bat` then `win\run.bat`.

## Setup scripts — do not trust

`linux/setup.sh`, `win/setup.bat`, `win/run.bat` are broken by path assumptions (they `cd` into their dirs and look for `requirements.txt` etc at that level). `linux/run.sh` is the only correct launcher. Re-running `linux/setup.sh` is destructive as-is: it can create `linux/.venv`/`linux/.sysroot` and its heredocs overwrite `linux/activate.sh`/`linux/run.sh` with absolute paths into `linux/`, breaking the working launcher. Do not delete root `.venv`/`.sysroot`; back up `linux/activate.sh` before touching `setup.sh`. If fixing, either `cd ..` in each or resolve paths from repo root.

## Setup

```bash
./linux/setup.sh   # venv + GTK3 sysroot + regenerate activate.sh/run.sh
```

Two jobs, no-root:

1. Local `.venv/`: built `--without-pip` due to missing `python3-venv/ensurepip` and PEP 668; seeded with pip via `python3 -m pip --python .venv/bin/python install --upgrade pip`.
2. Local `.sysroot/`: GTK3/X11 runtime libs fetched via `apt-get download` and unpacked with `dpkg-deb -x`. Prebuilt wheel links Ubuntu 24.04 sonames (Debian trixie differs). `setup.sh` also pulls `libjpeg-turbo8` from Ubuntu by hardcoded URL because trixie only has `libjpeg.so.62` (different soname) — do not replace with distro package. Read full `GTK_PACKAGES` rationale in `setup.sh`.

`requirements.txt` pins exact wheel by direct URL on Linux (no manylinux CPython 3.13 wheel on PyPI). Windows/macOS use plain `wxPython==4.2.2`.

If `import wx` breaks after wheel change, re-run `setup.sh` to refresh sysroot; it ends with an `ldd` check on `_core*.so` that fails loudly.

### Verification

There is no test suite and no headless path through the GUI. The only non-GUI check is:

```bash
source linux/activate.sh && python -c "import wx; print(wx.version()); a = wx.App(False); print('ok')"
```

Anything about rendering, the completion popup, or dialogs has to be checked by hand in a real session. No `xvfb-run` is installed, so you cannot fake a display — you are stuck with whatever `$DISPLAY` the box has (currently `:0` for XWayland, with `wayland-0` also present, which is exactly the case the `GDK_BACKEND` note below exists for).

Screenshotting the window does **not** work either, so pixel checks are not an option: `wx.ScreenDC.Blit` into a `wx.MemoryDC` succeeds (`ok True`) but every pixel reads `#000000`, including a deliberately white `wx.Frame` probe. Use the Scintilla style getters plus `TextWidth`/`TextHeight` metrics instead, and leave anything that only shows on screen to the user.

`linux/activate.sh` is generated, gitignored, and machine-specific. It exports five things; four are load-bearing (`PATH` only finds the venv `python`):

| Var | Consequence if missing |
| --- | --- |
| `LD_LIBRARY_PATH` | `import wx` → "cannot open shared object file" |
| `XKB_CONFIG_ROOT` | **`wx.App(False)` segfaults** during GTK init, with only a misleading `xkbcommon: ERROR: failed to add default include path` on stderr |
| `GSETTINGS_SCHEMA_DIR` | any `wx.FileDialog` aborts the process: `No GSettings schemas are installed on the system`, exit 133. Only the first Ctrl+S on an unsaved file hits this; quick-save of a pathed file never opens a dialog |
| `GDK_BACKEND=x11` | under Wayland the autocompletion popup is never mapped (see below). Set only when `DISPLAY` is set and `GDK_BACKEND` is unset, so an explicit choice wins |

## Gotchas

**Environment / platform**

- **Under Wayland the autocompletion popup is invisible.** Scintilla draws the list in a separate `GTK_WINDOW_POPUP` window that a compositor never maps. It is still logically open — `AutoCompActive()` is `True` and `AutoCompGetCurrent()` returns an item, filtering keeps working, nothing is drawn. Not an app bug; no `AutoCompSet*` flag affects it. Diagnose with `gdk_display_get_name()` returning `wayland-0`.
- **Every launch wipes `error.log`.** `main.py:9` configures `log.basicConfig` but never logs anything; file is truncated on start. Tracked and gitignored → runs dirty tree; don't commit.

**wx / Scintilla API**

- **Use `StyledTextCtrl` APIs, not `wx.TextCtrl` ones.** Control is `wx.stc.StyledTextCtrl` (`SetText`/`AppendText`/`GetValue`/`SetLexer`).
- **Never call `WriteText` on the control.** On `StyledTextCtrl` it is a `SetText` alias (docstring lies): it *replaces* the document, so `SetInsertionPoint` + `WriteText('\n')` at position 3 of `'abc'` yields `'\n'`. Use `AddText` for inserts. This silently wiped the buffer on every Return until fixed.
- **Never add a `wx.Caret`.** Scintilla draws its own caret; `wx.Caret(ctrl,1)` raises TypeError (ctor wants bitmap). `error.log` retains old `Caret.Move()` failures.
- **`STC_STYLE_DEFAULT` does *not* feed the lexer styles.** Plain text is style 0 (`STC_P_DEFAULT`) and every `SCE_P_*` style keeps its own attributes, so theming needs an explicit `StyleSetBackground`/`StyleSetForeground` per style (`DARK_STYLES` in `main.py`). Verified with `TextWidth(style, text)`: setting the font on style 32 left `TextWidth(0, ...)` at 123px while `TextWidth(32, ...)` dropped to 38px. Consequence: colours set only on style 32 leave comments/strings black — invisible on the black background. `StyleGetForeground` cannot detect this: unset and explicitly-black both report `#000000`.
- **A leftover margin keeps the left edge white.** The control creates a 16px *text* margin (margin 1) that nothing writes to (`MarginGetText` is `''` on every line). `GetMarginBackground(1)` still reports black, so it is not the Scintilla margin colour doing it — GTK paints that strip from the widget background, which no style change reaches. `InitUI` zeroes every margin width instead.
- **Autocomplete is `AutoCompShow(length, items)`.** Phoenix has no `AutoCompStart` (`hasattr` False). `length` is prefix chars before caret (from `currentWord()`).
- **`GetUnicodeKey()` returns `int` (not `str`), `WXK_NONE=0`.** Special keys like `WXK_LEFT=314` give `chr(314)` = alnum `'ĺ'` — filter `keycode == wx.WXK_NONE or keycode >= wx.WXK_START` (300) before `chr()`.
- **`WordStartPosition` takes two args.** Use `ctrl1.WordStartPosition(pos, False)`.
- **Bind `EVT_CHAR` to the control, not the frame.** Frame binding doesn't fire (ctrl consumes). Use `self.ctrl1.Bind(...)`. `EVT_CHAR_HOOK` on frame works (used by `autoTab`).
- **`GetStyleAt()` returns 0 until colourisation runs.** Call `Colourise(0,-1)` after `SetLexer`. No lexer set → all styles 0 and `IGNORED_STYLES` silently fails. Verified: `STC_P_COMMENTLINE=1`, `STC_P_STRING=3`, `STC_P_CHARACTER=4`, `STC_P_WORD=5`, `STC_P_TRIPLE=6`, `STC_P_TRIPLEDOUBLE=7`, `STC_P_OPERATOR=10`, `STC_P_IDENTIFIER=11`, `STC_P_COMMENTBLOCK=12`, `STC_P_STRINGEOL=13`.
- **Always pass `encoding=` to `open()`** (utf-8). 
- **Zoom via style, not `SetFont`** (see Known issues).
- **Backspace unindents, and `DeleteBackNotLine()` does not save you.** With the caret in leading whitespace Scintilla drops the *whole* indentation (`BackSpaceUnIndents`, exposed as `Get/SetBackSpaceUnIndents`), so one Backspace undid several Tabs. Verified: `DeleteBack()` and `DeleteBackNotLine()` obey the same rule, so `autoTab` deletes the range itself via `SetTargetStart/SetTargetEnd` + `ReplaceTarget('')`. `CmdKeyExecute(WXK_BACK)` is *not* the GTK backspace path — it does nothing at all.
- **`SetCurrentPos` is `SCI_SETCURRENTPOS`: it moves the caret but keeps the selection anchor.** A stale selection survives it, so delete-the-selection logic (e.g. backspace) can act on the old one; use `SetSelection(pos, pos)` to collapse. `GetSelection()` returns `(min, max)`.
- **`wx.UIActionSimulator` has no `SendKeys`.** It exposes `KeyDown`/`KeyUp`/`Char`/`Text`, which do drive real GTK key events after `frame.Show()` + `ctrl.SetFocus()` + yields — the only way to test a key outside `autoTab`'s hook.
- **Return does not accept completion by default.** Intercept in `autoTab` and call `AutoCompComplete()` — **guard on `AutoCompActive()` and `AutoCompGetCurrent() >= 0`** (can be active with nothing highlighted). Without branch, intercepted Return inserts newline. `autoTab` swallows Return in hook; preserve skip paths.
- **That guard cannot detect a stale popup.** `SetText` (e.g. `openFile`) leaves an open popup *active with its old selection*, so the next Return completes that item over the new text — `print(...)` became `defprint(...)`. `AutoCompCancel()` before every `SetText`.
- **With the shipped 191-item `completions`, the popup only maps for some prefixes** (verified: 27/48 sampled; `abs`, `KeyError`, `IOError`, `Exception`, `False`, `None` never open it). `AutoCompActive()` is then False, so Return still indents — benign but user visible. Same prefix against a pre-filtered list always opens, and one filtered shape trips `wxVListBox::SetSelection(): invalid item index` inside Scintilla's GTK popup. Not an `AutoCompShow` call-signature problem.

**Editor behaviour**

- **`EVT_CHAR` fires *before* Scintilla inserts the character.** Opening the popup inline makes it lag one keystroke behind, because `currentWord()` can't see the char just typed. `autoComplete` therefore does `event.Skip()` then `wx.CallAfter(self.showAutocomplete)`. Don't "simplify" this back into a direct `AutoCompShow` call.
- **`showAutocomplete` gates on `MIN_COMPLETE_LENGTH = 2`**; `onAutocomplete` (the menu item) does not, so the menu still works on a 1-char prefix.
- **Autocomplete is suppressed inside literals/comments** via the `IGNORED_STYLES` check on `GetStyleAt(pos - 1)`. It is also skipped when `AutoCompActive()` so typing doesn't retrigger mid-filter.
- **`self.pathname` is the quick-save target**; `None` means unsaved, and `onSave` falls through to `OnSaveAs`. Set it in both `openFile` and `writeFile`.
- **Accelerator table**: Ctrl+Q/S/Shift+S/O/1/2. Zoom is bound to Ctrl+1/Ctrl+2, not Ctrl+=/-.

## Known issues

- **Zoom calls `SetFont`, not `STC_STYLE_DEFAULT`.** The font is bound at init via `StyleSetFont(stc.STC_STYLE_DEFAULT, font1)`, so mutating `GetFont()` + `SetFont` does not reliably resize rendered text on STC. Fix by adjusting `stc.STC_STYLE_DEFAULT` instead.
- `self.completions` is a static space-joined `keyword.kwlist | dir(builtins)` built once in `InitUI`. It excludes names defined in the open file, and there is no member completion after `.`.
- File dialogs are `*.py`-only (no "all files"), and both use the `with wx.FileDialog(...)` context-manager form — keep new dialogs consistent or the dialog leaks.

## Conventions

- Formatted with **Black** (configured in `.idea/misc.xml`; Black is *not* installed locally, so don't try to run it). Match surrounding style — the file uses single quotes and `%`-formatting for titles.
- Commit messages are short, imperative, unadorned, no bodies: `Fix autohighlight issue`, `Changed file dialogues`.
- Work on `master`. No release branches or tags.
