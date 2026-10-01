# Morelia

Single-file wxPython (Phoenix) text editor. All application code is `main.py` (~241 lines, one `Frame1` class, no notebook). No package, no build step, no test suite, no CI, no lint config.

## Running

```bash
./linux/run.sh
```

The cwd matters: `main.py` resolves `wx.Icon("icon.png")` and `log.basicConfig(filename="error.log")` against the current directory, so it must be launched from the **repo root**. `run.sh` handles this itself by `cd ..`ing after sourcing `activate.sh`.

Equivalent subshell:

```bash
source linux/activate.sh && python main.py
```

On Windows: `win\setup.bat` then `win\run.bat`.

### The setup scripts are currently broken — verify before trusting them

`linux/setup.sh`, `win/setup.bat`, and `win/run.bat` all `cd` into their own directory and then reference root-relative paths that no longer resolve from there:

- `linux/setup.sh:23` does `cd "$(dirname "$0")"` → `linux/`, then `:101` runs `pip install -r requirements.txt` → `linux/requirements.txt` does not exist. It would also create `linux/.venv` + `linux/.sysroot` instead of the root ones.
- `win/setup.bat:10` cds to `win\`, then `:25` installs `-r requirements.txt` → missing.
- `win/run.bat:4` cds to `win\`, then `:9` runs `main.py` → missing.

`linux/run.sh` *is* correct because it `cd ..`s before execing. The live environment was provisioned before the scripts were moved into `linux/`/`win/`, which is why `.venv/`, `.sysroot/`, and `error.log` sit at the repo root. `linux/activate.sh` is therefore stale relative to `setup.sh`: it points at **root** `.venv`/`.sysroot`, whereas re-running `setup.sh` would generate one pointing into `linux/`. Do not delete the root `.venv`/`.sysroot`.

## Setup

```bash
./linux/setup.sh   # venv + GTK3 sysroot + regenerate activate.sh/run.sh
```

Two jobs, both no-root:

1. A local `.venv/`. `python3-venv/ensurepip` is missing on this host and the system interpreter is PEP 668 externally-managed, so the venv is built `--without-pip` and seeded with `python3 -m pip --python .venv/bin/python install --upgrade pip`.
2. A local `.sysroot/` of GTK3/X11 runtime libs, fetched with `apt-get download` and unpacked with `dpkg-deb -x`. The prebuilt wheel links Ubuntu 24.04 sonames Debian trixie doesn't ship. `setup.sh` also pulls `libjpeg-turbo8` from Ubuntu by hardcoded URL because trixie only has `libjpeg.so.62` (different soname) — don't replace it with the distro package. The full `GTK_PACKAGES` list and its per-package rationale are in `setup.sh`; read it there rather than duplicating it.

`requirements.txt` pins the exact wheel by **direct URL** on Linux, because PyPI has no manylinux wheel for CPython 3.13 on Linux. Windows/macOS use plain `wxPython==4.2.2`.

Sanity-check without launching the app:

```bash
source linux/activate.sh && python -c "import wx; print(wx.version()); a = wx.App(False); print('ok')"
```

`activate.sh` (generated, gitignored, machine-specific) exports five things — all four are load-bearing:

| Var | Consequence if missing |
| --- | --- |
| `LD_LIBRARY_PATH` | `import wx` → "cannot open shared object file" |
| `XKB_CONFIG_ROOT` | **`wx.App(False)` segfaults** during GTK init, with only a misleading `xkbcommon: ERROR: failed to add default include path` on stderr |
| `GSETTINGS_SCHEMA_DIR` | any `wx.FileDialog` aborts the process: `No GSettings schemas are installed on the system`, exit 133. Only the first Ctrl+S on an unsaved file hits this; quick-save of a pathed file never opens a dialog |
| `GDK_BACKEND=x11` | under Wayland the autocompletion popup is never mapped (see below). Set only when `DISPLAY` is set and `GDK_BACKEND` is unset, so an explicit choice wins |

If `import wx` breaks after a wheel change, re-run `setup.sh` to refresh the sysroot; it ends with an `ldd` check on `_core*.so` that fails loudly rather than letting the app die with a bare linker error.

## Gotchas

**Environment / platform**

- **Under Wayland the autocompletion popup is invisible.** Scintilla draws the list in a separate `GTK_WINDOW_POPUP` window that a compositor never maps. It is still logically open — `AutoCompActive()` is `True` and `AutoCompGetCurrent()` returns an item, filtering keeps working, nothing is drawn. Not an app bug; no `AutoCompSet*` flag affects it. Diagnose with `gdk_display_get_name()` returning `wayland-0`.
- **`error.log` is gitignored *and* still tracked** (it predates the ignore rule). Running the app rewrites it and dirties the tree; don't commit the churn. It is a real diagnostic — the only content is historical `Caret.Move()` overload errors.

**wx / Scintilla API**

- **Use `StyledTextCtrl` APIs, not `wx.TextCtrl` ones.** The control is `wx.stc.StyledTextCtrl`: `SetText`/`AppendText`/`GetValue`/`SetLexer`.
- **Never add a `wx.Caret`.** Scintilla draws its own caret, and `wx.Caret` is not even constructible here — `wx.Caret(ctrl, 1)` raises `TypeError: arguments did not match any overloaded call` (the ctor wants a bitmap). `error.log` retains the old `Caret.Move()` failures.
- **Autocomplete is `AutoCompShow(length, items)`.** Phoenix has no `AutoCompStart` (`hasattr` → `False`); calling it raises `AttributeError`. `length` is how many chars before the caret form the filter prefix, which is why it comes from `currentWord()`.
- **`GetUnicodeKey()` returns an `int`, not a `str`** (`WXK_NONE` = 0). Worse, some *special* keys are valid codepoints: `WXK_LEFT` is 314 and `chr(314)` is `'ĺ'`, which **is** alnum, so arrow keys would open a bogus popup. Filter `keycode == wx.WXK_NONE or keycode >= wx.WXK_START` (300) before `chr()`.
- **`WordStartPosition` takes two arguments and returns one int.** `ctrl1.WordStartPosition(pos, False)`; passing only `pos` raises `TypeError`.
- **Bind `EVT_CHAR` to the control, not the frame.** `self.Bind(wx.EVT_CHAR, ...)` on `Frame1` never fires because `ctrl1` consumes the event and it does not propagate. Use `self.ctrl1.Bind(...)`. `EVT_CHAR_HOOK` on the frame *does* work, which is why `autoTab` gets away with it.
- **`GetStyleAt()` returns 0 until colourisation runs**, so style-based logic needs `Colourise(0, -1)` first (there is no `ForceFullColourise` in Phoenix). Critically, **`SetLexer` must have been called too** — with no lexer set, `Colourise` leaves every style at 0 and any `IGNORED_STYLES` guard silently never matches. Verified style numbers: `STC_P_COMMENTLINE=1`, `STC_P_STRING=3`, `STC_P_CHARACTER=4`, `STC_P_WORD=5`, `STC_P_TRIPLE=6`, `STC_P_TRIPLEDOUBLE=7`, `STC_P_OPERATOR=10`, `STC_P_IDENTIFIER=11`, `STC_P_COMMENTBLOCK=12`, `STC_P_STRINGEOL=13`.
- **Always pass `encoding=` to `open()`.** Bare `open()` follows the locale (UTF-8 on dev machines, ASCII under `LC_ALL=C`). Both read and write now pass `"utf-8"`.
- **Zoom must go through the style, not `SetFont`** (see Known issues).
- **Scintilla never accepts a completion on Return.** Per its docs, the selected item is chosen with the *tab character* or a member of `SCI_AUTOCSETFILLUPS` (empty by default, and this app never sets it). So `autoTab` must intercept Return and call `AutoCompComplete()` itself. Two things that will bite:
  - **`AutoCompComplete()` segfaults if the list is not active.** Always guard on `AutoCompActive()`, and additionally on `AutoCompGetCurrent() >= 0` — a list can be active with nothing highlighted, in which case Return should still insert a newline.
  - `autoTab` swallows Return deliberately (it is on `EVT_CHAR_HOOK` and only calls `event.Skip()` for other keys), so without the completion branch a newline lands in the buffer instead of the chosen word. Preserve both skip paths or the editor stops receiving input.

**Editor behaviour**

- **`EVT_CHAR` fires *before* Scintilla inserts the character.** Opening the popup inline makes it lag one keystroke behind, because `currentWord()` can't see the char just typed. `autoComplete` therefore does `event.Skip()` then `wx.CallAfter(self.showAutocomplete)`. Don't "simplify" this back into a direct `AutoCompShow` call.
- **`showAutocomplete` gates on `MIN_COMPLETE_LENGTH = 2`**; `onAutocomplete` (the menu item) does not, so the menu still works on a 1-char prefix.
- **Autocomplete is suppressed inside literals/comments** via the `IGNORED_STYLES` check on `GetStyleAt(pos - 1)`. It is also skipped when `AutoCompActive()` so typing doesn't retrigger mid-filter.
- **`self.pathname` is the quick-save target**; `None` means unsaved, and `onSave` falls through to `OnSaveAs`. Set it in both `openFile` and `writeFile`.
- **Accelerator table**: Ctrl+Q/S/Shift+S/O/1/2. Zoom is bound to Ctrl+1/Ctrl+2, not Ctrl+=/-.

## Known issues

- **Zoom calls `SetFont`, not `STC_STYLE_DEFAULT`.** The font is bound at init via `StyleSetFont(stc.STC_STYLE_DEFAULT, font1)`, so mutating `GetFont()` + `SetFont` does not reliably resize rendered text on STC. Fix by adjusting `stc.STC_STYLE_DEFAULT` instead.
- **`linux/setup.sh`, `win/setup.bat`, and `win/run.bat` are broken** by the cwd bug above (`linux/run.sh` is fine). Highest-value first fix: make each script `cd ..` like `run.sh`, or resolve `main.py`/`requirements.txt` from the repo root.
- `self.completions` is a static space-joined `keyword.kwlist | dir(builtins)` built once in `InitUI`. It excludes names defined in the open file, and there is no member completion after `.`.
- File dialogs are `*.py`-only (no "all files"), and both use the `with wx.FileDialog(...)` context-manager form — keep new dialogs consistent or the dialog leaks.

## Conventions

- Formatted with **Black** (configured in `.idea/misc.xml`; Black is *not* installed locally, so don't try to run it). Match surrounding style — the file uses single quotes and `%`-formatting for titles.
- Commit messages are short, imperative, unadorned, no bodies: `Fix autohighlight issue`, `Changed file dialogues`.
- Work on `master`. No release branches or tags.
