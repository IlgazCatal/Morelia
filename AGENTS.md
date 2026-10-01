# Morelia

Single-file wxPython (Phoenix) text editor. All application code lives in `main.py` (~210 lines, one `Frame1` class). There is no package and no build step; `setup.sh` only provisions a venv. There is no committed test suite.

## Running

```bash
./run.sh
```

The cwd matters: `wx.Icon("icon.png")` and `log.basicConfig(filename="error.log")` are both relative paths. Launching from any other directory silently breaks the window icon and scatters the log.

On Windows use the `.bat` equivalents:

```bat
setup.bat
run.bat
```

`main.py` itself is platform-agnostic — it uses only plain relative filenames, no POSIX-only paths, and no `os.path` calls, so the same file runs on Linux, Windows, and macOS. Only the setup scripts differ per platform.

Alternatively, if you prefer a subshell, source the generated activation script:

```bash
source activate.sh && python main.py
```

## Setup

```bash
./setup.sh
```

The setup script provisions two things:
- a local Python virtualenv in `.venv/` with wxPython installed (it handles the missing `ensurepip` case on Debian)
- a local `.sysroot/` of GTK3/X11 runtime libraries extracted from `.deb` packages (no root required). `run.sh` and `activate.sh` automatically set `LD_LIBRARY_PATH` and `XKB_CONFIG_ROOT` to point at it. This is needed because the prebuilt wxPython wheel links against Ubuntu 24.04 sonames that are not present on Debian trixie.

The script is idempotent and will skip work if `.venv/` and `.sysroot/` are already present. If `import wx` fails with "cannot open shared object file" after updating the wheel, re-run `./setup.sh` to refresh the sysroot.

`activate.sh` is generated with absolute paths from the current checkout, so it is machine-specific and ignored by git. `run.sh`, `setup.sh`, `setup.bat`, and `run.bat` are committed. `.sysroot/` and `.venv/` are ignored. `requirements.txt` pins the exact wxPython wheel and `six`.

On Windows there is no sysroot step: official `wxPython==4.2.2` cp313 wheels exist, so `setup.bat` only creates the venv and installs from `requirements.txt`. The `--without-pip` + `pip --python` bootstrap is kept in `setup.bat` because it is harmless on machines that have `ensurepip`, and necessary on those that do not.

### If `pip install wxPython` builds from source

On Linux, CPython 3.13 has no manylinux wheel on PyPI, so a bare `wxPython==4.2.2` pin falls back to a source build and fails at `Error running configure` unless GTK dev packages are present. `requirements.txt` therefore pins a direct URL under `sys_platform == "linux"`; Windows and macOS use plain version pins, because official wheels exist there. On Linux the URL is:

```bash
pip install https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-24.04/wxPython-4.2.2-cp313-cp313-linux_x86_64.whl
```

The wheel is built against Ubuntu 24.04 system libraries. On a different distro you must supply the GTK3 runtime libs yourself (no root needed):

```bash
export LD_LIBRARY_PATH=/path/to/sysroot/usr/lib/x86_64-linux-gnu:/path/to/sysroot/usr/lib/x86_64-linux-gnu/pulseaudio:/path/to/sysroot/lib/x86_64-linux-gnu
export XKB_CONFIG_ROOT=/path/to/sysroot/usr/share/X11/xkb   # required, or wx.App() segfaults
```

`XKB_CONFIG_ROOT` matters: without it libxkbcommon cannot find `xkb/` and `wx.App(False)` **segfaults** during GTK init, with only a misleading `xkbcommon: ERROR: failed to add default include path` on stderr. Build the sysroot with `apt-get download <pkg>` plus `dpkg-deb -x pkg.deb /path/to/sysroot` (no root required); the packages are `libgtk-3-0t64`, `libnotify4`, `libcairo-gobject2`, `libsndfile1`, `libpulse0`, and the usual `libx*`/`libatk*` set.

To sanity-check the install without launching the app:

```bash
python -c "import wx; print(wx.version()); a = wx.App(False); print('ok')"
```

## Gotchas

- **`error.log` is tracked in git.** Running the app rewrites it and dirties the working tree. Don't commit incidental log churn; it exists only to surface wx-internal errors (nothing in `main.py` calls `log.*` explicitly, yet the file captures framework-level messages, so it is a real diagnostic).
- **Use `StyledTextCtrl` APIs, not `wx.TextCtrl` ones.** The control is `wx.stc.StyledTextCtrl` (Scintilla): `SetText`/`AppendText`/`GetValue`/`SetLexer`. Scintilla's caret is drawn by the control itself, so do **not** add a `wx.Caret`; a `Caret.Move()` on this panel throws on every startup.
- **Autocomplete is `AutoCompShow(length, items)`, not `AutoCompStart`.** Phoenix has no `AutoCompStart` — calling it raises `AttributeError`. The `length` argument is how many chars before the caret form the filter prefix. Configure via `AutoCompSet*` (`AutoCompSetIgnoreCase`, `AutoCompSetAutoHide`, `AutoCompSetMaxHeight`, `AutoCompSetCancelAtStart`).
- **`GetUnicodeKey()` returns an `int`, not a `str`** (`WXK_NONE` = 0 for non-printable keys). Wrap in `chr()` before calling string methods. Worse, some *special* keys are valid codepoints — `WXK_LEFT` is 314 and `chr(314)` is `'ĺ'`, which **is** alnum — so filter `keycode >= wx.WXK_START` (300) before `chr()`, or arrow keys fire a bogus popup.
- **Bind `EVT_CHAR` to the control, not the frame.** `self.Bind(wx.EVT_CHAR, ...)` on the `Frame1` never fires: `ctrl1` consumes the key event and it does not propagate up. Use `self.ctrl1.Bind(wx.EVT_CHAR, ...)`. `EVT_CHAR_HOOK` on the frame does work, which is why `autoTab` gets away with it.
- **`WordStartPosition` takes two arguments.** `ctrl1.WordStartPosition(pos, False)` → `int`. Passing only `pos` raises `TypeError: not enough arguments`.
- **Scintilla styles are only computed on idle.** `GetStyleAt()` returns 0 (default) until colourisation runs, so any test asserting on style-based logic must call `ctrl1.Colourise(0, -1)` first. There is no `ForceFullColourise` in Phoenix.
- **Always pass `encoding=` to `open()`.** Bare `open()` uses the locale encoding, which is UTF-8 on most dev machines but ASCII under `LC_ALL=C`, so non-ASCII bugs hide until they bite users. The repo now uses explicit `utf-8` on both read and write.
- **Zoom must go through the style, not `SetFont`.** `onZoomIn`/`onZoomOut` mutate `GetFont()` and call `ctrl1.SetFont`. That does not resize the rendered text reliably on STC — the font is bound via `StyleSetFont(stc.STC_STYLE_DEFAULT, ...)` at init. Prefer adjusting `stc.STC_STYLE_DEFAULT`.
- **`autoTab` swallows Return on purpose.** It's bound to `EVT_CHAR_HOOK` and only calls `event.Skip()` for non-Return keys. If you add keys, preserve the skip path or the editor will stop receiving input.
- **The file dialogs are `.py`-only** (`*.py` wildcard, no "all files"). Both open and save use the `with wx.FileDialog(...)` context-manager form — keep new dialogs consistent, otherwise the dialog leaks.
- **Ctrl+S on an unsaved file aborts with `No GSettings schemas are installed on the system`.** `wx.FileDialog` uses GTK's native chooser, which calls `g_settings_new()`; with no reachable schema cache GLib raises a fatal `GLib-GIO-ERROR` (the process dies with `Trace/breakpoint trap`, exit 133). The sysroot's `libgtk-3-common` and `gsettings-desktop-schemas` provide only `.gschema.xml`, so `setup.sh` compiles them with `glib-compile-schemas` and `activate.sh` exports `GSETTINGS_SCHEMA_DIR` pointing at the result. If you see this after a wheel/sysroot change, re-run `./setup.sh`; quick-save of an already-pathed file never opens a dialog and is unaffected.
- **Under Wayland the autocompletion popup is invisible.** Scintilla draws the completion list in a separate `GTK_WINDOW_POPUP` window, and a Wayland compositor (Weston included) never maps it. The list is still logically open — `AutoCompActive()` returns `True` and `AutoCompGetCurrent()` returns an item — the editing keys keep filtering, but nothing is drawn. This is *not* an app bug and no `AutoCompSet*` flag affects it; forcing the X11 backend fixes it. `activate.sh` therefore sets `GDK_BACKEND=x11` when `DISPLAY` is set (XWayland counts), unless `GDK_BACKEND` is already exported. Diagnose with GDK: if `gdk_display_get_name()` says `wayland-0`, the popup will not render.

## Known issues

- Zoom still calls `SetFont` rather than adjusting `STC_STYLE_DEFAULT`, so it is unreliable on STC (see Gotchas).
- `self.completions` is a static keyword + `builtins` list built once in `InitUI`. It does not include names defined in the open file, and there is no member completion after `.`.
- The old `#TODO` markers at the top of `main.py` were stale and have been removed; syntax highlighting landed in `89a9fc4`.

## Conventions

- The project is formatted with **Black** (configured in `.idea/misc.xml`); Black is not installed locally. Match surrounding style when editing.
- Commit messages are short, imperative, and unadorned: `Fix autohighlight issue`, `Changed file dialogues`. No prefixes, no bodies.
- Work on `master`; there are no release branches or tags.
