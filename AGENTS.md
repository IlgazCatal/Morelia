# AGENTS.md

## Overview

- **Single file app:** All logic lives in `main.py` (804 lines). Classes: `Frame1`, `RunArgsDialog`, `SearchDialog`, `FuzzyDialog`, `RunOutputFrame`. No package, build step, test suite, CI, lint, or typecheck.
- **Scope:** wxPython (Phoenix) + Scintilla text editor. Run everything from repo root - all script paths are relative to it.
- **Notes on docs:** `README.md` is user-facing and may be stale relative to root scripts. Trust `main.py` and root-level scripts when they disagree.

## Run

```bash
./run.sh                                     # activate.sh + python main.py
source ./activate.sh && python main.py       # equivalent by hand
```

`run.sh` and `linux_run.sh` are byte-identical duplicates.

## Setup (Linux)

- `./linux_setup.sh` creates `.venv/` and `.sysroot/` (gitignored), and regenerates `activate.sh`/`run.sh` from heredocs.
- **Critical:** The heredoc in `linux_setup.sh` (lines 62–73) omits `pulseaudio` and `gtk-3.0/modules` from `LD_LIBRARY_PATH`. The tracked `activate.sh` includes them. Overwriting the tracked `activate.sh` breaks the app (`ImportError: libpulsecommon-17.0.so: cannot open shared object file`). Back it up first or fix the heredoc to match the tracked version.
- `.venv` is built `--without-pip` and bootstrapped via `python3 -m pip --python .venv/bin/python install --upgrade pip` (PEP 668 externally-managed). GTK deps are extracted via `apt-get download` + `dpkg-deb -x` into `.sysroot/` (Debian trixie targeting Ubuntu 24.04 wheel).
- Windows files (`windows_setup.bat`/`windows_run.bat`) exist; tracked `run.bat`/`setup.bat` show as deleted (replaced). `.win.bak` and `.linux.bak` hold pre-move copies.
- `requirements.txt` pins the Linux wheel by direct URL (no manylinux CPython 3.13 wheel on PyPI); Windows/macOS by version.

## Verification

Quick sanity check:
```bash
source ./activate.sh && python -c "import wx; print(wx.version()); a = wx.App(False); print('ok')"
```

For UI behavior, driving with `wx.UIActionSimulator` (frame must be shown, focused, and yield/sleep between keys) is effective. Do not rely on pixel reads - `wx.ScreenDC.Blit` returns True but reads all black even for visible content.

## Environment Quirks (Must-Know)

- `GSETTINGS_SCHEMA_DIR` must point to the sysroot schemas. If unset, opening a `wx.FileDialog` (e.g. Ctrl+S on unsaved file) crashes with `GLib-GIO-ERROR: No GSettings schemas are installed`.
- `GDK_BACKEND=x11` is required when using XWayland - Wayland breaks Scintilla's popup completion list (`AutoCompActive()` becomes True but popup never maps). The activate script only sets this if unset and DISPLAY is set.
- `LD_LIBRARY_PATH` must include `.sysroot/usr/lib/x86_64-linux-gnu/pulseaudio` and `.sysroot/usr/lib/x86_64-linux-gnu/gtk-3.0/modules` (tracked activate.sh has them).
- `activate.sh` is tracked (even though `.gitignore` lists it). The heredoc in `linux_setup.sh` omits the pulseaudio/gtk-3.0 modules entries - don't blindly overwrite it.
