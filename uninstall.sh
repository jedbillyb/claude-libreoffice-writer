#!/usr/bin/env bash
# Remove the extension from LibreOffice and the interpreter config.
set -euo pipefail
cd "$(dirname "$0")"

if pgrep -x soffice.bin >/dev/null 2>&1; then
  echo "Close LibreOffice first, then re-run."; exit 1
fi

unopkg remove org.quill.writer 2>/dev/null || echo "(extension was not installed)"
rm -f "$HOME/.config/quill/python"
echo "Removed. The sidecar venv (.venv) was left in place — 'rm -rf .venv' to delete it."
