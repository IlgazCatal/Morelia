#!/usr/bin/env bash
# Set up the Morelia virtualenv and the GTK3 runtime libraries wxPython needs.
# Run from repo root.

set -euo pipefail

VENV=.venv
SYSROOT=.sysroot

GTK_PACKAGES=(
  libgtk-3-0t64 libgtk-3-common gsettings-desktop-schemas
  libgdk-pixbuf-2.0-0 libcairo-gobject2 libnotify4 libepoxy0 libcolord2
  libdatrie1 libdecor-0-0 libcloudproviders0 libatk1.0-0t64
  libatk-bridge2.0-0t64 libatspi2.0-0t64 libpcre2-32-0 libpixman-1-0
  libx11-6 libxau6 libxdmcp6 libxcb1 libxcb-render0 libxcb-shm0
  libxcomposite1 libxcursor1 libxdamage1 libxext6 libxinerama1
  libxkbcommon0 libxrandr2 libxss1 libxtst6 libgl1 libglx0 libglvnd0
  libwayland-cursor0 libwayland-egl1 libpulse0 libpulse-mainloop-glib0
  libasound2t64 libasyncns0 libsndfile1 libflac14 libogg0 libopus0
  libvorbis0a libvorbisenc2 libmp3lame0 libmpg123-0t64
  libjpeg-turbo8
)

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get not found; assuming packages available"
fi

if [ ! -d "$VENV" ]; then
  echo "==> Creating $VENV"
  python3 -m venv --without-pip "$VENV"
fi

if [ ! -x "$VENV/bin/pip" ]; then
  echo "==> Bootstrapping pip into $VENV"
  python3 -m pip --python "$VENV/bin/python" install --upgrade pip
fi

echo "==> Installing Python requirements"
"$VENV/bin/pip" install -r requirements.txt

if [ ! -d "$SYSROOT" ]; then
  echo "==> Fetching GTK runtime libraries into $SYSROOT"
  mkdir -p "$SYSROOT"
  PKG_DIR="$(mktemp -d)"
  for pkg in "${GTK_PACKAGES[@]}"; do
    if ! apt-get download "$pkg" -o Dir::Cache::archives="$PKG_DIR" >/dev/null 2>&1; then
      echo "warning: failed to download $pkg"
    fi
  done
  for deb in "$PKG_DIR"/*.deb; do
    [ -f "$deb" ] || continue
    dpkg-deb -x "$deb" "$SYSROOT"
  done
  rm -rf "$PKG_DIR"
fi

if [ ! -s libjpeg-turbo8_*.deb ] 2>/dev/null; then
  :
fi

echo "==> Generating activate.sh"
cat > activate.sh << ACT
#!/usr/bin/env bash
VENV_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)/.venv"
SYSROOT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)/.sysroot"
export PATH="\$VENV_DIR/bin:\$PATH"
export LD_LIBRARY_PATH="\$SYSROOT_DIR/usr/lib/x86_64-linux-gnu:\$SYSROOT_DIR/lib/x86_64-linux-gnu:\$LD_LIBRARY_PATH"
export XKB_CONFIG_ROOT="\$SYSROOT_DIR/usr/share/X11/xkb"
export GSETTINGS_SCHEMA_DIR="\$SYSROOT_DIR/usr/share/glib-2.0/schemas"
if [ -z "\${GDK_BACKEND:-}" ] && [ -n "\${DISPLAY:-}" ]; then
  export GDK_BACKEND=x11
fi
ACT
chmod +x activate.sh

echo "==> Generating run.sh"
cat > run.sh << RUN
#!/usr/bin/env bash
set -euo pipefail
cd "\$(dirname "\$0")"
source ./activate.sh
exec python main.py "\$@"
RUN
chmod +x run.sh

echo "==> Verifying wx import"
# shellcheck source=/dev/null
source ./activate.sh
python -c "import wx; print('wx', wx.version())" || true

echo "Done."
