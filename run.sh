#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source ./activate.sh
exec python main.py "$@"
