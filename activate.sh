#!/usr/bin/env bash
VENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.venv"
SYSROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.sysroot"
export PATH="$VENV_DIR/bin:$PATH"

LD_LIBRARY_PATH=""
for d in \
  "$SYSROOT_DIR/usr/lib/x86_64-linux-gnu" \
  "$SYSROOT_DIR/lib/x86_64-linux-gnu" \
  "$SYSROOT_DIR/usr/lib/x86_64-linux-gnu/pulseaudio" \
  "$SYSROOT_DIR/usr/lib/x86_64-linux-gnu/gtk-3.0/modules" \
  ; do
  if [ -d "$d" ]; then
    if [ -z "$LD_LIBRARY_PATH" ]; then
      LD_LIBRARY_PATH="$d"
    else
      LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$d"
    fi
  fi
done
export LD_LIBRARY_PATH

export XKB_CONFIG_ROOT="$SYSROOT_DIR/usr/share/X11/xkb"
export GSETTINGS_SCHEMA_DIR="$SYSROOT_DIR/usr/share/glib-2.0/schemas"
if [ -z "${GDK_BACKEND:-}" ] && [ -n "${DISPLAY:-}" ]; then
  export GDK_BACKEND=x11
fi
