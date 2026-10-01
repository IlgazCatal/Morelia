#!/usr/bin/env bash
# Set up the Morelia virtualenv and the GTK3 runtime libraries wxPython needs.
#
# Why this script exists instead of a plain "python3 -m venv .venv":
#   1. Debian/Ubuntu mark the system interpreter as externally managed
#      (PEP 668), so "pip install" into it is refused by design.
#   2. python3-venv/ensurepip is not installed on this machine, so a stock
#      venv is created without pip and ".venv/bin/pip install" then fails
#      with "No such file or directory".
# The venv is therefore built with --without-pip and seeded from the system
# interpreter's pip, which is a supported way to target another environment.
#
# It also unpacks the GTK3 shared libraries into .sysroot/, because the
# prebuilt wxPython wheel links against Ubuntu 24.04 libraries that Debian
# trixie does not ship in matching sonames. No root is required: packages are
# fetched with "apt-get download" and unpacked with "dpkg-deb -x".
#
# Usage:
#   ./setup.sh              set up venv + sysroot
#   source activate.sh      then just run "python main.py"
set -euo pipefail

cd "$(dirname "$0")"

VENV=.venv
SYSROOT=.sysroot

# GTK3 and its transitive shared-library dependencies. Every entry below was
# confirmed by ldd against the installed wxPython extension modules; adding a
# name that is not needed is harmless, omitting one that is needed makes
# "import wx" fail with a bare "cannot open shared object file".
GTK_PACKAGES=(
  libgtk-3-0t64          # core toolkit
  libgtk-3-common        # /usr/share/glib-2.0/schemas/org.gtk.Settings.*.gschema.xml
  gsettings-desktop-schemas  # org.gnome.desktop.* needed by the GTK file chooser
  libgdk-pixbuf-2.0-0
  libcairo-gobject2
  libnotify4
  libepoxy0
  libcolord2
  libdatrie1
  libdecor-0-0
  libcloudproviders0
  libatk1.0-0t64
  libatk-bridge2.0-0t64
  libatspi2.0-0t64
  libpcre2-32-0
  libpixman-1-0
  libx11-6
  libxau6
  libxdmcp6
  libxcb1
  libxcb-render0
  libxcb-shm0
  libxcomposite1
  libxcursor1
  libxdamage1
  libxext6
  libxinerama1
  libxkbcommon0
  libxrandr2
  libxss1
  libxtst6
  libgl1
  libglx0
  libglvnd0
  libwayland-cursor0
  libwayland-egl1
  libpulse0
  libpulse-mainloop-glib0
  libasound2t64
  libasyncns0
  libsndfile1
  libflac14
  libogg0
  libopus0
  libvorbis0a
  libvorbisenc2
  libmp3lame0
  libmpg123-0t64
  libsamplerate0
  libsdl2-2.0-0
  xkb-data               # X keyboard rules/symbols, see below
)

# The Ubuntu 24.04 wheel links against libjpeg.so.8. Debian trixie's
# libjpeg62-turbo only ships libjpeg.so.62 (different soname), so the Ubuntu
# package has to be fetched directly. Its own dependencies are already
# installed on the host, so unpacking it alone is enough.
UBUNTU_JPEG_DEB=http://archive.ubuntu.com/ubuntu/pool/main/libj/libjpeg-turbo/libjpeg-turbo8_2.1.5-4ubuntu4_amd64.deb

echo "==> Creating $VENV"
[ -d "$VENV" ] || python3 -m venv --without-pip "$VENV"

if [ ! -x "$VENV/bin/pip" ]; then
  echo "==> Bootstrapping pip into $VENV"
  python3 -m pip --python "$VENV/bin/python" install --upgrade pip
fi

echo "==> Installing Python requirements"
"$VENV/bin/pip" install -r requirements.txt

# ---------------------------------------------------------------------------
# GTK3 runtime libraries
# ---------------------------------------------------------------------------
if [ -f "$SYSROOT/.stamp" ] && [ -d "$SYSROOT/usr/share/X11/xkb" ] \
   && [ -f "$SYSROOT/usr/share/glib-2.0/schemas/gschemas.compiled" ]; then
  echo "==> $SYSROOT already populated, skipping"
else
  echo "==> Fetching GTK3 runtime libraries into $SYSROOT (no root needed)"
  debs=$(mktemp -d)
  trap 'rm -rf "$debs"' EXIT

  for pkg in "${GTK_PACKAGES[@]}"; do
    # Some names are not resolvable directly (e.g. libmpg123-0 does not
    # exist on trixie but libmpg123-0t64 does); fall back to an apt search.
    if ! (cd "$debs" && apt-get download "$pkg" >/dev/null 2>&1); then
      alt=$(apt-cache search --names-only "^${pkg}[0-9]" 2>/dev/null | awk '{print $1}' | head -1)
      if [ -n "$alt" ] && (cd "$debs" && apt-get download "$alt" >/dev/null 2>&1); then
        echo "    $pkg -> $alt"
      else
        echo "    WARNING: could not download $pkg, continuing" >&2
      fi
    fi
  done

  echo "==> Fetching libjpeg.so.8 from Ubuntu (soname mismatch with Debian)"
  if ! (cd "$debs" && curl -fsSLO "$UBUNTU_JPEG_DEB"); then
    echo "    WARNING: could not download libjpeg-turbo8, import wx will fail" >&2
  fi

  echo "==> Unpacking into $SYSROOT"
  mkdir -p "$SYSROOT"
  for d in "$debs"/*.deb; do
    [ -f "$d" ] && dpkg-deb -x "$d" "$SYSROOT"
  done

  # GTK's native file chooser calls g_settings_new(), which aborts the whole
  # process with "No GSettings schemas are installed on the system" unless a
  # compiled schema cache is reachable. The .debs ship only .gschema.xml, so
  # compile them here; activate.sh points GSETTINGS_SCHEMA_DIR at the result.
  echo "==> Compiling GSettings schemas"
  compile_schemas="$(command -v glib-compile-schemas || true)"
  if [ -z "$compile_schemas" ] \
     && [ -x /usr/lib/x86_64-linux-gnu/glib-2.0/glib-compile-schemas ]; then
    compile_schemas=/usr/lib/x86_64-linux-gnu/glib-2.0/glib-compile-schemas
  fi
  if [ -n "$compile_schemas" ]; then
    "$compile_schemas" "$SYSROOT/usr/share/glib-2.0/schemas/"
  else
    echo "    WARNING: glib-compile-schemas not found; Ctrl+S on an unsaved" >&2
    echo "             file will abort with No GSettings schemas." >&2
  fi
  touch "$SYSROOT/.stamp"
fi

# Fail loudly here rather than letting the app die with a bare linker error.
sysroot_ldpath="$SYSROOT/usr/lib/x86_64-linux-gnu:$SYSROOT/usr/lib/x86_64-linux-gnu/pulseaudio:$SYSROOT/lib/x86_64-linux-gnu"
unresolved=$(LD_LIBRARY_PATH="$sysroot_ldpath" \
  ldd .venv/lib/python3.13/site-packages/wx/_core*.so 2>/dev/null | grep "not found" || true)
if [ -n "$unresolved" ]; then
  echo "ERROR: some wxPython shared libraries are still unresolved:" >&2
  echo "$unresolved" >&2
  exit 1
fi
echo "==> All wxPython shared libraries resolve"

# libxkbcommon looks for keyboard data under /usr/share/X11/xkb. Without it
# wx.App() segfaults during GTK init, printing only a misleading
# "xkbcommon: ERROR: failed to add default include path". activate.sh sets
# XKB_CONFIG_ROOT to point at the copy we just unpacked.
if [ ! -d "$SYSROOT/usr/share/X11/xkb" ]; then
  echo "ERROR: $SYSROOT/usr/share/X11/xkb is missing; the app will segfault." >&2
  exit 1
fi

cat > activate.sh <<EOF
#!/usr/bin/env bash
# Source this to get a working Morelia environment:  source activate.sh
export LD_LIBRARY_PATH="$PWD/$SYSROOT/usr/lib/x86_64-linux-gnu:$PWD/$SYSROOT/usr/lib/x86_64-linux-gnu/pulseaudio:$PWD/$SYSROOT/lib/x86_64-linux-gnu\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export XKB_CONFIG_ROOT="$PWD/$SYSROOT/usr/share/X11/xkb"
export PATH="$PWD/$VENV/bin:\$PATH"

# GTK's native file chooser (wx.FileDialog) calls g_settings_new(); with no
# reachable schema cache the whole process aborts with "No GSettings schemas
# are installed on the system". Point GLib at the schemas compiled into the
# sysroot so Ctrl+S on an unsaved file can open Save As.
export GSETTINGS_SCHEMA_DIR="$PWD/$SYSROOT/usr/share/glib-2.0/schemas\${GSETTINGS_SCHEMA_DIR:+:\$GSETTINGS_SCHEMA_DIR}"

# Scintilla draws the autocompletion list in a separate GTK popup window.
# Under a Wayland compositor that popup is never mapped, so completion silently
# works but the list is invisible. Prefer the X11 backend when an X display is
# reachable (XWayland counts). Set GDK_BACKEND yourself to override.
if [ -n "\${DISPLAY:-}" ] && [ -z "\${GDK_BACKEND:-}" ]; then
  export GDK_BACKEND=x11
fi
EOF

cat > run.sh <<'EOF'
#!/usr/bin/env bash
# Run the editor without activating anything:  ./run.sh
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck source=/dev/null
source ./activate.sh
# main.py resolves "icon.png" and "error.log" against the current directory,
# so it MUST be launched from the repo root, not from linux/.
cd ..
exec python main.py "$@"
EOF
chmod +x run.sh

echo
echo "Done."
echo
echo "  ./run.sh              launch the editor"
echo "  source activate.sh    then: python main.py"