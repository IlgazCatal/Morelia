#!/usr/bin/env bash
# Run the editor without activating anything:  ./run.sh
set -euo pipefail
# activate.sh lives next to this script and holds absolute paths, so source it
# from this directory first.
cd "$(dirname "$0")"
# shellcheck source=/dev/null
source ./activate.sh
# main.py resolves "icon.png" and "error.log" against the current directory,
# so it MUST be launched from the repo root, not from linux/.
cd ..
exec python main.py "$@"
